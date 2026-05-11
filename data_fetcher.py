"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
使用 AKShare（新浪/东方财富数据源）作为主要A股数据源，实时行情优先新浪
"""
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

# 绕过Windows系统代理（系统代理127.0.0.1:7897不可用时会导致所有数据源失败）
# 创建专用 session，trust_env=False 避免读取 Windows 注册表中的代理配置
_session = requests.Session()
_session.trust_env = False

from config import SPOT_CACHE_TTL_SECONDS
import random
import io
import json
import os
import re
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

    # 离线缓存文件锁，防止多线程并发写坏
    _cache_lock = Lock()

    # 数据源健康状态缓存
    _health_status = {
        'akshare_em': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'akshare': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'sina': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'yfinance': {'healthy': True, 'last_check': None, 'fail_count': 0}
    }

    # 全市场快照缓存（避免每次获取单只股票名称/行情都下载5000+行）
    _spot_cache = None
    _spot_cache_time = None
    _spot_cache_ttl = timedelta(seconds=SPOT_CACHE_TTL_SECONDS)

    _index_spot_cache = None
    _index_spot_cache_time = None

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
        """获取A股全市场快照（带缓存，60秒内复用，避免重复下载5000+条）
        数据源：新浪财经（通过 AKShare）
        成功下载后自动生成主板股票池缓存文件
        """
        now = datetime.now()
        if cls._spot_cache is not None and cls._spot_cache_time is not None:
            if now - cls._spot_cache_time < cls._spot_cache_ttl:
                return cls._spot_cache
        if AKSHARE_AVAILABLE:
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(ak.stock_zh_a_spot)
                    cls._spot_cache = future.result(timeout=45)
                cls._spot_cache_time = now

                # 自动生成主板股票池缓存（供推荐系统使用）
                cls._save_main_board_cache(cls._spot_cache)

                return cls._spot_cache
            except Exception:
                return None
        return None

    @classmethod
    def _save_main_board_cache(cls, spot_df):
        """从全市场快照中提取主板股票并写入缓存文件"""
        import json as _json
        cache_file = os.path.join(os.path.dirname(__file__), '.main_board_cache.json')
        try:
            stocks = []
            for _, row in spot_df.iterrows():
                code = str(row['代码'])
                if code.startswith(('sh', 'sz', 'bj')):
                    code = code[2:]
                # 仅保留沪深主板（排除创业板/科创板/北交所）
                if not (code.startswith(('600', '601', '603', '605')) or
                        code.startswith(('000', '001', '002', '003'))):
                    continue
                stocks.append({'code': code, 'name': str(row['名称'])})

            with open(cache_file, 'w', encoding='utf-8') as f:
                _json.dump({
                    'updated': datetime.now().isoformat(),
                    'count': len(stocks),
                    'stocks': stocks
                }, f, ensure_ascii=False)
        except Exception:
            pass

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
        """保存离线缓存数据（线程安全 + 原子写入）"""
        with self._cache_lock:
            try:
                cache_data = {}
                if os.path.exists(self._offline_cache_file):
                    try:
                        with open(self._offline_cache_file, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                    except json.JSONDecodeError:
                        # 缓存文件已损坏，重建
                        cache_data = {}

                # 只保存最近20个股票
                if len(cache_data) >= 20:
                    oldest_key = min(cache_data.keys(), key=lambda k: cache_data[k].get('timestamp', 0))
                    del cache_data[oldest_key]

                cache_data[symbol] = {
                    'timestamp': datetime.now().isoformat(),
                    'data': data.to_json(orient='split', date_format='iso') if isinstance(data, pd.DataFrame) else data
                }

                # 原子写入：先写临时文件，再 os.replace 替换
                tmp_file = self._offline_cache_file + '.tmp'
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, default=str)
                os.replace(tmp_file, self._offline_cache_file)
            except Exception as e:
                print(f"保存离线缓存失败: {str(e)}")
                # 清理可能残留的临时文件
                try:
                    tmp_file = self._offline_cache_file + '.tmp'
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass

    def _load_offline_cache(self, symbol, max_age_hours=24):
        """加载离线缓存数据（线程安全）"""
        try:
            if not os.path.exists(self._offline_cache_file):
                return None

            with self._cache_lock:
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
                if datetime.now() - cache_time < timedelta(minutes=2):
                    if isinstance(cache_data, pd.DataFrame):
                        cache_data.attrs['data_source'] = cache_source
                    return cache_data

            result = None
            data_source = None
            offline_mode = False

            if market == "CN":
                # A股数据获取：始终构建完整回退链，按用户偏好排序
                all_sources = [
                    ('akshare_em', self._get_cn_stock_data_akshare_em, '东方财富'),
                    ('akshare', self._get_cn_stock_data_akshare, '腾讯财经'),
                    ('sina', self._get_cn_stock_data_sina_fallback, '新浪财经'),
                ]
                # yfinance 对 A 股数据不稳定，仅作最后兜底（不暴露为可选偏好）
                all_sources.append(('yfinance', self._get_cn_stock_data_yfinance, 'Yahoo Finance'))

                sources_to_try = []
                if self.preferred_source == 'auto':
                    # 自动模式：按默认健康顺序
                    for src_name, src_func, src_label in all_sources:
                        if self._health_status[src_name]['healthy']:
                            sources_to_try.append((src_name, src_func))
                else:
                    # 用户指定偏好源：该源排第一，其余健康源作回退
                    for src_name, src_func, src_label in all_sources:
                        if src_name == self.preferred_source and self._health_status[src_name]['healthy']:
                            sources_to_try.append((src_name, src_func))
                    for src_name, src_func, src_label in all_sources:
                        if src_name != self.preferred_source and self._health_status[src_name]['healthy']:
                            sources_to_try.append((src_name, src_func))

                # 尝试所有数据源
                for source_name, source_func in sources_to_try:
                    try:
                        result = self._retry_with_backoff(source_func, source_name, symbol, period)
                        if result is not None and len(result) >= 10:
                            data_source = {
                                'akshare_em': '东方财富',
                                'akshare': '腾讯财经',
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
                # 港股：Yahoo Finance 历史K线（国内可直连），新浪实时行情
                result = self._retry_with_backoff(
                    lambda s, p: yf.Ticker(f"{s}.HK").history(period=p, interval=interval),
                    'yfinance', symbol, period
                )
                if result is not None and not result.empty:
                    data_source = "Yahoo Finance"
                # 失败则尝试离线缓存
                if result is None:
                    result = self._load_offline_cache(symbol)
                    if result is not None:
                        data_source = result.attrs.get('data_source', '离线缓存')
                        offline_mode = True
            elif market == "US":
                # 美股：新浪财经历史日K（国内直连），AKShare 备用
                result = self._get_us_stock_data_sina(symbol, period)
                if result is not None:
                    data_source = "新浪财经"
                if result is None:
                    result = self._retry_with_backoff(
                        lambda s, p: yf.Ticker(s).history(period=p, interval=interval),
                        'yfinance', symbol, period
                    )
                    if result is not None and not result.empty:
                        data_source = "Yahoo Finance"
                if result is None:
                    result = self._load_offline_cache(symbol)
                    if result is not None:
                        data_source = result.attrs.get('data_source', '离线缓存')
                        offline_mode = True

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

    def _get_us_stock_data_sina(self, symbol, period, **kwargs):
        """使用新浪财经获取美股历史日K数据"""
        try:
            period_days = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
            days = period_days.get(period, 365)
            # 美股约252个交易日/年，加10条余量
            datalen = max(int(days * 252 / 365) + 10, 10)

            url = 'https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK'
            params = {'symbol': symbol.lower(), 'type': 'day', 'datalen': datalen}
            headers = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = _session.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data or not isinstance(data, list) or len(data) < 10:
                return None

            df = pd.DataFrame(data)
            df = df.rename(columns={'d': 'date', 'o': 'open', 'h': 'high',
                                    'l': 'low', 'c': 'close', 'v': 'volume'})
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            if len(df) >= 10:
                return df
        except Exception as e:
            print(f"新浪美股历史数据获取失败 {symbol}: {str(e)}")
        return None

    def _get_cn_stock_data_akshare_em(self, symbol, period, **kwargs):
        """使用 AKShare 获取A股历史数据（东方财富数据源，与同花顺一致）"""
        if not AKSHARE_AVAILABLE:
            return None

        try:
            period_days = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
            days = period_days.get(period, 365)

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=""  # 不复权，与同花顺默认一致
            )

            if df is not None and not df.empty and len(df) >= 10:
                # stock_zh_a_hist 列名为中文，需要重命名
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                })
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)

                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                df = df.dropna(subset=['open', 'high', 'low', 'close'])

                if len(df) >= 10:
                    df.attrs['adjust_method'] = '不复权'
                    df.attrs['data_provider'] = '东方财富'
                    return df

        except Exception as e:
            print(f"AKShare(东方财富) 获取失败 {symbol}: {str(e)}")

        return None

    def _get_cn_stock_data_akshare(self, symbol, period, **kwargs):
        """使用 AKShare 获取A股历史数据（腾讯财经数据源，直连稳定）"""
        if not AKSHARE_AVAILABLE:
            return None

        try:
            # 转换period为天数
            period_days = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
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
                adjust=""  # 不复权，与同花顺默认一致
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
                    df.attrs['adjust_method'] = '不复权'
                    return df

        except Exception as e:
            print(f"AKShare 获取失败 {symbol}: {str(e)}")

        return None

    def _get_cn_stock_data_sina_fallback(self, symbol, period, **kwargs):
        """获取A股数据 - 新浪财经（备选数据源，带超时）"""
        try:
            period_days = {"1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
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
            response = _session.get(url, headers=headers, timeout=10)

            if response.status_code == 200 and response.text.strip():
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
        """获取股票名称，新浪优先（快~200ms），AKShare快照兜底，映射表最终回退"""
        if market == "CN":
            # 第一优先：新浪财经实时行情（~200ms，快）
            prefix_map = [
                ('sz', lambda s: s.startswith(('0', '3'))),
                ('sh', lambda s: s.startswith('6')),
                ('bj', lambda s: s.startswith(('4', '8'))),
            ]
            for prefix, check in prefix_map:
                if check(symbol):
                    try:
                        url = f"https://hq.sinajs.cn/list={prefix}{symbol}"
                        headers = {
                            'Referer': 'https://finance.sina.com.cn',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                        response = _session.get(url, headers=headers, timeout=3)
                        if response.status_code == 200:
                            match = re.search(r'"([^"]*)"', response.text)
                            if match:
                                data = match.group(1).split(',')
                                if len(data) >= 1 and data[0]:
                                    return data[0]
                    except Exception:
                        pass
                    break  # 匹配到前缀就不再试其他

            # 前缀不明确时，先试深圳再试上海
            try:
                url = f"https://hq.sinajs.cn/list=sz{symbol}"
                response = _session.get(url, headers={
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }, timeout=3)
                if response.status_code == 200:
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 1 and data[0]:
                            return data[0]
                url = f"https://hq.sinajs.cn/list=sh{symbol}"
                response = _session.get(url, headers={
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }, timeout=3)
                if response.status_code == 200:
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 1 and data[0]:
                            return data[0]
            except Exception:
                pass

            # 第二优先：查映射表（即时）
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return name

            # 第三优先：AKShare 全市场快照（慢，但覆盖全）
            spot_df = self._get_spot_snapshot()
            if spot_df is not None:
                stock_row = spot_df[spot_df['代码'].str.endswith(symbol)]
                if not stock_row.empty:
                    return stock_row.iloc[0]['名称']

            return symbol

        # 美股/港股使用yfinance
        try:
            info = self.get_stock_info(symbol, market)
            if info:
                name = info.get('shortName') or info.get('longName')
                if name:
                    return name
        except Exception:
            pass
        return symbol

    def get_realtime_quote(self, symbol, market="US"):
        """获取实时行情 - A股优先新浪HTTP（~200ms），AKShare快照做 fallback"""
        try:
            if market == "CN":
                # 确定交易所前缀
                if symbol.startswith('6'):
                    prefix = 'sh'
                elif symbol.startswith('0') or symbol.startswith('3'):
                    prefix = 'sz'
                elif symbol.startswith('4') or symbol.startswith('8'):
                    prefix = 'bj'
                else:
                    prefix = 'sz'

                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                # 第一优先：新浪财经实时行情（~200ms，快）
                url = f"https://hq.sinajs.cn/list={prefix}{symbol}"
                response = _session.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    content = response.text
                    match = re.search(r'"([^"]*)"', content)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 33 and data[3]:
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

                # 第二优先：AKShare 全市场快照（带缓存，首次慢后续快）
                spot_df = self._get_spot_snapshot()
                if spot_df is not None:
                    stock_row = spot_df[spot_df['代码'].str.endswith(symbol)]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        return {
                            'symbol': symbol,
                            'name': row['名称'],
                            'price': float(row['最新价']),
                            'open': float(row['今开']),
                            'high': float(row['最高']),
                            'low': float(row['最低']),
                            'volume': int(float(row['成交量']) / 100),
                            'prev_close': float(row['昨收']),
                            'change': (float(row['最新价']) / float(row['昨收']) - 1) * 100
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
                # 港股实时行情：新浪财经优先
                quote = self._get_sina_realtime(symbol, "hk")
                if quote:
                    return quote
                # 备选：Yahoo Finance
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
                # 美股实时行情：新浪财经优先
                quote = self._get_sina_realtime(symbol, "us")
                if quote:
                    return quote
                # 备选：Yahoo Finance
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

    def get_batch_realtime_quotes(self, symbols, market="CN"):
        """批量获取实时行情，并行新浪HTTP调用（每只~200ms）
        返回 {symbol: {price, change_pct}}，查不到的 symbol 不在结果中
        """
        result = {}
        if not symbols or market != "CN":
            return result

        import concurrent.futures as _cf

        def _fetch_one(symbol):
            try:
                # 确定交易所前缀
                if symbol.startswith('6'):
                    prefix = 'sh'
                elif symbol.startswith('0') or symbol.startswith('3'):
                    prefix = 'sz'
                elif symbol.startswith('4') or symbol.startswith('8'):
                    prefix = 'bj'
                else:
                    prefix = 'sz'
                url = f"https://hq.sinajs.cn/list={prefix}{symbol}"
                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = _session.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    match = re.search(r'"([^"]*)"', response.text)
                    if match:
                        data = match.group(1).split(',')
                        if len(data) >= 33 and data[3]:
                            price = float(data[3])
                            prev_close = float(data[2])
                            return symbol, {
                                'price': price,
                                'change_pct': round((price / prev_close - 1) * 100, 2),
                            }
            except Exception:
                pass
            return symbol, None

        with _cf.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_one, s): s for s in symbols}
            for future in _cf.as_completed(futures, timeout=8):
                try:
                    symbol, data = future.result(timeout=5)
                    if data is not None:
                        result[symbol] = data
                except Exception:
                    pass
        return result

    def get_index_realtime(self, symbol):
        """获取A股指数实时行情

        Returns:
            dict: {symbol, name, price, change_pct, prev_close} 或 None
        """
        try:
            if AKSHARE_AVAILABLE:
                try:
                    spot_df = self._get_index_spot()
                    if spot_df is not None:
                        row_match = spot_df[spot_df['代码'] == symbol]
                        if not row_match.empty:
                            row = row_match.iloc[0]
                            return {
                                'symbol': symbol,
                                'name': row['名称'],
                                'price': float(row['最新价']),
                                'change_pct': float(row['涨跌幅']),
                                'prev_close': float(row['昨收']),
                            }
                except Exception as e:
                    print(f"AKShare指数行情失败 {symbol}: {e}")

            # 新浪财经（使用全版格式，非简版 s_ 前缀）
            if symbol.startswith('000') or symbol.startswith('600'):
                sina_code = f"sh{symbol}"
            elif symbol.startswith('899'):
                sina_code = f"bj{symbol}"
            else:
                sina_code = f"sz{symbol}"
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = _session.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                content = resp.text
                match = re.search(r'"([^"]*)"', content)
                if match:
                    data = match.group(1).split(',')
                    if len(data) >= 4:
                        price = float(data[3]) if data[3] else 0
                        prev_close = float(data[2]) if data[2] else 1
                        return {
                            'symbol': symbol,
                            'name': data[0],
                            'price': price,
                            'change_pct': (price / prev_close - 1) * 100 if prev_close else 0,
                            'prev_close': prev_close,
                        }

            # yfinance
            yf_map = {'000001': '^SSEC', '399001': '399001.SZ', '399006': '399006.SZ'}
            yf_symbol = yf_map.get(symbol, f"{symbol}.SS")
            try:
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info or {}
                hist = ticker.history(period='5d')
                if hist is not None and len(hist) >= 2:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2]
                    return {
                        'symbol': symbol,
                        'name': info.get('shortName', symbol),
                        'price': float(latest['Close']),
                        'change_pct': float((latest['Close'] / prev['Close'] - 1) * 100),
                        'prev_close': float(prev['Close']),
                    }
            except Exception:
                pass

        except Exception as e:
            print(f"获取指数行情失败 {symbol}: {e}")
        return None

    @classmethod
    def _get_index_spot(cls):
        """获取A股指数快照（类级别缓存60秒）"""
        now = datetime.now()
        if (cls._index_spot_cache is not None and cls._index_spot_cache_time is not None
                and (now - cls._index_spot_cache_time).seconds < SPOT_CACHE_TTL_SECONDS):
            return cls._index_spot_cache
        if not AKSHARE_AVAILABLE:
            return None
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(ak.stock_zh_index_spot_em)
                cls._index_spot_cache = future.result(timeout=8)
            cls._index_spot_cache_time = now
            return cls._index_spot_cache
        except Exception as e:
            print(f"AKShare指数快照失败: {e}")
            return None

    def _get_sina_realtime(self, symbol, market):
        """新浪财经实时行情 — 支持 us / hk"""
        if market == "hk":
            sina_sym = f"hk{symbol}"
        elif market == "us":
            sina_sym = f"gb_{symbol.lower()}"
        else:
            return None

        url = f"https://hq.sinajs.cn/list={sina_sym}"
        headers = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        try:
            resp = _session.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None
            match = re.search(r'"([^"]*)"', resp.text)
            if not match:
                return None
            data = match.group(1).split(',')
        except Exception:
            return None

        if market == "hk" and len(data) >= 17:
            return {
                'symbol': symbol,
                'name': data[1] if data[1] else data[0],
                'price': float(data[4]),          # 最新价
                'open': float(data[3]),           # 今开
                'high': float(data[2]),           # 最高
                'low': float(data[6]),            # 最低
                'volume': int(float(data[12])),   # 成交量（股）
                'prev_close': float(data[5]),     # 昨收
                'change': float(data[8]),         # 涨跌幅(%)
            }
        elif market == "us" and len(data) >= 11:
            # 新浪美股: 名称, 最新价, 涨跌幅(%), 时间, 涨跌额($), 今开, 最高, 最低, ...
            return {
                'symbol': symbol,
                'name': data[0],
                'price': float(data[1]),
                'open': float(data[5]),
                'high': float(data[6]),
                'low': float(data[7]),
                'volume': int(float(data[10])),
                'prev_close': float(data[1]) - float(data[4]),  # 昨收 = 最新价 - 涨跌额($)
                'change': float(data[2]),  # 涨跌幅(%)
            }
        return None

    def get_intraday_data(self, symbol, market="CN"):
        """获取当日分钟K线数据，用于分时图（仅A股，新浪优先，东方财富备用）"""
        if market != "CN":
            return None

        cache_key = f"intraday_{symbol}"
        if cache_key in self.cache:
            cache_time, cache_data, _ = self.cache[cache_key]
            if datetime.now() - cache_time < timedelta(minutes=1):
                return cache_data

        df = self._fetch_intraday_sina(symbol, cache_key)
        if df is None and AKSHARE_AVAILABLE:
            df = self._fetch_intraday_akshare(symbol, cache_key)
        return df

    def _fetch_intraday_sina(self, symbol, cache_key):
        """新浪财经分钟数据（稳定，5分钟线）"""
        try:
            prefix = 'sh' if symbol.startswith('6') else 'sz'
            sina_symbol = f'{prefix}{symbol}'
            url = ('https://quotes.sina.cn/cn/api/json_v2.php/'
                   f'CN_MarketDataService.getKLineData?symbol={sina_symbol}'
                   '&scale=5&ma=no&datalen=240')
            r = _session.get(url, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            if not data or not isinstance(data, list):
                return None
            df = pd.DataFrame(data)
            df.rename(columns={
                'day': 'time', 'open': 'open', 'high': 'high',
                'low': 'low', 'close': 'close', 'volume': 'volume',
                'amount': 'amount'
            }, inplace=True)
            df['time'] = pd.to_datetime(df['time'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').astype(int)
            if 'amount' in df.columns:
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
                # 计算均价 = 累计成交额 / 累计成交量
                df['avg_price'] = df['amount'].cumsum() / df['volume'].cumsum().replace(0, float('nan'))
            # 仅保留当日数据
            today = pd.Timestamp.now().date()
            df = df[df['time'].dt.date == today].copy()
            if df.empty:
                return None
            self.cache[cache_key] = (datetime.now(), df, "新浪财经")
            return df
        except Exception:
            return None

    def _fetch_intraday_akshare(self, symbol, cache_key):
        """东方财富分钟数据（备用，1分钟线）"""
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=symbol, period='1', adjust='')
            if df is not None and len(df) > 0:
                df.rename(columns={
                    '时间': 'time', '开盘': 'open', '收盘': 'close',
                    '最高': 'high', '最低': 'low', '成交量': 'volume',
                    '成交额': 'amount', '均价': 'avg_price'
                }, inplace=True)
                df['time'] = pd.to_datetime(df['time'])
                # 仅保留当日数据
                today = pd.Timestamp.now().date()
                df = df[df['time'].dt.date == today].copy()
                if df.empty:
                    return None
                self.cache[cache_key] = (datetime.now(), df, "AKShare(东方财富)")
                return df
        except Exception:
            pass
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

    @classmethod
    def get_main_board_stocks(cls):
        """获取全部主板A股股票列表（排除创业板/科创板），缓存24小时

        优先从缓存文件加载，过期后从 AKShare 全市场快照刷新。
        返回 [{'code': '000001', 'name': '平安银行'}, ...]
        """
        import json as _json
        cache_file = os.path.join(os.path.dirname(__file__), '.main_board_cache.json')

        # 1. 尝试从缓存加载（24小时有效）
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = _json.load(f)
                cache_time = datetime.fromisoformat(cached.get('updated', '2000-01-01'))
                if datetime.now() - cache_time < timedelta(hours=24):
                    return cached['stocks']
        except Exception:
            pass

        # 2. 从AKShare全市场快照获取
        stocks = []
        try:
            spot_df = cls._get_spot_snapshot()
            if spot_df is not None and not spot_df.empty:
                for _, row in spot_df.iterrows():
                    code = str(row['代码'])
                    # 去掉交易所前缀（sh600519 → 600519）
                    if code.startswith(('sh', 'sz', 'bj')):
                        code = code[2:]
                    # 仅保留沪深主板（排除创业板/科创板/北交所）
                    if not (code.startswith(('600', '601', '603', '605')) or
                            code.startswith(('000', '001', '002', '003'))):
                        continue
                    stocks.append({'code': code, 'name': str(row['名称'])})

                # 写入缓存
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        _json.dump({
                            'updated': datetime.now().isoformat(),
                            'count': len(stocks),
                            'stocks': stocks
                        }, f, ensure_ascii=False)
                except Exception:
                    pass
        except Exception:
            pass

        return stocks


# 股票名称映射表（静态回退，覆盖沪深主板主要龙头 ~200只）
CN_STOCK_NAMES_EXTENDED = {
    # 金融
    '000001': '平安银行', '002142': '宁波银行', '600000': '浦发银行', '600015': '华夏银行',
    '600016': '民生银行', '600036': '招商银行', '601009': '南京银行', '601166': '兴业银行',
    '601229': '上海银行', '601288': '农业银行', '601328': '交通银行', '601398': '工商银行',
    '601818': '光大银行', '601939': '建设银行', '601988': '中国银行', '601997': '贵阳银行',
    # 券商
    '000166': '申万宏源', '000776': '广发证券', '002736': '国信证券', '600030': '中信证券',
    '600837': '海通证券', '600958': '东方证券', '601066': '中信建投', '601211': '国泰君安',
    '601236': '红塔证券', '601377': '兴业证券', '601688': '华泰证券', '601878': '浙商证券',
    # 保险
    '601318': '中国平安', '601319': '中国人保', '601336': '新华保险', '601601': '中国太保',
    '601628': '中国人寿',
    # 白酒食品
    '000568': '泸州老窖', '000596': '古井贡酒', '000799': '酒鬼酒', '000858': '五粮液',
    '000860': '顺鑫农业', '002304': '洋河股份', '600519': '贵州茅台', '600559': '老白干酒',
    '600600': '青岛啤酒', '600702': '舍得酒业', '600779': '水井坊', '600809': '山西汾酒',
    '600887': '伊利股份', '002568': '百润股份', '603288': '海天味业', '603345': '安井食品',
    '600882': '妙可蓝多', '002847': '盐津铺子',
    # 医药
    '000423': '东阿阿胶', '000538': '云南白药', '000963': '华东医药', '002001': '新和成',
    '002007': '华兰生物', '002422': '科伦药业', '600085': '同仁堂', '600196': '复星医药',
    '600276': '恒瑞医药', '600332': '白云山', '600436': '片仔癀', '600566': '济川药业',
    '603259': '药明康德', '603392': '万泰生物', '603658': '安图生物',
    # 家电家居
    '000333': '美的集团', '000651': '格力电器', '002032': '苏泊尔', '002242': '九阳股份',
    '002508': '老板电器', '600690': '海尔智家', '603486': '科沃斯', '000100': 'TCL科技',
    '002705': '新宝股份',
    # 新能源
    '002074': '国轩高科', '002129': 'TCL中环', '002459': '晶澳科技', '002460': '赣锋锂业',
    '600438': '通威股份', '600732': '爱旭股份', '601012': '隆基绿能', '601615': '明阳智能',
    '601865': '福莱特', '603185': '上机数控', '603799': '华友钴业', '603806': '福斯特',
    # 新能源汽车
    '002594': '比亚迪', '000625': '长安汽车', '000800': '一汽解放', '600104': '上汽集团',
    '600733': '北汽蓝谷', '601127': '赛力斯', '601238': '广汽集团', '601633': '长城汽车',
    # 电力能源
    '000027': '深圳能源', '000539': '粤电力A', '000543': '皖能电力', '600011': '华能国际',
    '600023': '浙能电力', '600025': '华能水电', '600027': '华电国际', '600795': '国电电力',
    '600886': '国投电力', '600900': '长江电力', '600905': '三峡能源', '601985': '中国核电',
    '601857': '中国石油', '600028': '中国石化', '601088': '中国神华', '600188': '兖矿能源',
    '601225': '陕西煤业', '601699': '潞安环能', '601898': '中煤能源',
    # 电子半导体
    '000725': '京东方A', '002049': '紫光国微', '002156': '通富微电', '002185': '华天科技',
    '002371': '北方华创', '002409': '雅克科技', '002916': '深南电路', '002938': '鹏鼎控股',
    '600171': '上海贝岭', '600460': '士兰微', '600584': '长电科技', '600703': '三安光电',
    '603005': '晶方科技', '603160': '汇顶科技', '603501': '韦尔股份', '603986': '兆易创新',
    '002456': '欧菲光', '002475': '立讯精密',
    # 计算机软件
    '002230': '科大讯飞', '002410': '广联达', '002439': '启明星辰', '600536': '中国软件',
    '600570': '恒生电子', '600588': '用友网络', '603019': '中科曙光', '000977': '浪潮信息',
    '002335': '科华数据', '600845': '宝信软件', '603881': '数据港', '600756': '浪潮软件',
    '000938': '中核科技',
    # 通信
    '000063': '中兴通讯', '002396': '星网锐捷', '600487': '亨通光电', '600498': '烽火通信',
    '600522': '中天科技', '601138': '工业富联', '601728': '中国电信', '601869': '长飞光纤',
    '600941': '中国移动',
    # 军工
    '000768': '中航西飞', '002013': '中航机电', '002025': '航天电器', '002179': '中航光电',
    '600038': '中直股份', '600118': '中国卫星', '600150': '中国船舶', '600391': '航发科技',
    '600685': '中船防务', '600760': '中航沈飞', '600862': '中航高科', '600893': '航发动力',
    '601989': '中国重工',
    # 化工
    '000301': '东方盛虹', '000408': '藏格矿业', '000792': '盐湖股份', '000830': '鲁西化工',
    '002064': '华峰化学', '002601': '龙佰集团', '600309': '万华化学', '600346': '恒力石化',
    '600352': '浙江龙盛', '600426': '华鲁恒升', '600989': '宝丰能源', '601233': '桐昆股份',
    # 有色钢铁
    '000630': '铜陵有色', '000831': '中国稀土', '000878': '云南铜业', '000933': '神火股份',
    '002155': '湖南黄金', '600010': '包钢股份', '600019': '宝钢股份', '600111': '北方稀土',
    '600362': '江西铜业', '600547': '山东黄金', '600585': '海螺水泥', '600489': '中金黄金',
    '601168': '西部矿业', '601600': '中国铝业', '601899': '紫金矿业',
    # 地产基建
    '000002': '万科A', '000006': '深振业A', '000069': '华侨城A', '000401': '冀东水泥',
    '001979': '招商蛇口', '002146': '荣盛发展', '002244': '滨江集团', '600048': '保利发展',
    '600325': '华发股份', '600383': '金地集团', '600606': '绿地控股',
    '601668': '中国建筑', '601800': '中国交建', '601390': '中国中铁', '601186': '中国铁建',
    # 交通运输
    '000089': '深圳机场', '000338': '潍柴动力', '002352': '顺丰控股', '600004': '白云机场',
    '600009': '上海机场', '600029': '南方航空', '600115': '中国东航', '600377': '宁沪高速',
    '601006': '大秦铁路', '601021': '春秋航空', '601111': '中国国航', '601816': '京沪高铁',
    '601919': '中远海控',
    # 大消费
    '000999': '华润三九', '002024': '苏宁易购', '002127': '南极电商', '002277': '友阿股份',
    '002419': '天虹股份', '002563': '森马服饰', '600655': '豫园股份', '600859': '王府井',
    '601888': '中国中免', '600415': '小商品城',
    # 农业
    '000876': '新希望', '002311': '海大集团', '002714': '牧原股份',
    '600737': '中粮糖业', '600873': '梅花生物', '603363': '傲农生物',
    # 其他制造
    '000157': '中联重科', '000425': '徐工机械', '002050': '三花智控', '002101': '广东鸿图',
    '600031': '三一重工', '600580': '卧龙电驱', '600885': '宏发股份', '603305': '旭升集团',
    '603596': '伯特利', '603920': '世运电路', '002241': '歌尔股份', '002600': '领益智造',
    '601231': '环旭电子', '002929': '润建股份',
    # 传媒
    '000156': '华数传媒', '002027': '分众传媒', '002555': '三七互娱', '002624': '完美世界',
    '600373': '中文传媒', '600637': '东方明珠', '601595': '上海电影', '601928': '凤凰传媒',
    '603444': '吉比特',
}

POPULAR_US_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC',
                   'JPM', 'V', 'WMT', 'JNJ', 'MA', 'PG', 'UNH', 'HD', 'BAC', 'DIS']

def _build_cn_stock_pool():
    """构建A股推荐池：优先加载磁盘缓存（24h有效），无缓存时退回静态映射表

    缓存文件由 StockDataFetcher.get_main_board_stocks() 在首次成功下载后写入。
    应用冷启动后缓存就已存在（除首次部署外），无需每次导入都下载全市场快照。
    """
    import json as _json
    cache_file = os.path.join(os.path.dirname(__file__), '.main_board_cache.json')
    try:
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = _json.load(f)
            cache_time = datetime.fromisoformat(cached.get('updated', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(hours=24):
                stocks = cached.get('stocks', [])
                if stocks and len(stocks) >= 20:
                    return stocks
    except Exception:
        pass

    # 无缓存或缓存过期：退回静态映射表（首次部署时）
    return [{'code': code, 'name': name} for code, name in CN_STOCK_NAMES_EXTENDED.items()]

# 直接加载缓存中的股票池（首次启动时只有静态列表，之后会被动态刷新）
POPULAR_CN_STOCKS = _build_cn_stock_pool()

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
