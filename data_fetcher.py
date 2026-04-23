"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
"""
import yfinance as yf
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


class StockDataFetcher:
    """股票数据获取器"""

    def __init__(self):
        self.cache = {}

    def get_stock_data(self, symbol, period="1y", interval="1d", market="US"):
        """
        获取股票历史数据

        参数:
            symbol: 股票代码
            period: 时间周期 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 时间间隔 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            market: 市场 (US-美股, CN-A股, HK-港股)
        """
        cache_key = f"{symbol}_{period}_{interval}_{market}"

        if cache_key in self.cache:
            cache_time, cache_data = self.cache[cache_key]
            # 缓存5分钟
            if datetime.now() - cache_time < timedelta(minutes=5):
                return cache_data

        try:
            if market == "CN":
                # A股使用akshare获取数据
                data = self._get_cn_stock_data(symbol, period)
            elif market == "HK":
                # 港股使用yfinance
                ticker = yf.Ticker(f"{symbol}.HK")
                data = ticker.history(period=period, interval=interval)
            else:
                # 美股使用yfinance
                ticker = yf.Ticker(symbol)
                data = ticker.history(period=period, interval=interval)

            if data.empty:
                print(f"未找到股票 {symbol} 的数据")
                return None

            # 标准化列名
            data.columns = [col.lower().replace(' ', '_') for col in data.columns]

            # 缓存数据
            self.cache[cache_key] = (datetime.now(), data)

            return data

        except Exception as e:
            print(f"获取股票数据失败 {symbol}: {str(e)}")
            return None

    def _get_cn_stock_data(self, symbol, period):
        """获取A股数据"""
        # 转换period为start_date
        end_date = datetime.now()

        if period == "1d":
            start_date = end_date - timedelta(days=1)
        elif period == "5d":
            start_date = end_date - timedelta(days=5)
        elif period == "1mo":
            start_date = end_date - timedelta(days=30)
        elif period == "3mo":
            start_date = end_date - timedelta(days=90)
        elif period == "6mo":
            start_date = end_date - timedelta(days=180)
        elif period == "1y":
            start_date = end_date - timedelta(days=365)
        elif period == "2y":
            start_date = end_date - timedelta(days=730)
        elif period == "5y":
            start_date = end_date - timedelta(days=1825)
        else:
            start_date = end_date - timedelta(days=365)

        # 使用akshare获取A股历史数据
        try:
            # 尝试获取个股数据
            data = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                       start_date=start_date.strftime("%Y%m%d"),
                                       end_date=end_date.strftime("%Y%m%d"),
                                       adjust="qfq")  # 前复权

            if data is not None and not data.empty:
                # 重命名列以匹配标准格式
                data = data.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '振幅': 'amplitude',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '换手率': 'turnover'
                })
                data['date'] = pd.to_datetime(data['date'])
                data.set_index('date', inplace=True)
                return data
        except Exception as e:
            print(f"akshare获取数据失败，尝试yfinance: {e}")

        # 备用：使用yfinance (A股需要加后缀)
        if '.' not in symbol:
            symbol_yf = f"{symbol}.SS"  # 上海
            ticker = yf.Ticker(symbol_yf)
            data = ticker.history(period=period)
            if data.empty:
                symbol_yf = f"{symbol}.SZ"  # 深圳
                ticker = yf.Ticker(symbol_yf)
                data = ticker.history(period=period)
        else:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)

        return data

    def get_stock_info(self, symbol, market="US"):
        """获取股票基本信息"""
        try:
            if market == "CN":
                # A股信息
                try:
                    info = ak.stock_individual_info_em(symbol=symbol)
                    if info is not None and not info.empty:
                        return dict(zip(info['item'], info['value']))
                except:
                    pass

            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
            else:
                ticker = yf.Ticker(symbol)

            return ticker.info

        except Exception as e:
            print(f"获取股票信息失败 {symbol}: {str(e)}")
            return {}

    def get_realtime_quote(self, symbol, market="US"):
        """获取实时行情"""
        try:
            if market == "CN":
                # A股实时行情
                try:
                    data = ak.stock_zh_a_spot_em()
                    stock_data = data[data['代码'] == symbol]
                    if not stock_data.empty:
                        return {
                            'symbol': symbol,
                            'name': stock_data['名称'].values[0],
                            'price': float(stock_data['最新价'].values[0]),
                            'change': float(stock_data['涨跌幅'].values[0]),
                            'volume': float(stock_data['成交量'].values[0]),
                            'turnover': float(stock_data['成交额'].values[0]),
                            'high': float(stock_data['最高'].values[0]),
                            'low': float(stock_data['最低'].values[0]),
                            'open': float(stock_data['今开'].values[0]),
                            'prev_close': float(stock_data['昨收'].values[0])
                        }
                except Exception as e:
                    print(f"akshare实时行情失败: {e}")

            # 使用yfinance获取
            if market == "HK":
                ticker = yf.Ticker(f"{symbol}.HK")
            else:
                ticker = yf.Ticker(symbol)

            hist = ticker.history(period="1d")
            info = ticker.info

            if not hist.empty:
                latest = hist.iloc[-1]
                return {
                    'symbol': symbol,
                    'name': info.get('shortName', symbol),
                    'price': latest['Close'],
                    'open': latest['Open'],
                    'high': latest['High'],
                    'low': latest['Low'],
                    'volume': latest['Volume'],
                    'prev_close': info.get('previousClose', latest['Open']),
                    'change': ((latest['Close'] - info.get('previousClose', latest['Open']))
                               / info.get('previousClose', latest['Open']) * 100)
                }

        except Exception as e:
            print(f"获取实时行情失败 {symbol}: {str(e)}")

        return None

    def search_stock(self, keyword, market="CN"):
        """搜索股票"""
        try:
            if market == "CN":
                # A股搜索
                try:
                    data = ak.stock_zh_a_spot_em()
                    # 按代码或名称搜索
                    result = data[(data['代码'].str.contains(keyword)) |
                                  (data['名称'].str.contains(keyword))]
                    return result[['代码', '名称', '最新价', '涨跌幅']].head(10).to_dict('records')
                except Exception as e:
                    print(f"搜索失败: {e}")

            return []

        except Exception as e:
            print(f"搜索股票失败: {str(e)}")
            return []
