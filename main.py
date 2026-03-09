import os
import sys
import subprocess
import json
from datetime import datetime, time, timedelta, timezone

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import requests
    import chinese_calendar
except ImportError:
    install("requests")
    install("chinesecalendar")
    import requests
    import chinese_calendar


def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)


UP_THRESHOLD = 3500
DOWN_THRESHOLD = 3500
INCREMENT_THRESHOLD = 250

STATE_FILE = "alert_state.json"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"down_level": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_market_data():

    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0"
    }

    result = {
        "up": 0,
        "down": 0,
        "flat": 0,
        "date": get_beijing_time().strftime("%Y-%m-%d %H:%M")
    }

    try:

        url = "https://push2ex.eastmoney.com/api/qt/pts/get"

        params = {
            "fields1": "f1,f2,f3",
            "fields2": "f1,f2,f3,f4",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }

        res = requests.get(url, params=params, headers=headers, timeout=10).json()

        if res and res.get("data"):

            data = res["data"]

            result["up"] = data.get("f2", 0)
            result["down"] = data.get("f3", 0)
            result["flat"] = data.get("f4", 0)

    except Exception as e:
        print("获取数据失败:", e)

    return result


def is_trading_time(now):

    if now.weekday() >= 5:
        return False

    if chinese_calendar.is_holiday(now.date()):
        return False

    now_time = now.time()

    return time(9, 15) <= now_time <= time(15, 0)


def send_wechat_notification(content, key):

    if not key:
        return

    if "qyapi.weixin.qq.com" in key and "?key=" in key:
        key = key.split("?key=")[1]

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("发送失败:", e)


def main():

    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")

    now_bj = get_beijing_time()

    wechat_key = os.environ.get("QYWECHAT_KEY")

    print("事件:", event_name)
    print("北京时间:", now_bj)

    result = fetch_market_data()

    print("上涨:", result["up"], "下跌:", result["down"])

    # 手动运行逻辑
    if event_name in ["workflow_dispatch", "manual"]:

        msg = (
            f"### A股行情\n"
            f"上涨: <font color=\"warning\">{result['up']}</font>\n"
            f"下跌: <font color=\"info\">{result['down']}</font>\n"
            f"平盘: {result['flat']}\n"
            f"时间: {result['date']}"
        )

        send_wechat_notification(msg, wechat_key)

    # 定时监控逻辑
    elif event_name == "schedule":

        if not is_trading_time(now_bj):
            print("非交易时间")
            return

        down = result["down"]

        state = load_state()

        last_level = state.get("down_level", 0)

        notify = False

        if down >= DOWN_THRESHOLD:

            current_level = (down - DOWN_THRESHOLD) // INCREMENT_THRESHOLD + 1

            if current_level != last_level:
                notify = True
                state["down_level"] = current_level

        else:

            if last_level != 0:
                state["down_level"] = 0

        if notify:

            msg = (
                f"### A股情绪监测\n"
                f"下跌家数: <font color=\"info\">{down}</font>\n"
                f"时间: {result['date']}"
            )

            send_wechat_notification(msg, wechat_key)

        save_state(state)


if __name__ == "__main__":
    main()
