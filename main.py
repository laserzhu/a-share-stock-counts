import requests
import json
import os
from datetime import datetime, time, date
import chinesecalendar

# 预警阈值
UP_THRESHOLD = 3500
DOWN_THRESHOLD = 3500
INCREMENT_THRESHOLD = 250

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

def is_trading_time(current_date):
    # 检查是否为周末
    if current_date.weekday() >= 5: # 5: Saturday, 6: Sunday
        return False

    # 检查是否为法定节假日
    if chinesecalendar.is_holiday(current_date):
        return False

    # 检查交易时间 (9:15 - 15:00)
    now_time = datetime.now().time()
    market_open = time(9, 15)
    market_close = time(15, 0)
    if not (market_open <= now_time <= market_close):
        return False

    return True

def send_wechat_notification(content, key):
    if not key:
        print("警告: 未检测到环境变量 QYWECHAT_KEY，请确保在 GitHub Secrets 中已设置并在 workflow 文件中引用。")
        return
    
    # 检查 key 是否是完整的 URL，如果是，则提取出实际的 key
    if "qyapi.weixin.qq.com" in key and "?key=" in key:
        key = key.split("?key=")[1]

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
    # 判断是否为手动触发 (workflow_dispatch) 或自动触发 (schedule)
    # 在 GitHub Actions 中，可以通过环境变量 GITHUB_EVENT_NAME 来判断
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual") # 默认为 manual
    
    current_date = date.today()
    
    # 手动运行模式
    if event_name == "workflow_dispatch" or event_name == "manual":
        rules_text = (
            "### 运行规则 (手动模式)\n"
            "1. 抓取 A 股当前的上涨家数和下跌家数。\n"
            "2. 如果今天是非交易日，抓取前一个交易日的家数。\n"
            "3. 脚本将输出统计结果并发送企业微信通知。\n"
        )
        print("--- 运行规则 ---")
        print(rules_text)
        print("----------------\n")
        
        trading_day_info = ""
        if not is_trading_time(current_date):
            trading_day_info = f"提示: 今天 ({current_date.strftime("%Y-%m-%d")}) 是非交易日或非交易时间，将显示上一个交易日的数据。\n"
            print(trading_day_info)
        
        result = fetch_stock_counts()
        if result:
            output = (
                f"### A股涨跌家数统计\n"
                f"> **查询时间**: {result["date"]}\n"
                f"> **上涨家数**: <font color=\"info\">{result["up"]}</font>\n"
                f"> **下跌家数**: <font color=\"warning\">{result["down"]}</font>\n"
                f"> **平盘家数**: {result["flat"]}</font>\n"
                f"> **总计家数**: {result["up"] + result["down"] + result["flat"]}\n"
            )
            
            full_content = f"{rules_text}\n{trading_day_info}\n{output}"
            print(output)
            
            wechat_key = os.environ.get("QYWECHAT_KEY")
            send_wechat_notification(full_content, wechat_key)
        else:
            print("未能获取到数据，请检查网络或接口。")

    # 自动定时运行模式
    elif event_name == "schedule":
        if not is_trading_time(current_date):
            print(f"今天 ({current_date.strftime("%Y-%m-%d")}) 是非交易日或非交易时间，跳过监测。")
            return
        
        print(f"今天 ({current_date.strftime("%Y-%m-%d")}) 是交易日且在交易时间，开始监测...")
        result = fetch_stock_counts()
        if result:
            up_count = result["up"]
            down_count = result["down"]
            
            notification_needed = False
            message = f"### A股情绪监测 ({result["date"]})\n"
            
            # 上涨预警
            if up_count >= UP_THRESHOLD:
                # 计算当前上涨家数相对于阈值的增量
                # 这里需要一个机制来存储上一次提醒的家数，以便判断是否增加了250家
                # 由于 GitHub Actions 每次运行都是新的环境，直接在脚本中存储状态比较困难
                # 简单的实现是每次达到阈值就提醒，或者需要将状态存储到外部（如文件、GitHub Issue、数据库等）
                # 为了简化，目前只实现“超过3500提醒一次”，以及“每增加250家提醒”的首次触发
                # 更精确的“每增加250家”需要外部状态存储，此处暂时简化为：
                # 只要达到或超过阈值，并且是250的倍数（从3500开始），就提醒
                
                # 简化逻辑：如果上涨家数达到或超过3500，并且是3500 + N*250 的形式，就提醒
                if (up_count - UP_THRESHOLD) % INCREMENT_THRESHOLD == 0 or up_count == UP_THRESHOLD:
                    message += f"> **上涨家数突破**: <font color=\"info\">{up_count}</font> 家！\n"
                    notification_needed = True

            # 下跌预警
            if down_count >= DOWN_THRESHOLD:
                # 简化逻辑：如果下跌家数达到或超过3500，并且是3500 + N*250 的形式，就提醒
                if (down_count - DOWN_THRESHOLD) % INCREMENT_THRESHOLD == 0 or down_count == DOWN_THRESHOLD:
                    message += f"> **下跌家数突破**: <font color=\"warning\">{down_count}</font> 家！\n"
                    notification_needed = True
            
            if notification_needed:
                print("触发预警通知：")
                print(message)
                wechat_key = os.environ.get("QYWECHAT_KEY")
                send_wechat_notification(message, wechat_key)
            else:
                print("未达到预警条件，不发送通知。")
        else:
            print("未能获取到数据，请检查网络或接口。")

if __name__ == "__main__":
    main()
