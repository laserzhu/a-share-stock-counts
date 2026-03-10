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
    # 1. 获取涨跌分布数据 (上涨/下跌/平盘)
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "secids": "1.000001,0.399001",
            "fields": "f104,f105,f106",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }
        res = requests.get(url, params=params, headers=headers, timeout=5).json()
        if res and "data" in res and "diff" in res["data"]:
            for i in res["data"]["diff"]:
                result["up"] += i.get("f104", 0)
                result["down"] += i.get("f105", 0)
                result["flat"] += i.get("f106", 0)
    except Exception as e:
        print("涨跌分布接口失败:", e)
    # 2. 获取涨跌停数据
    try:
        url = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
        params = {
            "page": "1",
            "limit": "1",
            "field": "199112,10,9001,330329,330325",
            "filter": "HS,GEM2STAR",
            "order_field": "330329",
            "order_type": "0"
        }
        res = requests.get(url, params=params, headers=headers, timeout=5).json()
        if res:
            result["limit_up"] = res.get("data", {}).get("limit_up_count", {}).get("today", {}).get("num", 0)
            result["limit_down"] = res.get("data", {}).get("limit_down_count", {}).get("today", {}).get("num", 0)
    except Exception as e:
        print("涨跌停接口失败:", e)
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
        # 每次直接发送完整消息，无预警逻辑
        msg = format_market_message(result)
        send_wechat(msg, key)
if __name__ == "__main__":
    main()
