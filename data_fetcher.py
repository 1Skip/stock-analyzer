"""
股票数据获取模块 - 获取真实股票数据
支持A股、港股、美股
使用同花顺/AKShare（新浪/东方财富数据源）作为主要A股数据源，实时行情优先新浪
"""
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import logging

# 绕过Windows系统代理（系统代理127.0.0.1:7897不可用时会导致所有数据源失败）
# 创建专用 session，trust_env=False 避免读取 Windows 注册表中的代理配置
_session = requests.Session()
_session.trust_env = False

from config import SPOT_CACHE_TTL_SECONDS, OFFLINE_CACHE_MAX_ENTRIES, RUNTIME_CACHE_DIR
import random
import io
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from threading import Lock
from data.providers.daily_kline_provider import (
    AkshareDailyKlineProvider,
    MootdxDailyKlineProvider,
    SinaDailyKlineProvider,
    ThsDailyKlineProvider,
    is_request_error,
    is_timeout_error,
)
from data.providers.eastmoney_intraday_provider import EastmoneyIntradayProvider
from data.providers.index_realtime_provider import SinaIndexRealtimeProvider
from data.providers.sina_intraday_provider import SinaIntradayProvider
from data.providers.sina_realtime_provider import SinaRealtimeProvider
from data.providers.yahoo_kline_provider import YahooKlineProvider
from data.providers.yahoo_quote_provider import YahooQuoteProvider

logger = logging.getLogger(__name__)

# 尝试导入 AKShare，如果失败则使用备选方案
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("AKShare 导入失败，将使用 yfinance 作为备选")


def _runtime_cache_path(filename):
    """返回运行缓存路径，兼容旧根目录缓存文件。"""
    cache_dir = RUNTIME_CACHE_DIR or os.path.dirname(__file__)
    return os.path.join(cache_dir, filename)


def _static_data_path(filename):
    return os.path.join(os.path.dirname(__file__), 'data', 'static', filename)


def _legacy_cache_path(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def _ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _read_json_cache(primary_file, legacy_filename=None):
    """读取运行缓存，主路径不存在时兼容旧根目录缓存。"""
    candidates = [primary_file]
    if legacy_filename:
        legacy_file = _legacy_cache_path(legacy_filename)
        if legacy_file != primary_file:
            candidates.append(legacy_file)

    for cache_file in candidates:
        if not os.path.exists(cache_file):
            continue
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f), cache_file
    return None, None


def _normalize_stock_name(name):
    """规范化股票名称，兼容全角字符、空格和大小写差异。"""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(name))).upper()


def _clean_stock_name(name):
    """清理展示用股票名称，去掉异常空格并转半角。"""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(name)))


def _stock_name_similarity(query, candidate):
    """计算股票名称近似度，兼容相邻字颠倒等常见输入错误。"""
    query = _normalize_stock_name(query)
    candidate = _normalize_stock_name(candidate)
    if not query or not candidate:
        return 0.0
    ratio = SequenceMatcher(None, query, candidate).ratio()
    if len(query) >= 3 and len(candidate) >= 3 and sorted(query) == sorted(candidate):
        ratio = max(ratio, 0.95)
    return ratio


