"""
股票数据获取模块 - 使用AKShare作为主要数据源（更准确）
"""
import yfinance as yf
import akshare as ak
import pandas as pd
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

        if cache_key in self.cache:
            cache_time, cache_data = self.cache[cache_key]
            if datetime.now() - cache_time < timedelta(minutes=5):
                return cache_data

        def _fetch_data():
            if market == "CN":
                return self._get_cn_stock_data_akshare(symbol, period)
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

    def _get_cn_stock_data_akshare(self, symbol, period):
        """使用AKShare获取A股数据（更准确）"""
        try:
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
            days = period_days.get(period, 365)

            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq"
            )

            if df.empty:
                return None

            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high',
                '最低': 'low', '成交量': 'volume', '成交额': 'amount',
                '振幅': 'amplitude', '涨跌幅': 'pct_change', '涨跌额': 'change', '换手率': 'turnover'
            })

            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            return df

        except Exception as e:
            print(f"AKShare失败 {symbol}: {str(e)}")
            return self._get_cn_stock_data_yfinance(symbol, period)

    def _get_cn_stock_data_yfinance(self, symbol, period):
        """使用yfinance获取A股数据（备选）"""
        if '.' not in symbol:
            symbol_yf = f"{symbol}.SS"
            ticker = yf.Ticker(symbol_yf)
            data = ticker.history(period=period)
            if data.empty:
                symbol_yf = f"{symbol}.SZ"
                ticker = yf.Ticker(symbol_yf)
                data = ticker.history(period=period)
        else:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
        return data

    def get_stock_info(self, symbol, market="US"):
        """获取股票基本信息"""
        def _fetch_info():
            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
                return ticker.info
            elif market == "CN":
                name = CN_STOCK_NAMES_EXTENDED.get(symbol)
                if name:
                    return {'shortName': name, 'symbol': symbol}
                if '.' not in symbol:
                    ticker = yf.Ticker(f"{symbol}.SS")
                    info = ticker.info
                    if info and info.get('shortName'):
                        return info
                    ticker = yf.Ticker(f"{symbol}.SZ")
                    return ticker.info
                else:
                    ticker = yf.Ticker(symbol)
                    return ticker.info
            else:
                ticker = yf.Ticker(symbol)
                return ticker.info

        info = self._retry_with_backoff(_fetch_info)
        if info is None:
            return {}
        return info

    def get_stock_name(self, symbol, market="US"):
        """获取股票名称，优先使用映射表"""
        if market == "CN":
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return name
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
        """获取实时行情 - A股使用AKShare"""
        try:
            if market == "CN":
                try:
                    df = ak.stock_zh_a_spot_em()
                    stock_row = df[df['代码'] == symbol]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        return {
                            'symbol': symbol, 'name': row.get('名称', symbol),
                            'price': float(row.get('最新价', 0)), 'open': float(row.get('今开', 0)),
                            'high': float(row.get('最高', 0)), 'low': float(row.get('最低', 0)),
                            'volume': int(float(row.get('成交量', 0))),
                            'prev_close': float(row.get('昨收', 0)), 'change': float(row.get('涨跌幅', 0))
                        }
                except Exception as e:
                    print(f"AKShare实时行情失败: {e}")

                ticker = yf.Ticker(f"{symbol}.SS")
                hist = ticker.history(period="5d")
                info = ticker.info
                if not hist.empty:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else latest
                    return {
                        'symbol': symbol, 'name': info.get('shortName', symbol),
                        'price': latest['Close'], 'open': latest['Open'],
                        'high': latest['High'], 'low': latest['Low'],
                        'volume': latest['Volume'], 'prev_close': prev['Close'],
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
                        'symbol': symbol, 'name': info.get('shortName', symbol),
                        'price': latest['Close'], 'open': latest['Open'],
                        'high': latest['High'], 'low': latest['Low'],
                        'volume': latest['Volume'], 'prev_close': prev['Close'],
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
                        'symbol': symbol, 'name': info.get('shortName', symbol),
                        'price': latest['Close'], 'open': latest['Open'],
                        'high': latest['High'], 'low': latest['Low'],
                        'volume': latest['Volume'], 'prev_close': prev['Close'],
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
    '000027': '深圳能源', '600900': '长江电力', '601985': '中国核电'
}

POPULAR_US_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC']

POPULAR_CN_STOCKS = [
    {'code': '000001', 'name': '平安银行'}, {'code': '000002', 'name': '万科A'},
    {'code': '000858', 'name': '五粮液'}, {'code': '002594', 'name': '比亚迪'},
    {'code': '300750', 'name': '宁德时代'}, {'code': '600519', 'name': '贵州茅台'}
]
