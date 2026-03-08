import requests
import json
import os
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
    now = datetime.now()
    if now.weekday() >= 5: # 5: Saturday, 6: Sunday
        return False
    return True

def send_wechat_notification(content, key):
    if not key:
        print("警告: 未检测到环境变量 QYWECHAT_KEY，请确保在 GitHub Secrets 中已设置并在 workflow 文件中引用。")
        return
    
    print(f"正在尝试发送企业微信通知，Key 长度: {len(key)}")
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if response.status_code == 200:
            print("企业微信通知发送成功。")
            print(f"响应内容: {response.text}")
        else:
            print(f"企业微信通知发送失败，状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        print(f"发送通知时出错: {e}")

def main():
    rules = (
        "### 运行规则\n"
        "1. 抓取 A 股当前的上涨家数和下跌家数。\n"
        "2. 如果今天是非交易日，抓取前一个交易日的家数。\n"
        "3. 脚本将输出统计结果并发送企业微信通知。\n"
    )
    print("--- 运行规则 ---")
    print(rules)
    print("----------------\n")
    
    trading_day = is_trading_day()
    trading_info = ""
    if not trading_day:
        trading_info = f"提示: 今天 ({datetime.now().strftime('%Y-%m-%d')}) 是非交易日，将显示上一个交易日的数据。\n"
        print(trading_info)
    
    result = fetch_stock_counts()
    if result:
        output = (
            f"### A股涨跌家数统计\n"
            f"> **查询时间**: {result['date']}\n"
            f"> **上涨家数**: <font color=\"info\">{result['up']}</font>\n"
            f"> **下跌家数**: <font color=\"warning\">{result['down']}</font>\n"
            f"> **平盘家数**: {result['flat']}\n"
            f"> **总计家数**: {result['up'] + result['down'] + result['flat']}\n"
        )
        
        full_content = f"{rules}\n{trading_info}\n{output}"
        print(output)
        
        # 从环境变量获取企业微信 Key
        wechat_key = os.environ.get("QYWECHAT_KEY")
        send_wechat_notification(full_content, wechat_key)
    else:
        print("未能获取到数据，请检查网络或接口。")

if __name__ == "__main__":
    main()