class StockDataFetcher:
    """股票数据获取器 - 带重试机制、离线模式、健康检查"""

    # 类级别的请求锁，防止重复请求
    _request_locks = {}
    _lock_mutex = Lock()

    # 离线缓存文件锁，防止多线程并发写坏
    _cache_lock = Lock()

    # 数据源健康状态缓存
    _health_status = {
        'mootdx': {'healthy': True, 'last_check': None, 'fail_count': 0},
        'ths': {'healthy': True, 'last_check': None, 'fail_count': 0},
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
    _offline_cache_file = _runtime_cache_path('stock_cache.json')
    _default_offline_cache_file = _offline_cache_file
    _main_board_cache_file = _runtime_cache_path('main_board_cache.json')
    _stock_name_index_file = _runtime_cache_path('stock_name_index.json')

    def __init__(self):
        from config import MAX_RETRIES, RETRY_DELAY
        self.cache = {}
        self.max_retries = MAX_RETRIES
        self.retry_delay = RETRY_DELAY
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
    def _get_spot_snapshot(cls, timeout=45):
        """获取A股全市场快照（带缓存，60秒内复用，避免重复下载5000+条）
        数据源：新浪财经（通过 AKShare）
        成功下载后自动生成主板股票池缓存文件
        timeout: 请求超时秒数（默认45，名称搜索时可设短，如8秒）
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
                    cls._spot_cache = future.result(timeout=timeout)
                cls._spot_cache_time = now

                # 自动生成主板股票池缓存（供推荐系统使用）
                cls._save_main_board_cache(cls._spot_cache)

                return cls._spot_cache
            except Exception:
                logger.warning("获取A股全市场快照失败", exc_info=True)
                return None
        return None

    @classmethod
    def _save_main_board_cache(cls, spot_df):
        """从全市场快照中提取主板股票并写入缓存文件"""
        import json as _json
        cache_file = cls._main_board_cache_file
        try:
            _ensure_parent_dir(cache_file)
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
            logger.warning("保存主板股票池缓存失败: %s", cache_file, exc_info=True)

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
                            logger.info("%s 离线超5分钟，尝试恢复检查", source_name)
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
                    logger.warning("%s 数据源暂时跳过（连续失败%s次）", source_name, fail_count)
                    return None

        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                    self._update_health_status(source_name, True)
                    return result
            except Exception:
                logger.warning(
                    "%s 尝试 %s/%s 失败",
                    source_name,
                    attempt + 1,
                    self.max_retries,
                    exc_info=True,
                )
                self._update_health_status(source_name, False)

            if attempt < self.max_retries - 1:
                # 智能退避：失败次数越多，等待越长
                base_delay = self.retry_delay * (2 ** attempt)
                fail_penalty = min(self._health_status[source_name]['fail_count'] * 2, 10)
                delay = base_delay + fail_penalty + random.uniform(0, 0.5)
                time.sleep(delay)
        return None

    @staticmethod
    def _offline_cache_key(symbol, adjust=""):
        adjust_key = str(adjust or "").strip()
        return f"{symbol}__{adjust_key}" if adjust_key else str(symbol)

    def _save_offline_cache(self, symbol, data, adjust=""):
        """保存离线缓存数据（线程安全 + 原子写入）"""
        with self._cache_lock:
            try:
                _ensure_parent_dir(self._offline_cache_file)
                cache_data = {}
                if os.path.exists(self._offline_cache_file):
                    try:
                        with open(self._offline_cache_file, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                    except json.JSONDecodeError:
                        # 缓存文件已损坏，重建
                        cache_data = {}
                elif self._offline_cache_file == self._default_offline_cache_file:
                    try:
                        cache_data, _ = _read_json_cache(self._offline_cache_file, '.stock_cache.json')
                        cache_data = cache_data or {}
                    except json.JSONDecodeError:
                        cache_data = {}

                # 只保存最近 N 个股票
                if len(cache_data) >= OFFLINE_CACHE_MAX_ENTRIES:
                    oldest_key = min(cache_data.keys(), key=lambda k: cache_data[k].get('timestamp', 0))
                    del cache_data[oldest_key]

                cache_key = self._offline_cache_key(symbol, adjust)
                cache_data[cache_key] = {
                    'timestamp': datetime.now().isoformat(),
                    'data': data.to_json(orient='split', date_format='iso') if isinstance(data, pd.DataFrame) else data,
                    'attrs': dict(getattr(data, 'attrs', {}) or {}) if isinstance(data, pd.DataFrame) else {},
                }

                # 原子写入：先写临时文件，再 os.replace 替换
                tmp_file = self._offline_cache_file + '.tmp'
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, default=str)
                os.replace(tmp_file, self._offline_cache_file)
            except Exception:
                logger.warning("保存离线缓存失败: %s", self._offline_cache_file, exc_info=True)
                # 清理可能残留的临时文件
                try:
                    tmp_file = self._offline_cache_file + '.tmp'
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    logger.debug("清理离线缓存临时文件失败", exc_info=True)

    def _load_offline_cache(self, symbol, max_age_hours=24, adjust=""):
        """加载离线缓存数据（线程安全）"""
        try:
            legacy_filename = None
            if self._offline_cache_file == self._default_offline_cache_file:
                legacy_filename = '.stock_cache.json'

            if not os.path.exists(self._offline_cache_file):
                if not legacy_filename or not os.path.exists(_legacy_cache_path(legacy_filename)):
                    return None

            with self._cache_lock:
                try:
                    cache_data, _ = _read_json_cache(self._offline_cache_file, legacy_filename)
                    if not cache_data:
                        return None
                except json.JSONDecodeError:
                    # 缓存文件损坏，删除后重建
                    if os.path.exists(self._offline_cache_file):
                        os.remove(self._offline_cache_file)
                    elif legacy_filename and os.path.exists(_legacy_cache_path(legacy_filename)):
                        logger.warning("旧离线缓存文件已损坏，请删除后重建: %s", _legacy_cache_path(legacy_filename))
                    return None

            cache_key = self._offline_cache_key(symbol, adjust)
            if cache_key not in cache_data:
                return None

            cached = cache_data[cache_key]
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
            cached_attrs = cached.get('attrs') if isinstance(cached.get('attrs'), dict) else {}
            for attr_key, attr_value in cached_attrs.items():
                if attr_key != 'data_source':
                    df.attrs[attr_key] = attr_value
            if 'volume' in df.columns and not df.attrs.get('volume_unit'):
                max_volume = pd.to_numeric(df['volume'], errors='coerce').dropna().max()
                df.attrs['volume_unit'] = 'share' if pd.notna(max_volume) and max_volume >= 1_000_000 else 'hand'
            if adjust:
                df.attrs['adjust_method'] = '前复权' if adjust == 'qfq' else adjust
            return df
        except Exception:
            logger.warning("加载离线缓存失败: %s", self._offline_cache_file, exc_info=True)
            return None

    def get_stock_data(self, symbol, period="1y", interval="1d", market="US", use_cache=True, adjust=""):
        """获取股票历史数据 - 带重试机制、数据源追踪、离线模式"""
        cache_key = f"{symbol}_{period}_{interval}_{market}_{adjust or 'raw'}"

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
            result_source_name = None
            offline_mode = False

            if market == "CN":
                # A股数据获取：始终构建完整回退链，按用户偏好排序
                all_sources = [
                    ('mootdx', self._get_cn_stock_data_mootdx, '通达信mootdx'),
                    ('ths', self._get_cn_stock_data_ths, '同花顺'),
                    ('akshare', self._get_cn_stock_data_akshare, '腾讯财经'),
                    ('akshare_em', self._get_cn_stock_data_akshare_em, '东方财富'),
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
                stale_result = None
                stale_source_name = None
                for source_name, source_func in sources_to_try:
                    try:
                        if adjust:
                            result = self._retry_with_backoff(
                                lambda source_symbol, source_period, func=source_func: func(
                                    source_symbol,
                                    source_period,
                                    adjust=adjust,
                                ),
                                source_name,
                                symbol,
                                period,
                            )
                        else:
                            result = self._retry_with_backoff(source_func, source_name, symbol, period)
                        if result is not None and len(result) >= 10:
                            if not self._is_cn_daily_kline_fresh(result):
                                if stale_result is None:
                                    stale_result = result
                                    stale_source_name = source_name
                                logger.info(
                                    "%s A股日K滞后，继续尝试下一个真实日K源: symbol=%s last=%s",
                                    source_name,
                                    symbol,
                                    result.index[-1] if isinstance(result.index, pd.DatetimeIndex) else None,
                                )
                                continue
                            data_source = {
                                'mootdx': '通达信mootdx',
                                'ths': '同花顺',
                                'akshare_em': '东方财富',
                                'akshare': '腾讯财经',
                                'sina': '新浪财经',
                                'yfinance': 'Yahoo Finance'
                            }.get(source_name, source_name)
                            result_source_name = source_name
                            break
                    except Exception as e:
                        logger.info("%s 获取失败: %s", source_name, e)
                else:
                    result = None

                if result is None and stale_result is not None:
                    result = stale_result
                    data_source = {
                        'mootdx': '通达信mootdx',
                        'ths': '同花顺',
                        'akshare_em': '东方财富',
                        'akshare': '腾讯财经',
                        'sina': '新浪财经',
                        'yfinance': 'Yahoo Finance'
                    }.get(stale_source_name, stale_source_name)
                    result_source_name = stale_source_name
                    result.attrs['source_note'] = "当前数据源未返回最新交易日日K，暂显示最后可用真实日K"

                # 所有在线源失败，尝试离线缓存
                if result is None:
                    result = self._load_offline_cache(symbol, adjust=adjust)
                    if result is not None:
                        data_source = result.attrs.get('data_source', '离线缓存')
                        offline_mode = True

            elif market == "HK":
                # 港股：Yahoo Finance 历史K线（国内可直连），新浪实时行情
                result = self._retry_with_backoff(
                    lambda s, p: YahooKlineProvider(yf).fetch(s, p, interval=interval, market="HK"),
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
                        lambda s, p: YahooKlineProvider(yf).fetch(s, p, interval=interval, market="US"),
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
                logger.info("未找到股票 %s 的数据", symbol)
                return None

            if isinstance(result, pd.DataFrame):
                result.columns = [col.lower().replace(' ', '_') for col in result.columns]
                # 添加数据源信息到DataFrame属性
                result.attrs['data_source'] = data_source or "未知"
                if data_source and not result.attrs.get('data_provider'):
                    result.attrs['data_provider'] = data_source
                if result_source_name and result_source_name != 'ths' and not result.attrs.get('source_note'):
                    result.attrs['source_note'] = "同花顺日K滞后时自动切换到可用真实日K源"
                result.attrs['offline_mode'] = offline_mode

                # 保存到离线缓存
                if not offline_mode:
                    self._save_offline_cache(symbol, result, adjust=adjust)

            self.cache[cache_key] = (datetime.now(), result, data_source)
            return result

    @staticmethod
    def _is_cn_daily_kline_fresh(data):
        """判断A股日K是否包含当前最新交易日；缺当天K线时继续尝试其它真实数据源。"""
        if data is None or data.empty or not isinstance(data.index, pd.DatetimeIndex):
            return False
        last_day = data.index.max().normalize()
        now = datetime.now()
        today = pd.Timestamp(now.date())
        if today.weekday() >= 5:
            return True
        if now.hour < 15:
            return True
        return last_day >= today

    def _get_us_stock_data_sina(self, symbol, period, **kwargs):
        try:
            return SinaDailyKlineProvider(_session).fetch_us(symbol, period)
        except Exception as e:
            logger.info("新浪美股历史数据获取失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_ths(self, symbol, period, **kwargs):
        try:
            return ThsDailyKlineProvider(_session).fetch(symbol, period, adjust=kwargs.get("adjust") or "")
        except Exception as e:
            logger.info("同花顺日K获取失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_mootdx(self, symbol, period, **kwargs):
        try:
            return MootdxDailyKlineProvider().fetch(symbol, period, adjust=kwargs.get("adjust") or "")
        except Exception as e:
            logger.info("mootdx日K获取失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_akshare_em(self, symbol, period, **kwargs):
        if not AKSHARE_AVAILABLE:
            return None
        try:
            return AkshareDailyKlineProvider(ak).fetch_eastmoney(symbol, period, adjust=kwargs.get("adjust") or "")
        except Exception as e:
            logger.info("AKShare(东方财富)获取失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_akshare(self, symbol, period, **kwargs):
        if not AKSHARE_AVAILABLE:
            return None
        try:
            return AkshareDailyKlineProvider(ak).fetch_tencent(symbol, period, adjust=kwargs.get("adjust") or "")
        except Exception as e:
            logger.info("AKShare获取失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_sina_fallback(self, symbol, period, **kwargs):
        try:
            return SinaDailyKlineProvider(_session).fetch_cn(symbol, period)
        except Exception as e:
            if is_timeout_error(e):
                logger.info("新浪财经请求超时 symbol=%s", symbol)
            elif is_request_error(e):
                logger.info("新浪财经网络错误 symbol=%s error=%s", symbol, e)
            else:
                logger.info("新浪财经失败 symbol=%s error=%s", symbol, e)
        return None

    def _get_cn_stock_data_yfinance(self, symbol, period, **kwargs):
        try:
            return YahooKlineProvider(yf).fetch_cn_with_retry(symbol, period)
        except Exception as e:
            logger.info("yfinance获取失败 symbol=%s error=%s", symbol, e)
        return None

    def get_stock_info(self, symbol, market="US"):
        """获取股票基本信息"""
        # A股直接返回映射表中的名称
        if market == "CN":
            name = CN_STOCK_NAMES_EXTENDED.get(symbol)
            if name:
                return {'shortName': name, 'symbol': symbol}

        def _fetch_info():
            return YahooQuoteProvider(yf).fetch_info(symbol, market)

        info = self._retry_with_backoff(_fetch_info, 'yfinance')
        if info is None:
            return {'shortName': symbol, 'symbol': symbol}
        return info

    def get_stock_name(self, symbol, market="US"):
        if market == "CN":
            name = SinaRealtimeProvider(_session).fetch_cn_name(symbol)
            if name:
                return name
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

            # 第三优先：查全量名称索引缓存
            index_name = self._get_name_from_index(symbol)
            if index_name:
                return index_name

            # 第四优先：AKShare 全市场快照（慢，但覆盖全）
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

    def resolve_stock_input(self, text, market="CN"):
        """解析用户输入（股票代码或名称），返回 (code, name) 或 None

        支持：
        - 6位代码 → 直接返回
        - 中文名称（精确/模糊匹配）→ 返回对应代码
        """
        text = text.strip()
        if not text:
            return None

        # 已经是代码
        if market == "CN" and text.isdigit() and len(text) == 6:
            name = CN_STOCK_NAMES_EXTENDED.get(text) or self._get_name_from_index(text) or text
            return (text, name)

        # 非CN市场不支持名称搜索
        if market != "CN":
            return None

        # 含中文字符 → 按名称搜索
        if not any('一' <= c <= '鿿' for c in text):
            return None

        return self._resolve_cn_stock_name(text)

    @classmethod
    def _load_stock_name_index(cls, max_age_hours=24):
        """加载全量A股名称索引，优先磁盘缓存，过期后用 AKShare 轻量接口刷新。"""
        try:
            cached, _ = _read_json_cache(cls._stock_name_index_file)
            if cached:
                cache_time = datetime.fromisoformat(cached.get('updated', '2000-01-01'))
                stocks = cached.get('stocks', [])
                if datetime.now() - cache_time < timedelta(hours=max_age_hours) and stocks:
                    return stocks
        except Exception:
            logger.warning("读取股票名称索引缓存失败", exc_info=True)

        stocks = []
        if AKSHARE_AVAILABLE:
            try:
                df = ak.stock_info_a_code_name()
                for _, row in df.iterrows():
                    code = str(row.get('code', '')).strip()
                    name = str(row.get('name', '')).strip()
                    if re.fullmatch(r'\d{6}', code) and name:
                        stocks.append({'code': code, 'name': _clean_stock_name(name)})
                if stocks:
                    _ensure_parent_dir(cls._stock_name_index_file)
                    with open(cls._stock_name_index_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'updated': datetime.now().isoformat(),
                            'count': len(stocks),
                            'stocks': stocks,
                        }, f, ensure_ascii=False)
                    return stocks
            except Exception:
                logger.warning("刷新股票名称索引失败", exc_info=True)

        try:
            static_file = _static_data_path('stock_name_index.json')
            if os.path.exists(static_file):
                with open(static_file, 'r', encoding='utf-8') as f:
                    static_index = json.load(f)
                stocks = static_index.get('stocks', [])
                if stocks:
                    return stocks
        except Exception:
            logger.warning("读取内置股票名称索引失败", exc_info=True)

        return [{'code': code, 'name': name} for code, name in CN_STOCK_NAMES_EXTENDED.items()]

    @classmethod
    def _get_name_from_index(cls, symbol):
        for item in cls._load_stock_name_index():
            if item.get('code') == symbol:
                return _clean_stock_name(item.get('name'))
        return None

    def _resolve_cn_stock_name(self, text):
        """用全量名称索引解析 A 股中文名，失败时才进入慢网络行情快照。"""
        normalized_text = _normalize_stock_name(text)

        all_stocks = []
        seen_codes = set()
        for code, name in CN_STOCK_NAMES_EXTENDED.items():
            all_stocks.append({'code': code, 'name': name})
            seen_codes.add(code)

        for item in self._load_stock_name_index():
            code = item.get('code', '')
            if code and code not in seen_codes:
                all_stocks.append(item)
                seen_codes.add(code)

        for item in self.get_main_board_stocks():
            code = item.get('code', '')
            if code and code not in seen_codes:
                all_stocks.append({'code': code, 'name': _clean_stock_name(item.get('name', ''))})
                seen_codes.add(code)

        # 精确匹配
        for item in all_stocks:
            if _normalize_stock_name(item.get('name', '')) == normalized_text:
                return (item['code'], _clean_stock_name(item['name']))

        prefix_matches = []
        contains_matches = []
        for item in all_stocks:
            normalized_name = _normalize_stock_name(item.get('name', ''))
            if normalized_name.startswith(normalized_text):
                prefix_matches.append(item)
            elif normalized_text in normalized_name:
                contains_matches.append(item)

        if prefix_matches:
            match = sorted(prefix_matches, key=lambda item: len(item.get('name', '')))[0]
            return (match['code'], _clean_stock_name(match['name']))
        if contains_matches:
            match = sorted(contains_matches, key=lambda item: len(item.get('name', '')))[0]
            return (match['code'], _clean_stock_name(match['name']))

        fuzzy_matches = []
        if len(normalized_text) >= 3:
            for item in all_stocks:
                normalized_name = _normalize_stock_name(item.get('name', ''))
                similarity = _stock_name_similarity(normalized_text, normalized_name)
                if similarity >= 0.72:
                    fuzzy_matches.append((similarity, len(normalized_name), item))

        if fuzzy_matches:
            _, _, match = sorted(fuzzy_matches, key=lambda item: (-item[0], item[1]))[0]
            return (match['code'], _clean_stock_name(match['name']))

        # 兼容老缓存或轻量索引临时失败时的最后兜底
        return self._resolve_cn_stock_name_from_spot(text)

    def _resolve_cn_stock_name_from_spot(self, text):
        """从全市场行情快照兜底解析名称，可能较慢。"""
        normalized_text = _normalize_stock_name(text)

        # 全量快照搜索（覆盖5000+只股票），限时8秒，缓存命中直接返回
        spot_df = self._get_spot_snapshot(timeout=8)
        if spot_df is not None:
            def _strip_code(c):
                """去掉 sh/sz/bj 前缀，返回6位数字代码"""
                c = str(c)
                if c.startswith(('sh', 'sz', 'bj')) and len(c) >= 8:
                    return c[2:]
                return c

            # 精确匹配
            candidates = []
            for _, row in spot_df.iterrows():
                name = str(row['名称'])
                normalized_name = _normalize_stock_name(name)
                if normalized_name == normalized_text:
                    return (_strip_code(row['代码']), _clean_stock_name(name))
                if normalized_name.startswith(normalized_text):
                    candidates.append((0, len(name), row))
                elif normalized_text in normalized_name:
                    candidates.append((1, len(name), row))
            if candidates:
                _, _, row = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
                return (_strip_code(row['代码']), _clean_stock_name(row['名称']))

        return None

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
                quote = SinaRealtimeProvider(_session).fetch_cn_quote(symbol)
                if quote:
                    return quote
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
                                'volume': float(data[8]) / 100,
                                'volume_unit': 'hand',
                                'prev_close': float(data[2]),
                                'quote_date': data[30] if len(data) > 30 else None,
                                'quote_time': data[31] if len(data) > 31 else None,
                                'turnover_rate': None,
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
                            'volume': float(row['成交量']) / 100,
                            'volume_unit': 'hand',
                            'prev_close': float(row['昨收']),
                            'turnover_rate': float(row['换手率']) if '换手率' in row and pd.notna(row['换手率']) else None,
                            'change': (float(row['最新价']) / float(row['昨收']) - 1) * 100
                        }

                # 备选：使用yfinance
                quote = YahooQuoteProvider(yf).fetch_quote(symbol, "CN")
                if quote:
                    return quote

            elif market == "HK":
                # 港股实时行情：新浪财经优先
                quote = self._get_sina_realtime(symbol, "hk")
                if quote:
                    return quote
                # 备选：Yahoo Finance
                quote = YahooQuoteProvider(yf).fetch_quote(symbol, "HK")
                if quote:
                    return quote
            else:
                # 美股实时行情：新浪财经优先
                quote = self._get_sina_realtime(symbol, "us")
                if quote:
                    return quote
                # 备选：Yahoo Finance
                quote = YahooQuoteProvider(yf).fetch_quote(symbol, "US")
                if quote:
                    return quote

        except Exception:
            logger.warning("获取实时行情失败 symbol=%s market=%s", symbol, market, exc_info=True)
        return None

    def get_batch_realtime_quotes(self, symbols, market="CN"):
        """批量获取实时行情，优先新浪批量HTTP分片请求。
        返回 {symbol: {price, change_pct}}，查不到的 symbol 不在结果中
        """
        result = {}
        if not symbols or market != "CN":
            return result

        import concurrent.futures as _cf
        provider = SinaRealtimeProvider(_session)

        def _sina_code(symbol):
            if symbol.startswith('6'):
                prefix = 'sh'
            elif symbol.startswith('0') or symbol.startswith('3'):
                prefix = 'sz'
            elif symbol.startswith('4') or symbol.startswith('8'):
                prefix = 'bj'
            else:
                prefix = 'sz'
            return f"{prefix}{symbol}"

        def _parse_sina_quote(symbol, raw):
            if not raw:
                return None
            try:
                data = raw.split(',')
                if len(data) >= 33 and data[3]:
                    price = float(data[3])
                    prev_close = float(data[2])
                    return {
                        'symbol': symbol,
                        'name': data[0],
                        'price': price,
                        'open': float(data[1]),
                        'high': float(data[4]),
                        'low': float(data[5]),
                        'volume': int(float(data[8]) / 100),
                        'prev_close': prev_close,
                        'change_pct': round((price / prev_close - 1) * 100, 2),
                    }
            except Exception:
                logger.debug("新浪行情解析失败 symbol=%s", symbol, exc_info=True)
                return None
            return None

        def _fetch_chunk(chunk):
            chunk_result = {}
            try:
                chunk_result.update(provider.fetch_cn_batch_quotes(list(chunk)))
                if chunk_result:
                    return chunk_result
                code_to_symbol = {_sina_code(symbol): symbol for symbol in chunk}
                url = "https://hq.sinajs.cn/list=" + ",".join(code_to_symbol.keys())
                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = _session.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    for code, raw in re.findall(r'var hq_str_([a-z]{2}\d{6})="([^"]*)"', response.text):
                        symbol = code_to_symbol.get(code)
                        parsed = _parse_sina_quote(symbol, raw) if symbol else None
                        if parsed:
                            chunk_result[symbol] = parsed
            except Exception:
                pass
            return chunk_result

        def _fetch_one(symbol):
            try:
                url = f"https://hq.sinajs.cn/list={_sina_code(symbol)}"
                headers = {
                    'Referer': 'https://finance.sina.com.cn',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = _session.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    match = re.search(r'"([^"]*)"', response.text)
                    parsed = _parse_sina_quote(symbol, match.group(1) if match else "")
                    if parsed:
                        return symbol, parsed
            except Exception:
                logger.debug("新浪行情单只补拉失败 symbol=%s", symbol, exc_info=True)
            return symbol, None

        chunks = [symbols[i:i + 80] for i in range(0, len(symbols), 80)]
        with _cf.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch_chunk, chunk): chunk for chunk in chunks}
            for future in _cf.as_completed(futures, timeout=8):
                try:
                    result.update(future.result(timeout=5) or {})
                except Exception:
                    logger.debug("新浪行情分片结果读取失败 symbols=%s", futures[future], exc_info=True)
        missing_symbols = [symbol for symbol in symbols if symbol not in result]
        if missing_symbols:
            with _cf.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(_fetch_one, symbol): symbol for symbol in missing_symbols[:200]}
                for future in _cf.as_completed(futures, timeout=8):
                    try:
                        symbol, data = future.result(timeout=5)
                        if data is not None:
                            result[symbol] = data
                    except Exception:
                        logger.debug("新浪行情单只补拉结果读取失败 symbol=%s", futures[future], exc_info=True)
        return result

    def get_index_realtime(self, symbol):
        """获取A股指数实时行情

        Returns:
            dict: {symbol, name, price, change_pct, prev_close} 或 None
        """
        try:
            sina_result = self._get_index_realtime_sina(symbol, timeout=2)
            if sina_result:
                return sina_result

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
                except Exception:
                    logger.info("AKShare指数行情失败 symbol=%s", symbol, exc_info=True)

            # yfinance
            try:
                quote = YahooQuoteProvider(yf).fetch_index_quote(symbol)
                if quote:
                    return quote
            except Exception:
                logger.debug("Yahoo指数行情失败 symbol=%s", symbol, exc_info=True)

        except Exception:
            logger.warning("获取指数行情失败 symbol=%s", symbol, exc_info=True)
        return None

    def _get_index_realtime_sina(self, symbol, timeout=2):
        """新浪财经指数实时行情，作为大盘温度快速源。"""
        try:
            return SinaIndexRealtimeProvider(_session).fetch_quote(symbol, timeout=timeout)
        except Exception:
            logger.debug("新浪指数行情失败 symbol=%s", symbol, exc_info=True)
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
        except Exception:
            logger.info("AKShare指数快照失败", exc_info=True)
            return None

    def _get_sina_realtime(self, symbol, market):
        """新浪财经实时行情 — 支持 us / hk"""
        quote = SinaRealtimeProvider(_session).fetch_global_quote(symbol, market)
        if quote:
            return quote

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
        """获取当日分钟K线数据，用于分时图（仅A股，新浪优先，东方财富备用）。"""
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

    @staticmethod
    def _normalize_intraday_frame(df, *, source, interval):
        """统一分时字段和均价口径，避免成交量单位把均价线抬偏。"""
        if df is None or df.empty or 'time' not in df.columns:
            return None
        df = df.copy()
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        df = df.dropna(subset=['time'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'avg_price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        today = pd.Timestamp.now().date()
        df = df[df['time'].dt.date == today].copy()
        if df.empty:
            return None

        if 'volume' in df.columns:
            volume = df['volume'].fillna(0).astype(float)
            df['volume'] = volume
            df['volume_shares'] = volume * 100
        else:
            df['volume'] = 0.0
            df['volume_shares'] = 0.0

        if 'amount' in df.columns:
            amount = df['amount'].fillna(0).astype(float)
            denom = df['volume_shares'].cumsum().replace(0, float('nan'))
            calculated_avg = amount.cumsum() / denom
            close_median = df['close'].dropna().median() if 'close' in df.columns else None
            calculated_median = calculated_avg.dropna().median()
            if pd.notna(close_median) and pd.notna(calculated_median) and calculated_median > 0:
                ratio = close_median / calculated_median
                if 80 <= ratio <= 120:
                    calculated_avg = calculated_avg * 100
            if 'avg_price' not in df.columns or not df['avg_price'].notna().any():
                df['avg_price'] = calculated_avg
            else:
                avg = pd.to_numeric(df['avg_price'], errors='coerce')
                avg_median = avg.dropna().median()
                if pd.notna(close_median) and pd.notna(avg_median) and (avg_median > close_median * 3 or avg_median < close_median / 3):
                    df['avg_price'] = calculated_avg
                else:
                    df['avg_price'] = avg.fillna(calculated_avg)

        df = df.sort_values('time').reset_index(drop=True)
        df.attrs['data_source'] = source
        df.attrs['interval'] = interval
        df.attrs['volume_unit'] = 'hand'
        return df

    def _fetch_intraday_sina(self, symbol, cache_key):
        """新浪财经分钟数据（稳定，5分钟线，作为兜底源）"""
        try:
            provider = SinaIntradayProvider(_session)
            raw = provider.fetch_raw(symbol)
            df = self._normalize_intraday_frame(raw, source=provider.source, interval=provider.interval)
            if df is None:
                return None
            self.cache[cache_key] = (datetime.now(), df, f"{provider.source}{provider.interval}")
            return df
        except Exception:
            logger.debug("新浪分时数据获取失败: symbol=%s", symbol, exc_info=True)
        return None

    def _fetch_intraday_akshare(self, symbol, cache_key):
        """东方财富分钟数据（1分钟线，分时图优先源）"""
        try:
            provider = EastmoneyIntradayProvider(ak)
            raw = provider.fetch_raw(symbol)
            df = self._normalize_intraday_frame(raw, source=provider.source, interval=provider.interval)
            if df is None:
                return None
            self.cache[cache_key] = (datetime.now(), df, "东方财富1分钟")
            return df
        except Exception:
            logger.debug("东方财富分时数据获取失败: symbol=%s", symbol, exc_info=True)
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
        valid_sources = ['auto', 'ths', 'akshare_em', 'akshare', 'sina', 'yfinance']
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
        cache_file = cls._main_board_cache_file

        # 1. 尝试从缓存加载（24小时有效）
        try:
            cached, _ = _read_json_cache(cache_file, '.main_board_cache.json')
            if cached:
                cache_time = datetime.fromisoformat(cached.get('updated', '2000-01-01'))
                if datetime.now() - cache_time < timedelta(hours=24):
                    return cached['stocks']
        except Exception:
            logger.warning("读取主板股票池缓存失败", exc_info=True)

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
                    _ensure_parent_dir(cache_file)
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        _json.dump({
                            'updated': datetime.now().isoformat(),
                            'count': len(stocks),
                            'stocks': stocks
                        }, f, ensure_ascii=False)
                except Exception:
                    logger.warning("写入主板股票池缓存失败: %s", cache_file, exc_info=True)
        except Exception:
            logger.warning("刷新主板股票池失败", exc_info=True)

        return stocks


from stock_names import CN_STOCK_NAMES_EXTENDED, POPULAR_US_STOCKS

def _build_cn_stock_pool():
    """构建A股推荐池：优先加载磁盘缓存（24h有效），无缓存时退回静态映射表

    缓存文件由 StockDataFetcher.get_main_board_stocks() 在首次成功下载后写入。
    应用冷启动后缓存就已存在（除首次部署外），无需每次导入都下载全市场快照。
    """
    cache_file = StockDataFetcher._main_board_cache_file
    try:
        cached, _ = _read_json_cache(cache_file, '.main_board_cache.json')
        if cached:
            cache_time = datetime.fromisoformat(cached.get('updated', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(hours=24):
                stocks = cached.get('stocks', [])
                if stocks and len(stocks) >= 20:
                    return stocks
    except Exception:
        logger.warning("构建A股推荐池时读取缓存失败", exc_info=True)

    # 无缓存或缓存过期：退回静态映射表（首次部署时）
    return [{'code': code, 'name': name} for code, name in CN_STOCK_NAMES_EXTENDED.items()]

# 懒加载：避免导入时读取磁盘 JSON，首次调用 _build_cn_stock_pool() 时才加载
_POPULAR_CN_STOCKS = None


def get_popular_cn_stocks():
    """获取 A 股推荐池（懒加载 + 缓存）"""
    global _POPULAR_CN_STOCKS
    if _POPULAR_CN_STOCKS is None:
        _POPULAR_CN_STOCKS = _build_cn_stock_pool()
    return _POPULAR_CN_STOCKS

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
