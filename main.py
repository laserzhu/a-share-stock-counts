import requests
import json
from datetime import datetime

def fetch_stock_counts():
    # 东方财富 API 接口
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2",
        "secids": "1.000001,0.399001",
        "fields": "f1,f2,f3,f4,f6,f12,f13,f104,f105,f106",
        "ut": "b2884a393a59ad64002292a3e90d46a5"
    }
    headers = {
        "Referer": "https://data.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if not data or "data" not in data or "diff" not in data["data"]:
            return None
        
        diff = data["data"]["diff"]
        # f104: 涨, f105: 跌, f106: 平
        
        total_up = 0
        total_down = 0
        total_flat = 0
        
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

def is_trading_day():
    # 简单的交易日判断：周六周日为非交易日
    # 实际情况还需考虑法定节假日，但通常 API 在非交易日会返回上一个交易日的数据
    now = datetime.now()
    if now.weekday() >= 5: # 5: Saturday, 6: Sunday
        return False
    return True

def main():
    print("--- 运行规则 ---")
    print("1. 抓取 A 股当前的上涨家数和下跌家数。")
    print("2. 如果今天是非交易日，抓取前一个交易日的家数。")
    print("3. 脚本将输出统计结果。")
    print("----------------\n")
    
    trading_day = is_trading_day()
    if not trading_day:
        print(f"提示: 今天 ({datetime.now().strftime('%Y-%m-%d')}) 是非交易日，将显示上一个交易日的数据。\n")
    
    result = fetch_stock_counts()
    if result:
        print(f"查询时间: {result['date']}")
        print(f"上涨家数: {result['up']}")
        print(f"下跌家数: {result['down']}")
        print(f"平盘家数: {result['flat']}")
        print(f"总计家数: {result['up'] + result['down'] + result['flat']}")
    else:
        print("未能获取到数据，请检查网络或接口。")

if __name__ == "__main__":
    main()
