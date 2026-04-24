"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
使用新浪财经作为主要A股数据源（国内访问快且稳定）
"""
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import random


class StockDataFetcher:
    """股票数据获取器 - 带重试机制"""

    def __init__(self):
        self.cache = {}
        self.max_retries = 3
        self.retry_delay = 1

    def _retry_with_backoff(self, func, *args, **kwargs):
        """带指数退避的重试机制"""
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                    return result
            except Exception as e:
                print(f"尝试 {attempt + 1}/{self.max_retries} 失败: {str(e)}")

            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
        return None

    def get_stock_data(self, symbol, period="1y", interval="1d", market="US"):
        """获取股票历史数据 - 带重试机制"""
        cache_key = f"{symbol}_{period}_{interval}_{market}"

        # 检查缓存，但缩短缓存时间到1分钟
        if cache_key in self.cache:
            cache_time, cache_data = self.cache[cache_key]
            if datetime.now() - cache_time < timedelta(minutes=1):
                return cache_data

        def _fetch_data():
            if market == "CN":
                # A股优先使用新浪财经
                return self._get_cn_stock_data_sina(symbol, period)
            elif market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
                return ticker.history(period=period, interval=interval)
            else:
                ticker = yf.Ticker(symbol)
                return ticker.history(period=period, interval=interval)

        data = self._retry_with_backoff(_fetch_data)

        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            print(f"未找到股票 {symbol} 的数据")
            return None

        if isinstance(data, pd.DataFrame):
            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

        self.cache[cache_key] = (datetime.now(), data)
        return data

    def _get_cn_stock_data_sina(self, symbol, period):
        """使用新浪财经获取A股数据（国内访问最快）"""
        try:
            # 转换period为天数
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
            days = period_days.get(period, 365)

            # 新浪财经接口
            url = f"https://quotes.sina.cn/cn/api/quotes.php?symbol={symbol}&scale=240&ma=5&datalen={days}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                import json
                data = json.loads(response.text)

                if data and len(data) > 0:
                    df = pd.DataFrame(data)
                    df['date'] = pd.to_datetime(df['day'])
                    df.set_index('date', inplace=True)
                    df.rename(columns={
                        'open': 'open',
                        'high': 'high',
                        'low': 'low',
                        'close': 'close',
                        'volume': 'volume'
                    }, inplace=True)
                    return df

            # 如果新浪财经失败，使用yfinance备选
            return self._get_cn_stock_data_yfinance(symbol, period)

        except Exception as e:
            print(f"新浪财经失败 {symbol}: {str(e)}")
            return self._get_cn_stock_data_yfinance(symbol, period)

    def _get_cn_stock_data_yfinance(self, symbol, period):
        """使用yfinance获取A股数据（备选）"""
        try:
            if '.' not in symbol:
                # 上海交易所
                symbol_yf = f"{symbol}.SS"
                ticker = yf.Ticker(symbol_yf)
                data = ticker.history(period=period)

                if data.empty:
                    # 深圳交易所
                    symbol_yf = f"{symbol}.SZ"
                    ticker = yf.Ticker(symbol_yf)
                    data = ticker.history(period=period)
            else:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period=period)

            return data
        except Exception as e:
            print(f"yfinance获取失败 {symbol}: {str(e)}")
            return None

    def get_stock_info(self, symbol, market="US"):
        """获取股票基本信息"""
        # A股直接返回映射表中的名称
        if market == "CN":
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return {'shortName': name, 'symbol': symbol}

        def _fetch_info():
            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
                return ticker.info
            else:
                ticker = yf.Ticker(symbol)
                return ticker.info

        info = self._retry_with_backoff(_fetch_info)
        if info is None:
            return {'shortName': symbol, 'symbol': symbol}
        return info

    def get_stock_name(self, symbol, market="US"):
        """获取股票名称，A股优先从新浪财经实时获取"""
        if market == "CN":
            # 优先从新浪财经实时获取（最准确）
            try:
                # 先尝试深圳交易所
                url = f"https://hq.sinajs.cn/list=sz{symbol}"
                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    import re
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 1 and data[0]:
                            return data[0]

                # 再尝试上海交易所
                url = f"https://hq.sinajs.cn/list=sh{symbol}"
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    import re
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 1 and data[0]:
                            return data[0]
            except:
                pass

            # 备选：查映射表
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return name

            return symbol

        # 美股/港股使用yfinance
        try:
            info = self.get_stock_info(symbol, market)
            if info:
                name = info.get('shortName') or info.get('longName')
                if name:
                    return name
        except:
            pass
        return symbol

    def get_realtime_quote(self, symbol, market="US"):
        """获取实时行情 - A股使用新浪财经"""
        try:
            if market == "CN":
                # 使用新浪财经实时行情
                url = f"https://hq.sinajs.cn/list=sz{symbol}"
                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                response = requests.get(url, headers=headers, timeout=5)

                if response.status_code == 200:
                    import re
                    content = response.text
                    match = re.search(r'"([^"]*)"', content)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 33:
                            return {
                                'symbol': symbol,
                                'name': data[0],
                                'price': float(data[3]),
                                'open': float(data[1]),
                                'high': float(data[4]),
                                'low': float(data[5]),
                                'volume': int(float(data[8]) / 100),  # 转换为手
                                'prev_close': float(data[2]),
                                'change': float(data[32])  # 涨跌幅
                            }

                # 如果深圳失败，尝试上海
                url = f"https://hq.sinajs.cn/list=sh{symbol}"
                response = requests.get(url, headers=headers, timeout=5)

                if response.status_code == 200:
                    import re
                    content = response.text
                    match = re.search(r'"([^"]*)"', content)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 33:
                            return {
                                'symbol': symbol,
                                'name': data[0],
                                'price': float(data[3]),
                                'open': float(data[1]),
                                'high': float(data[4]),
                                'low': float(data[5]),
                                'volume': int(float(data[8]) / 100),
                                'prev_close': float(data[2]),
                                'change': float(data[32])
                            }

                # 备选：使用yfinance
                ticker = yf.Ticker(f"{symbol}.SS")
                hist = ticker.history(period="5d")
                info = ticker.info

                if not hist.empty:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else latest
                    return {
                        'symbol': symbol,
                        'name': info.get('shortName', symbol),
                        'price': latest['Close'],
                        'open': latest['Open'],
                        'high': latest['High'],
                        'low': latest['Low'],
                        'volume': latest['Volume'],
                        'prev_close': prev['Close'],
                        'change': ((latest['Close'] - prev['Close']) / prev['Close'] * 100)
                    }

            elif market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
                hist = ticker.history(period="5d")
                info = ticker.info
                if not hist.empty:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else latest
                    return {
                        'symbol': symbol,
                        'name': info.get('shortName', symbol),
                        'price': latest['Close'],
                        'open': latest['Open'],
                        'high': latest['High'],
                        'low': latest['Low'],
                        'volume': latest['Volume'],
                        'prev_close': prev['Close'],
                        'change': ((latest['Close'] - prev['Close']) / prev['Close'] * 100)
                    }
            else:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                info = ticker.info
                if not hist.empty:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else latest
                    return {
                        'symbol': symbol,
                        'name': info.get('shortName', symbol),
                        'price': latest['Close'],
                        'open': latest['Open'],
                        'high': latest['High'],
                        'low': latest['Low'],
                        'volume': latest['Volume'],
                        'prev_close': prev['Close'],
                        'change': ((latest['Close'] - prev['Close']) / prev['Close'] * 100)
                    }

        except Exception as e:
            print(f"获取实时行情失败 {symbol}: {str(e)}")
        return None


# 股票名称映射表
CN_STOCK_NAMES_EXTENDED = {
    '000001': '平安银行', '000002': '万科A', '000858': '五粮液', '002594': '比亚迪',
    '300750': '宁德时代', '600519': '贵州茅台', '601398': '工商银行', '601857': '中国石油',
    '601318': '中国平安', '601012': '隆基绿能', '600036': '招商银行', '000333': '美的集团',
    '002415': '海康威视', '600276': '恒瑞医药', '600887': '伊利股份', '601888': '中国中免',
    '002714': '牧原股份', '300059': '东方财富', '000725': '京东方A', '601288': '农业银行',
    '601939': '建设银行', '601988': '中国银行', '601628': '中国人寿', '000568': '泸州老窖',
    '000651': '格力电器', '002475': '立讯精密', '603501': '韦尔股份', '603019': '中科曙光',
    '600570': '恒生电子', '002230': '科大讯飞', '603986': '兆易创新', '300014': '亿纬锂能',
    '300433': '蓝思科技', '000063': '中兴通讯', '600009': '上海机场', '600048': '保利发展',
    '600309': '万华化学', '601066': '中信建投', '601211': '国泰君安', '600030': '中信证券',
    '000027': '深圳能源', '600900': '长江电力', '601985': '中国核电', '603920': '世运电路'
}

POPULAR_US_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC']

POPULAR_CN_STOCKS = [
    {'code': '000001', 'name': '平安银行'}, {'code': '000002', 'name': '万科A'},
    {'code': '000858', 'name': '五粮液'}, {'code': '002594', 'name': '比亚迪'},
    {'code': '300750', 'name': '宁德时代'}, {'code': '600519', 'name': '贵州茅台'},
    {'code': '601398', 'name': '工商银行'}, {'code': '601857', 'name': '中国石油'},
    {'code': '601318', 'name': '中国平安'}, {'code': '601012', 'name': '隆基绿能'},
    {'code': '600036', 'name': '招商银行'}, {'code': '000333', 'name': '美的集团'},
    {'code': '002415', 'name': '海康威视'}, {'code': '600276', 'name': '恒瑞医药'},
    {'code': '600887', 'name': '伊利股份'}, {'code': '601888', 'name': '中国中免'},
    {'code': '002714', 'name': '牧原股份'}, {'code': '300059', 'name': '东方财富'},
    {'code': '000725', 'name': '京东方A'}, {'code': '601288', 'name': '农业银行'},
    {'code': '601939', 'name': '建设银行'}, {'code': '601988', 'name': '中国银行'},
    {'code': '601628', 'name': '中国人寿'}, {'code': '000568', 'name': '泸州老窖'},
    {'code': '000651', 'name': '格力电器'}, {'code': '002475', 'name': '立讯精密'},
    {'code': '603501', 'name': '韦尔股份'}, {'code': '603019', 'name': '中科曙光'}
]
