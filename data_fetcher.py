"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
使用 AKShare（同花顺/东方财富数据源）作为主要A股数据源
"""
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

# 绕过Windows系统代理（系统代理127.0.0.1:7897不可用时会导致所有数据源失败）
# requests 默认从 Windows 注册表读取代理配置，通过 monkey-patch 关闭
_original_session_init = requests.Session.__init__
def _patched_session_init(self):
    _original_session_init(self)
    self.trust_env = False
requests.Session.__init__ = _patched_session_init
import random
import io
import json
import os
from threading import Lock

# 尝试导入 AKShare，如果失败则使用备选方案
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("AKShare 导入失败，将使用 yfinance 作为备选")


class StockDataFetcher:
    """股票数据获取器 - 带重试机制、离线模式、健康检查"""

    # 类级别的请求锁，防止重复请求
    _request_locks = {}
    _lock_mutex = Lock()

    # 数据源健康状态缓存
    _health_status = {
        'akshare': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'sina': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'yfinance': {'healthy': True, 'last_check': None, 'fail_count': 0}
    }

    # 全市场快照缓存（避免每次获取单只股票名称/行情都下载5000+行）
    _spot_cache = None
    _spot_cache_time = None
    _spot_cache_ttl = timedelta(seconds=60)  # 60秒内复用

    # 离线数据缓存文件路径
    _offline_cache_file = os.path.join(os.path.dirname(__file__), '.stock_cache.json')

    def __init__(self):
        self.cache = {}
        self.max_retries = 3
        self.retry_delay = 1
        # 用户手动指定的优先数据源
        self.preferred_source = os.environ.get('STOCK_DATA_SOURCE', 'auto')

    def _get_request_lock(self, key):
        """获取请求锁，防止重复请求"""
        with self._lock_mutex:
            if key not in self._request_locks:
                self._request_locks[key] = Lock()
            return self._request_locks[key]

    def _update_health_status(self, source, success):
        """更新数据源健康状态"""
        status = self._health_status[source]
        status['last_check'] = datetime.now().isoformat()

        if success:
            status['fail_count'] = max(0, status['fail_count'] - 1)
            status['healthy'] = True
        else:
            status['fail_count'] += 1
            # 连续失败3次标记为不健康
            if status['fail_count'] >= 3:
                status['healthy'] = False

    def check_health(self):
        """检查各数据源健康状态"""
        return self._health_status.copy()

    @classmethod
    def _get_spot_snapshot(cls):
        """获取A股全市场快照（带缓存，60秒内复用，避免重复下载5000+条）"""
        now = datetime.now()
        if cls._spot_cache is not None and cls._spot_cache_time is not None:
            if now - cls._spot_cache_time < cls._spot_cache_ttl:
                return cls._spot_cache
        if AKSHARE_AVAILABLE:
            try:
                cls._spot_cache = ak.stock_zh_a_spot_em()
                cls._spot_cache_time = now
                return cls._spot_cache
            except Exception:
                return None
        return None

    def _retry_with_backoff(self, func, source_name, *args, **kwargs):
        """带指数退避和智能重试间隔的重试机制"""
        # 如果数据源不健康，检查是否应该尝试恢复
        if source_name in self._health_status:
            status = self._health_status[source_name]
            if not status['healthy']:
                # 如果距上次检查超过5分钟，尝试恢复（重置健康状态尝试一次）
                last_check = status.get('last_check')
                if last_check:
                    try:
                        last_check_time = datetime.fromisoformat(last_check)
                        if datetime.now() - last_check_time > timedelta(minutes=5):
                            print(f"{source_name} 离线超5分钟，尝试恢复检查...")
                            status['healthy'] = True
                            status['fail_count'] = 0
                    except (ValueError, TypeError):
                        status['healthy'] = True
                        status['fail_count'] = 0
                else:
                    # 从未检查过，允许首次尝试
                    pass
            if not status['healthy']:
                fail_count = status['fail_count']
                # 随着失败次数增加，跳过更多尝试
                if fail_count > 5 and random.random() < 0.5:
                    print(f"{source_name} 数据源暂时跳过（连续失败{fail_count}次）")
                    return None

        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                    self._update_health_status(source_name, True)
                    return result
            except Exception as e:
                print(f"{source_name} 尝试 {attempt + 1}/{self.max_retries} 失败: {str(e)}")
                self._update_health_status(source_name, False)

            if attempt < self.max_retries - 1:
                # 智能退避：失败次数越多，等待越长
                base_delay = self.retry_delay * (2 ** attempt)
                fail_penalty = min(self._health_status[source_name]['fail_count'] * 2, 10)
                delay = base_delay + fail_penalty + random.uniform(0, 0.5)
                time.sleep(delay)
        return None

    def _save_offline_cache(self, symbol, data):
        """保存离线缓存数据"""
        try:
            cache_data = {}
            if os.path.exists(self._offline_cache_file):
                with open(self._offline_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

            # 只保存最近20个股票
            if len(cache_data) >= 20:
                # 删除最早的条目
                oldest_key = min(cache_data.keys(), key=lambda k: cache_data[k].get('timestamp', 0))
                del cache_data[oldest_key]

            cache_data[symbol] = {
                'timestamp': datetime.now().isoformat(),
                'data': data.to_json(orient='split', date_format='iso') if isinstance(data, pd.DataFrame) else data
            }

            with open(self._offline_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, default=str)
        except Exception as e:
            print(f"保存离线缓存失败: {str(e)}")

    def _load_offline_cache(self, symbol, max_age_hours=24):
        """加载离线缓存数据"""
        try:
            if not os.path.exists(self._offline_cache_file):
                return None

            try:
                with open(self._offline_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            except json.JSONDecodeError:
                # 缓存文件损坏，删除后重建
                os.remove(self._offline_cache_file)
                return None

            if symbol not in cache_data:
                return None

            cached = cache_data[symbol]
            cached_time = datetime.fromisoformat(cached['timestamp'])
            age = datetime.now() - cached_time

            if age > timedelta(hours=max_age_hours):
                return None

            # 恢复DataFrame（新格式用json/orient='split'保留index类型，旧格式兼容from_dict）
            raw = cached['data']
            if isinstance(raw, str):
                df = pd.read_json(io.StringIO(raw), orient='split')
            else:
                df = pd.DataFrame.from_dict(raw)
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df = df.set_index('date')
            # 确保index为DatetimeIndex（兼容旧缓存字符串index）
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            df.attrs['data_source'] = f"离线缓存 ({age.days}天{age.seconds//3600}小时前)"
            return df
        except Exception as e:
            print(f"加载离线缓存失败: {str(e)}")
            return None

    def get_stock_data(self, symbol, period="1y", interval="1d", market="US", use_cache=True):
        """获取股票历史数据 - 带重试机制、数据源追踪、离线模式"""
        cache_key = f"{symbol}_{period}_{interval}_{market}"

        # 使用锁防止重复请求
        lock = self._get_request_lock(cache_key)
        if not lock.acquire(blocking=False):
            # 如果锁被占用，等待并返回缓存
            lock.acquire()
            lock.release()
            if cache_key in self.cache:
                _, result, source = self.cache[cache_key]
                if isinstance(result, pd.DataFrame):
                    result.attrs['data_source'] = source
                return result
        lock.release()

        with lock:
            # 检查内存缓存
            if use_cache and cache_key in self.cache:
                cache_time, cache_data, cache_source = self.cache[cache_key]
                if datetime.now() - cache_time < timedelta(minutes=1):
                    if isinstance(cache_data, pd.DataFrame):
                        cache_data.attrs['data_source'] = cache_source
                    return cache_data

            result = None
            data_source = None
            offline_mode = False

            if market == "CN":
                # A股数据获取，按优先级尝试不同数据源（AKShare 优先，数据最全）
                sources_to_try = []

                # 根据用户偏好或健康状态决定顺序
                if self.preferred_source == 'akshare' or self.preferred_source == 'auto':
                    if self._health_status['akshare']['healthy']:
                        sources_to_try.append(('akshare', self._get_cn_stock_data_akshare))
                if self.preferred_source == 'sina' or self.preferred_source == 'auto':
                    if self._health_status['sina']['healthy']:
                        sources_to_try.append(('sina', self._get_cn_stock_data_sina_fallback))
                if self.preferred_source == 'yfinance' or self.preferred_source == 'auto':
                    if self._health_status['yfinance']['healthy']:
                        sources_to_try.append(('yfinance', self._get_cn_stock_data_yfinance))

                # 尝试所有数据源
                for source_name, source_func in sources_to_try:
                    try:
                        result = self._retry_with_backoff(source_func, source_name, symbol, period)
                        if result is not None and len(result) >= 10:
                            data_source = {
                                'akshare': 'AKShare（腾讯财经）',
                                'sina': '新浪财经',
                                'yfinance': 'Yahoo Finance'
                            }.get(source_name, source_name)
                            break
                    except Exception as e:
                        print(f"{source_name} 获取失败: {str(e)}")

                # 所有在线源失败，尝试离线缓存
                if result is None:
                    result = self._load_offline_cache(symbol)
                    if result is not None:
                        data_source = result.attrs.get('data_source', '离线缓存')
                        offline_mode = True

            elif market == "HK":
                result = self._retry_with_backoff(
                    lambda s, p: yf.Ticker(f"{s}.HK").history(period=p, interval=interval),
                    'yfinance', symbol, period
                )
                if result is not None and not result.empty:
                    data_source = "Yahoo Finance"
            else:
                result = self._retry_with_backoff(
                    lambda s, p: yf.Ticker(s).history(period=p, interval=interval),
                    'yfinance', symbol, period
                )
                if result is not None and not result.empty:
                    data_source = "Yahoo Finance"

            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                print(f"未找到股票 {symbol} 的数据")
                return None

            if isinstance(result, pd.DataFrame):
                result.columns = [col.lower().replace(' ', '_') for col in result.columns]
                # 添加数据源信息到DataFrame属性
                result.attrs['data_source'] = data_source or "未知"
                result.attrs['offline_mode'] = offline_mode

                # 保存到离线缓存
                if not offline_mode:
                    self._save_offline_cache(symbol, result)

            self.cache[cache_key] = (datetime.now(), result, data_source)
            return result

    def _get_cn_stock_data_akshare(self, symbol, period, **kwargs):
        """使用 AKShare 获取A股历史数据（腾讯财经数据源，直连稳定）"""
        if not AKSHARE_AVAILABLE:
            return None

        try:
            # 转换period为天数
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
            days = period_days.get(period, 365)

            # 判断交易所，构造 AKShare 所需前缀
            if symbol.startswith(('600', '601', '603', '605', '688')):
                ak_symbol = f"sh{symbol}"
            else:
                ak_symbol = f"sz{symbol}"

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            # 使用 stock_zh_a_daily（直连稳定，不走东方财富 push2his 接口）
            df = ak.stock_zh_a_daily(
                symbol=ak_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

            if df is not None and not df.empty and len(df) >= 10:
                # stock_zh_a_daily 列名已是英文：date, open, high, low, close, volume
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)

                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                df = df.dropna(subset=['open', 'high', 'low', 'close'])

                if len(df) >= 10:
                    df.attrs['adjust_method'] = '前复权(qfq)'
                    return df

        except Exception as e:
            print(f"AKShare 获取失败 {symbol}: {str(e)}")

        return None

    def _get_cn_stock_data_sina_fallback(self, symbol, period, **kwargs):
        """获取A股数据 - 新浪财经（备选数据源，带超时）"""
        try:
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
            days = period_days.get(period, 365)

            # 判断交易所后缀
            if symbol.startswith(('600', '601', '603', '605', '688')):
                sina_symbol = f"sh{symbol}"
            else:
                sina_symbol = f"sz{symbol}"

            url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_symbol}&scale=240&ma=5&datalen={days}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/'
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200 and response.text.strip():
                import json
                data = json.loads(response.text)
                if data and isinstance(data, list) and len(data) >= 10:
                    df = pd.DataFrame(data)
                    df.rename(columns={
                        'day': 'date', 'open': 'open', 'high': 'high',
                        'low': 'low', 'close': 'close', 'volume': 'volume'
                    }, inplace=True)
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    df = df.dropna(subset=['open', 'high', 'low', 'close'])
                    if len(df) >= 10:
                        df.attrs['adjust_method'] = '未复权（新浪财经）'
                        return df
        except requests.exceptions.Timeout:
            print(f"新浪财经请求超时 {symbol}")
        except requests.exceptions.RequestException as e:
            print(f"新浪财经网络错误 {symbol}: {str(e)}")
        except Exception as e:
            print(f"新浪财经失败 {symbol}: {str(e)}")

        return None

    def _get_cn_stock_data_yfinance(self, symbol, period, **kwargs):
        """使用yfinance获取A股数据"""
        import time
        max_retries = 2

        for attempt in range(max_retries):
            try:
                if '.' not in symbol:
                    # 根据股票代码规则判断交易所
                    # 600/601/603/688 开头是上海，000/002/300 开头是深圳
                    if symbol.startswith(('600', '601', '603', '605', '688')):
                        # 上海交易所
                        symbol_yf = f"{symbol}.SS"
                    elif symbol.startswith(('000', '001', '002', '003', '300', '301')):
                        # 深圳交易所
                        symbol_yf = f"{symbol}.SZ"
                    else:
                        # 未知，先尝试上海再尝试深圳
                        symbol_yf = f"{symbol}.SS"

                    ticker = yf.Ticker(symbol_yf)
                    data = ticker.history(period=period)

                    # 如果失败，尝试另一个交易所
                    if data.empty or len(data) < 10:
                        if symbol_yf.endswith('.SS'):
                            symbol_yf = f"{symbol}.SZ"
                        else:
                            symbol_yf = f"{symbol}.SS"
                        ticker = yf.Ticker(symbol_yf)
                        data = ticker.history(period=period)
                else:
                    ticker = yf.Ticker(symbol)
                    data = ticker.history(period=period)

                if not data.empty and len(data) >= 10:
                    # 标准化列名
                    data.columns = [col.lower().replace(' ', '_') for col in data.columns]
                    data.attrs['adjust_method'] = 'adjusted close（yfinance）'
                    return data

                if attempt < max_retries - 1:
                    time.sleep(1)

            except Exception as e:
                print(f"yfinance尝试 {attempt+1} 失败 {symbol}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)

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

        info = self._retry_with_backoff(_fetch_info, 'yfinance')
        if info is None:
            return {'shortName': symbol, 'symbol': symbol}
        return info

    def get_stock_name(self, symbol, market="US"):
        """获取股票名称，A股优先从 AKShare 实时获取（东方财富数据）"""
        if market == "CN":
            # 第一优先：AKShare 实时数据（使用缓存的快照，避免重复下载全市场数据）
            spot_df = self._get_spot_snapshot()
            if spot_df is not None:
                stock_row = spot_df[spot_df['代码'] == symbol]
                if not stock_row.empty:
                    return stock_row.iloc[0]['名称']

            # 第二优先：新浪财经
            try:
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

                url = f"https://hq.sinajs.cn/list=sh{symbol}"
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    import re
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 1 and data[0]:
                            return data[0]
            except Exception:
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
        """获取实时行情 - A股优先使用 AKShare（同花顺/东方财富数据）"""
        try:
            if market == "CN":
                # 第一优先：AKShare 实时行情（使用缓存的快照，避免重复下载全市场数据）
                spot_df = self._get_spot_snapshot()
                if spot_df is not None:
                    stock_row = spot_df[spot_df['代码'] == symbol]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        return {
                            'symbol': symbol,
                            'name': row['名称'],
                            'price': float(row['最新价']),
                            'open': float(row['今开']),
                            'high': float(row['最高']),
                            'low': float(row['最低']),
                            'volume': int(float(row['成交量']) / 100),  # 转换为手
                            'prev_close': float(row['昨收']),
                            'change': (float(row['最新价']) / float(row['昨收']) - 1) * 100
                        }

                # 第二优先：新浪财经实时行情
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
                                'change': (float(data[3]) / float(data[2]) - 1) * 100
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
                                'change': (float(data[3]) / float(data[2]) - 1) * 100
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

    @staticmethod
    def fetch_multiple_stocks(symbols, period="3mo", market="CN", max_workers=5):
        """
        并发获取多只股票数据
        用于股票对比和智能推荐页面
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        fetcher = StockDataFetcher()

        def fetch_single(symbol_info):
            """获取单只股票数据"""
            try:
                if isinstance(symbol_info, dict):
                    symbol = symbol_info['code']
                    name = symbol_info.get('name', symbol)
                else:
                    symbol = symbol_info
                    name = symbol

                data = fetcher.get_stock_data(symbol, period=period, market=market)
                if data is not None and len(data) >= 10:
                    return symbol, {'data': data, 'name': name, 'success': True}
                return symbol, {'data': None, 'name': name, 'success': False}
            except Exception as e:
                return symbol_info if isinstance(symbol_info, str) else symbol_info.get('code'), \
                       {'data': None, 'name': symbol_info if isinstance(symbol_info, str) else symbol_info.get('name', ''), 'success': False, 'error': str(e)}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_single, symbol): symbol for symbol in symbols}

            for future in as_completed(futures):
                symbol, result = future.result()
                results[symbol] = result

        return results

    def set_preferred_source(self, source):
        """
        设置优先数据源
        source: 'auto', 'akshare', 'sina', 'yfinance'
        """
        valid_sources = ['auto', 'akshare', 'sina', 'yfinance']
        if source in valid_sources:
            self.preferred_source = source
            # 同时设置环境变量，让其他实例也能感知
            os.environ['STOCK_DATA_SOURCE'] = source
            return True
        return False

    def get_preferred_source(self):
        """获取当前优先数据源设置"""
        return self.preferred_source


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

