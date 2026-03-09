import os
import sys
import subprocess
from datetime import datetime, time, timedelta, timezone
import json
import re
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
INCREMENT_THRESHOLD = 250
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
    # 1. 获取涨跌分布数据和涨跌停数据 from 同花顺官网页面
    try:
        url = "https://q.10jqka.com.cn/"
        res = requests.get(url, headers=headers, timeout=5)
        text = res.text
        up_match = re.search(r'上涨：(\d+)只', text)
        down_match = re.search(r'下跌：(\d+)只', text)
        limit_up_match = re.search(r'涨停：(\d+)只', text)
        limit_down_match = re.search(r'跌停：(\d+)只', text)
        if up_match:
            result["up"] = int(up_match.group(1))
        if down_match:
            result["down"] = int(down_match.group(1))
        result["flat"] = 0  # 同花顺页面未显示平盘家数，设为0
        if limit_up_match:
            result["limit_up"] = int(limit_up_match.group(1))
        if limit_down_match:
            result["limit_down"] = int(limit_down_match.group(1))
    except Exception as e:
        print("同花顺页面接口失败:", e)
    # 3. 获取指数数据
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "secids": "1.000001,0.399001,0.399006,1.000688",
            "fields": "f2,f3,f12,f14",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }
        res = requests.get(url, params=params, headers=headers, timeout=5).json()
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
    # 周一到周五
    if now.weekday() >= 5:
        return False
    # 法定节假日
    if chinese_calendar.is_holiday(now.date()):
        return False
    # 交易时间段
    t = now.time()
    return time(9, 30) <= t <= time(15, 0)
# 统一消息格式
def format_market_message(result):
    up = result["up"]
    down = result["down"]
    flat = result["flat"]
    limit_up = result["limit_up"]
    limit_down = result["limit_down"]
    total = up + down + flat
    msg = f"**A股市场全景**\n"
    msg += f"> 涨: <font color=\"warning\">{up}</font> | 跌: <font color=\"info\">{down}</font> | 平: {flat}\n"
    msg += f"> 总计: {total}\n"
    msg += f"> 涨停: <font color=\"warning\">{limit_up}</font> | 跌停: <font color=\"info\">{limit_down}</font>\n"
    msg += "**主要指数**\n"
    for idx in result["indices"]:
        pct = idx["pct"] or 0
        color = "warning" if pct > 0 else "info" if pct < 0 else "comment"
        price = "{:.2f}".format(idx["price"] / 100) if idx["price"] else "-"
        msg += f"> {idx['name']}: {price} (<font color=\"{color}\">{pct}%</font>)\n"
    msg += f"<font color=\"comment\">{result['date']}</font>"
    return msg
# 企业微信发送
def send_wechat(msg, key):
    if not key:
        return
    if "?key=" in key:
        key = key.split("?key=")[1]
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    payload = {"msgtype": "markdown", "markdown": {"content": msg}}
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("微信返回:", res.status_code, res.text)
    except Exception as e:
        print("发送失败:", e)
# 主程序
def main():
    event = os.environ.get("GITHUB_EVENT_NAME", "manual")
    now = get_beijing_time()
    key = os.environ.get("QYWECHAT_KEY")
    result = fetch_market_data()
    # 手动触发，或数据异常时，直接发送完整盘面
    if event in ["workflow_dispatch", "manual"] or (result['up'] == 0 and result['down'] == 0):
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
        # 上涨预警
        up_level = up // INCREMENT_THRESHOLD
        if up >= UP_THRESHOLD and up_level > status["last_alert_up_level"]:
            alert += f"### **<font color=\"warning\">📈 上涨家数突破 {up_level * INCREMENT_THRESHOLD}</font>**\n"
            status["last_alert_up_level"] = up_level
            notify = True
        elif up < UP_THRESHOLD:
            status["last_alert_up_level"] = 0
        # 下跌预警
        down_level = down // INCREMENT_THRESHOLD
        if down >= DOWN_THRESHOLD and down_level > status["last_alert_down_level"]:
            alert += f"### **<font color=\"info\">📉 下跌家数突破 {down_level * INCREMENT_THRESHOLD}</font>**\n"
            status["last_alert_down_level"] = down_level
            notify = True
        elif down < DOWN_THRESHOLD:
            status["last_alert_down_level"] = 0
        if notify:
            msg = alert + "\n" + format_market_message(result)
            send_wechat(msg, key)
            save_status(status)
if __name__ == "__main__":
    main()
