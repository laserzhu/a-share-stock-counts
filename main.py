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
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64 ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    result = {
        "up": 0, "down": 0, "flat": 0,
        "limit_up": 0, "limit_down": 0,
        "indices": [],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # 1. 尝试获取详细统计 (包含涨停、跌停)
    try:
        url_summary = "https://push2ex.eastmoney.com/api/qt/pts/get"
        params_summary = {
            "fields1": "f1,f2,f3",
            "fields2": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }
        res = requests.get(url_summary, params=params_summary, headers=headers, timeout=10 ).json()
        if res and res.get("data"):
            data = res["data"]
            result["up"] = data.get("f2", 0)
            result["down"] = data.get("f3", 0)
            result["flat"] = data.get("f4", 0)
            result["limit_up"] = data.get("f14", 0)
            result["limit_down"] = data.get("f15", 0)
    except Exception as e:
        print(f"获取详细统计失败: {e}")

    # 2. 如果上方数据为0（非交易日常见情况），尝试使用备用稳定接口获取基础涨跌家数
    if result["up"] == 0 and result["down"] == 0:
        try:
            url_backup = "https://push2.eastmoney.com/api/qt/ulist.np/get"
            params_backup = {
                "fltt": "2",
                "secids": "1.000001,0.399001",
                "fields": "f104,f105,f106",
                "ut": "b2884a393a59ad64002292a3e90d46a5"
            }
            res_bak = requests.get(url_backup, params=params_backup, headers=headers, timeout=10 ).json()
            if res_bak and "data" in res_bak and "diff" in res_bak["data"]:
                for item in res_bak["data"]["diff"]:
                    result["up"] += item.get("f104", 0)
                    result["down"] += item.get("f105", 0)
                    result["flat"] += item.get("f106", 0)
        except Exception as e:
            print(f"获取备用数据失败: {e}")

    # 3. 获取指数行情
    try:
        url_index = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params_index = {
            "fltt": "2",
            "secids": "1.000001,0.399001,0.399006,1.000688",
            "fields": "f2,f3,f12,f14",
            "ut": "b2884a393a59ad64002292a3e90d46a5"
        }
        res_index = requests.get(url_index, params=params_index, headers=headers, timeout=10 ).json()
        if res_index and "data" in res_index and "diff" in res_index["data"]:
            for idx in res_index["data"]["diff"]:
                result["indices"].append({
                    "name": idx.get("f14"),
                    "price": idx.get("f2"),
                    "pct": idx.get("f3")
                })
    except Exception as e:
        print(f"获取指数行情失败: {e}")
                
    return result

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
    wechat_key = os.environ.get("QYWECHAT_KEY")
    
    result = fetch_market_data()
    
    if event_name in ["workflow_dispatch", "manual"]:
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
            color = "warning" if (idx['pct'] or 0) > 0 else "info" if (idx['pct'] or 0) < 0 else "comment"
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
        
        send_wechat_notification(f"{output}{index_text}{footer}", wechat_key)
    
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
            if notify: send_wechat_notification(msg, wechat_key)

if __name__ == "__main__":
    main()
