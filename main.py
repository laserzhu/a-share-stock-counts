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

def fetch_market_data():
    # 1. 获取涨跌家数统计 (包含涨停、跌停家数)
    url_summary = "https://push2ex.eastmoney.com/api/qt/pts/get"
    params_summary = {
        "fields1": "f1,f2,f3",
        "fields2": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15",
        "ut": "b2884a393a59ad64002292a3e90d46a5"
    }
    
    # 2. 获取指数行情
    url_index = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params_index = {
        "fltt": "2",
        "secids": "1.000001,0.399001,0.399006,1.000688", # 沪指, 深指, 创指, 科创50
        "fields": "f2,f3,f12,f14",
        "ut": "b2884a393a59ad64002292a3e90d46a5"
    }
    
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64 ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 获取全市场概况
        res_summary = requests.get(url_summary, params=params_summary, headers=headers, timeout=10).json()
        # 获取指数行情
        res_index = requests.get(url_index, params=params_index, headers=headers, timeout=10).json()
        
        if not res_summary or "data" not in res_summary:
            return None
            
        data = res_summary["data"]
        # f2: 上涨, f3: 下跌, f4: 平盘, f14: 涨停, f15: 跌停
        total_up = data.get("f2", 0)
        total_down = data.get("f3", 0)
        total_flat = data.get("f4", 0)
        total_limit_up = data.get("f14", 0)
        total_limit_down = data.get("f15", 0)
            
        indices = []
        if res_index and "data" in res_index and "diff" in res_index["data"]:
            for idx in res_index["data"]["diff"]:
                indices.append({
                    "name": idx.get("f14"),
                    "price": idx.get("f2"),
                    "pct": idx.get("f3")
                })
                
        return {
            "up": total_up,
            "down": total_down,
            "flat": total_flat,
            "limit_up": total_limit_up,
            "limit_down": total_limit_down,
            "indices": indices,
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
        result = fetch_market_data()
        if result:
            # 1. 涨跌统计
            output = (
                f"涨: <font color=\"warning\">{result['up']}</font>  |  "
                f"跌: <font color=\"info\">{result['down']}</font>  |  "
                f"平: {result['flat']}\n"
                f"总计家数: {result['up'] + result['down'] + result['flat']}\n"
                f"涨停: <font color=\"warning\">{result['limit_up']}</font>  |  "
                f"跌停: <font color=\"info\">{result['limit_down']}</font>\n"
                f"-----------------------\n"
            )
            
            # 2. 指数行情
            index_text = ""
            for idx in result['indices']:
                color = "warning" if idx['pct'] > 0 else "info" if idx['pct'] < 0 else "comment"
                index_text += f"{idx['name']}: {idx['price']} (<font color=\"{color}\">{idx['pct']}%</font>)\n"
            index_text += f"-----------------------\n"
            
            # 3. 运行规则和页脚
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
            
            send_wechat_notification(f"{output}{index_text}{footer}", os.environ.get("QYWECHAT_KEY"))
    
    elif event_name == "schedule":
        if not is_trading_time(current_date): return
        result = fetch_market_data()
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