POPULAR_US_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC',
                   'JPM', 'V', 'WMT', 'JNJ', 'MA', 'PG', 'UNH', 'HD', 'BAC', 'DIS']

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

POPULAR_HK_STOCKS = [
    {'code': '00700', 'name': '腾讯控股'},
    {'code': '09988', 'name': '阿里巴巴'},
    {'code': '03690', 'name': '美团'},
    {'code': '00005', 'name': '汇丰控股'},
    {'code': '01299', 'name': '友邦保险'},
    {'code': '00388', 'name': '香港交易所'},
    {'code': '00939', 'name': '建设银行'},
    {'code': '01398', 'name': '工商银行'},
    {'code': '03988', 'name': '中国银行'},
    {'code': '02318', 'name': '中国平安'},
    {'code': '00941', 'name': '中国移动'},
    {'code': '00883', 'name': '中国海油'},
    {'code': '01810', 'name': '小米集团'},
    {'code': '01211', 'name': '比亚迪股份'},
    {'code': '09618', 'name': '京东集团'},
    {'code': '09999', 'name': '网易'},
    {'code': '09888', 'name': '百度集团'},
    {'code': '01024', 'name': '快手'},
    {'code': '00992', 'name': '联想集团'},
    {'code': '00981', 'name': '中芯国际'},
]
