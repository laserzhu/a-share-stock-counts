import os
import sys
import subprocess
from datetime import datetime, time, timedelta, timezone
import json

# 自动安装依赖
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import requests
    import chinese_calendar
except ImportError:
    print("正在安装缺失依赖...")
    install("requests")
    install("chinesecalendar")
    import requests
    import chinese_calendar


# 北京时间
def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)


# 预警参数
UP_THRESHOLD = 3500
DOWN_THRESHOLD = 3500
INCREMENT_THRESHOLD = 10

STATUS_FILE = "status.json"


# 状态读取
def load_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"last_alert_up_level": 0, "last_alert_down_level": 0}


# 保存状态
def save_status(status):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


# 获取市场数据
def fetch_market_data():

    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    now = get_beijing_time()

    result = {
        "up": 0,
        "down": 0,
        "flat": 0,
        "limit_up": 0,
        "limit_down": 0,
        "indices": [],
        "date": now.strftime("%Y-%m-%d %H:%M")
    }

    # 主接口
    try:

        url = "https://push2ex.eastmoney.com/api/qt/pts/get"

        params = {
            "fields1": "f1,f2,f3",
            "fields2": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }

        res = requests.get(url, params=params, headers=headers, timeout=10).json()

        if res and res.get("data"):

            data = res["data"]

            result["up"] = data.get("f2", 0)
            result["down"] = data.get("f3", 0)
            result["flat"] = data.get("f4", 0)
            result["limit_up"] = data.get("f14", 0)
            result["limit_down"] = data.get("f15", 0)

    except Exception as e:
        print("主接口失败:", e)

    # 备用接口（防止返回0）
    if result["up"] == 0 and result["down"] == 0:

        try:

            url = "https://push2.eastmoney.com/api/qt/ulist.np/get"

            params = {
                "fltt": "2",
                "secids": "1.000001,0.399001",
                "fields": "f104,f105,f106",
                "ut": "b2884a393a59ad64002292a3e90d46a5"
            }

            res = requests.get(url, params=params, headers=headers, timeout=10).json()

            if res and "data" in res and "diff" in res["data"]:

                for i in res["data"]["diff"]:
                    result["up"] += i.get("f104", 0)
                    result["down"] += i.get("f105", 0)
                    result["flat"] += i.get("f106", 0)

        except Exception as e:
            print("备用接口失败:", e)

    # 指数
    try:

        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"

        params = {
            "fltt": "2",
            "secids": "1.000001,0.399001,0.399006,1.000688",
            "fields": "f2,f3,f12,f14",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }

        res = requests.get(url, params=params, headers=headers, timeout=10).json()

        if res and "data" in res and "diff" in res["data"]:

            for idx in res["data"]["diff"]:

                result["indices"].append({
                    "name": idx.get("f14"),
                    "price": idx.get("f2"),
                    "pct": idx.get("f3")
                })

    except Exception as e:
        print("指数接口失败:", e)

    return result


# 判断交易时间
def is_trading_time(now):

    if now.weekday() >= 5:
        return False

    if chinese_calendar.is_holiday(now.date()):
        return False

    t = now.time()

    return time(9, 0) <= t <= time(15, 0)


# 统一消息格式
def format_market_message(result):

    up = result["up"]
    down = result["down"]
    flat = result["flat"]

    limit_up = result["limit_up"]
    limit_down = result["limit_down"]

    msg = ""

    msg += f"涨: <font color=\"warning\">{up}</font>  |  跌: <font color=\"info\">{down}</font>  |  平: {flat}\n"
    msg += f"总计家数: {up + down + flat}\n"
    msg += f"涨停: <font color=\"warning\">{limit_up}</font> |  跌停: <font color=\"info\">{limit_down}</font>\n"

    msg += "--------------------------------\n"

    for idx in result["indices"]:

        pct = idx["pct"] or 0

        if pct > 0:
            color = "warning"
        elif pct < 0:
            color = "info"
        else:
            color = "comment"

        msg += f"{idx['name']}: {idx['price']} (<font color=\"{color}\">{pct}%</font>)\n"

    msg += "--------------------------------\n"

    msg += f"查询时间: {result['date']}"

    return msg


# 企业微信发送
def send_wechat(msg, key):

    if not key:
        return

    if "?key=" in key:
        key = key.split("?key=")[1]

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": msg}
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("发送失败:", e)


# 主程序
def main():

    event = os.environ.get("GITHUB_EVENT_NAME", "manual")

    now = get_beijing_time()

    key = os.environ.get("QYWECHAT_KEY")

    result = fetch_market_data()

    # 手动触发
    if event in ["workflow_dispatch", "manual"]:

        msg = format_market_message(result)

        send_wechat(msg, key)

        return

    # 自动监控
    if event == "schedule":

        if not is_trading_time(now):
            return

        status = load_status()

        up = result["up"]
        down = result["down"]

        alert = ""
        notify = False

        # 上涨
        if up >= UP_THRESHOLD:

            if status["last_alert_up_level"] == 0:

                alert += f"### 上涨预警\n> 上涨家数: <font color=\"warning\">{up}</font>\n\n"
                status["last_alert_up_level"] = up
                notify = True

            elif abs(up - status["last_alert_up_level"]) >= INCREMENT_THRESHOLD:

                alert += f"### 上涨变动\n> 上涨家数: <font color=\"warning\">{up}</font>\n\n"
                status["last_alert_up_level"] = up
                notify = True

        else:
            status["last_alert_up_level"] = 0

        # 下跌
        if down >= DOWN_THRESHOLD:

            if status["last_alert_down_level"] == 0:

                alert += f"### 下跌预警\n> 下跌家数: <font color=\"info\">{down}</font>\n\n"
                status["last_alert_down_level"] = down
                notify = True

            elif abs(down - status["last_alert_down_level"]) >= INCREMENT_THRESHOLD:

                alert += f"### 下跌变动\n> 下跌家数: <font color=\"info\">{down}</font>\n\n"
                status["last_alert_down_level"] = down
                notify = True

        else:
            status["last_alert_down_level"] = 0

        if notify:

            msg = alert + format_market_message(result)

            send_wechat(msg, key)

            save_status(status)


if __name__ == "__main__":
    main()
