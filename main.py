import os
import sys
import subprocess

# 自动安装缺失的库
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import requests
    import chinese_calendar
except ImportError:
    print("正在安装缺失的依赖库...")
    install('requests')
    install('chinesecalendar')
    import requests
    import chinese_calendar

import json
from datetime import datetime, time, date

# 预警阈值
UP_THRESHOLD = 3500
DOWN_THRESHOLD = 3500
INCREMENT_THRESHOLD = 250

def fetch_stock_counts():
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2",
        "secids": "1.000001,0.399001",
        "fields": "f1,f2,f3,f4,f6,f12,f13,f104,f105,f106",
        "ut": "b2884a393a59ad64002292a3e90d46a5"
    }
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64 ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        if not data or "data" not in data or "diff" not in data["data"]:
            return None
        diff = data["data"]["diff"]
        total_up, total_down, total_flat = 0, 0, 0
        for item in diff:
            total_up += item.get("f104", 0)
            total_down += item.get("f105", 0)
            total_flat += item.get("f106", 0)
        return {
            "up": total_up,
            "down": total_down,
            "flat": total_flat,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def is_trading_time(current_date):
    if current_date.weekday() >= 5: return False
    if chinese_calendar.is_holiday(current_date): return False
    now_time = datetime.now().time()
    return time(9, 15) <= now_time <= time(15, 0)

def send_wechat_notification(content, key):
    if not key: return
    if "qyapi.weixin.qq.com" in key and "?key=" in key:
        key = key.split("?key=")[1]
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        requests.post(url, json=payload, timeout=10 )
    except Exception as e:
        print(f"发送通知出错: {e}")

def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")
    current_date = date.today()
    
    if event_name in ["workflow_dispatch", "manual"]:
        result = fetch_stock_counts()
        if result:
            # 按照您的要求进行排版：涨 | 跌 | 平
            output = (
                f"涨: <font color=\"warning\">{result['up']}</font>  |  "
                f"跌: <font color=\"info\">{result['down']}</font>  |  "
                f"平: {result['flat']}\n"
                f"总计家数: {result['up'] + result['down'] + result['flat']}\n"
                f"-----------------------\n"
            )
            
            rules_text = (
                f"**运行规则 (手动模式)**\n"
                f"1. 抓取 A 股当前涨跌家数。\n"
                f"2. 非交易日显示上一个交易日数据。\n"
            )
            
            trading_day_info = ""
            if not is_trading_time(current_date):
                trading_day_info = f"提示: 今天 ({current_date.strftime('%Y-%m-%d')}) 是非交易日，显示上一个交易日数据。\n"
            
            footer = (
                f"{rules_text}"
                f"{trading_day_info}"
                f"查询时间: {result['date']}"
            )
            
            send_wechat_notification(f"{output}{footer}", os.environ.get("QYWECHAT_KEY"))
    
    elif event_name == "schedule":
        if not is_trading_time(current_date): return
        result = fetch_stock_counts()
        if result:
            up_count, down_count = result["up"], result["down"]
            msg = f"### A股情绪监测 ({result['date']})\n"
            notify = False
            if up_count >= UP_THRESHOLD and (up_count - UP_THRESHOLD) % INCREMENT_THRESHOLD == 0:
                msg += f"> **上涨突破**: <font color=\"warning\">{up_count}</font> 家！\n"; notify = True
            if down_count >= DOWN_THRESHOLD and (down_count - DOWN_THRESHOLD) % INCREMENT_THRESHOLD == 0:
                msg += f"> **下跌突破**: <font color=\"info\">{down_count}</font> 家！\n"; notify = True
            if notify: send_wechat_notification(msg, os.environ.get("QYWECHAT_KEY"))

if __name__ == "__main__":
    main()
