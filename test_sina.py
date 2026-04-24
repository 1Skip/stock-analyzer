import requests
import json

# 测试新浪财经接口
symbol = "000027"
url = f"https://quotes.sina.cn/cn/api/quotes.php?symbol={symbol}&scale=240&ma=5&datalen=30"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# 测试实时行情
url2 = f"https://hq.sinajs.cn/list=sz{symbol}"
headers2 = {
    'Referer': 'https://finance.sina.com.cn',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    response = requests.get(url2, headers=headers2, timeout=5)
    print(f"\nRealtime Status: {response.status_code}")
    print(f"Realtime Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
