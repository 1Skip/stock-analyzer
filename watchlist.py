"""
自选股管理模块
持久化到 watchlist.json，同时维护 session_state 缓存
"""
import streamlit as st
import json
import logging
import os

from data.file_lock import atomic_write_text, get_thread_lock, process_file_lock

_WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), 'watchlist.json')
logger = logging.getLogger(__name__)


# ============================================================
# 入场提示（纯计算，无网络请求）
# ============================================================

def get_entry_hint(price, indicators, signal_summary):
    """基于布林带位置和信号方向，生成入场提示

    Args:
        price: 当前价格
        indicators: dict, 至少含 boll_upper / boll_mid / boll_lower
        signal_summary: 信号综合建议（含"偏多"/"偏空"/"观望"）

    Returns:
        str: 入场提示文字
    """
    boll_upper = indicators.get('boll_upper')
    boll_mid = indicators.get('boll_mid')
    boll_lower = indicators.get('boll_lower')

    if boll_lower is None or boll_upper is None or boll_mid is None:
        return "数据不足"

    band_range = boll_upper - boll_lower
    if band_range <= 0:
        return "波动极小，观望"

    position = (price - boll_lower) / band_range  # 0=下轨, 1=上轨
    is_bullish = '偏多' in str(signal_summary)
    is_bearish = '偏空' in str(signal_summary)

    if position <= 0.05:
        return "接近支撑位，关注反弹"
    elif position <= 0.20:
        hint = "支撑位附近"
        if is_bullish:
            hint += "，信号偏多可关注"
        return hint
    elif position >= 0.95:
        return "接近压力位，不宜追高"
    elif position >= 0.80:
        hint = "压力位附近"
        if is_bearish:
            hint += "，注意风险"
        return hint
    elif 0.35 <= position <= 0.65:
        if is_bullish:
            return "中轨附近偏多，可考虑建仓"
        elif is_bearish:
            return "中轨附近偏空，等待企稳"
        else:
            return "中轨附近震荡，方向不明"
    elif position < 0.35:
        return "偏弱区间，等待金叉信号"
    else:
        return "偏强区间，注意高位风险"


# ============================================================
# 自选股批量摘要（数据获取 + 指标计算）
# ============================================================

def _fetch_single_stock(item):
    """获取单只股票的技术摘要（供并行调用）"""
    import pandas as _pd
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators

    symbol = item['symbol']
    name = item.get('name', symbol)
    market = item.get('market', 'CN')

    result = {
        'symbol': symbol,
        'name': name,
        'market': market,
        'price': None,
        'change_pct': None,
        'signal_summary': '--',
        'entry_hint': '--',
        'indicators': {},
        'error': None,
    }

    try:
        # 每个线程独立创建 fetcher 实例（线程安全）
        fetcher = StockDataFetcher()

        # 获取 3 个月历史数据用于指标计算
        df = fetcher.get_stock_data(symbol, period='3mo', market=market)
        if df is None or df.empty or len(df) < 10:
            result['error'] = '数据不足'
            return result

        # 计算技术指标
        df = TechnicalIndicators.calculate_all(df)
        signals = TechnicalIndicators.get_signals(df)

        # 最新数据
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest

        # 优先使用实时行情，拿不到再用 K 线收盘价
        try:
            quote = fetcher.get_realtime_quote(symbol, market)
            if quote and quote.get('price') is not None:
                result['price'] = float(quote['price'])
                result['change_pct'] = round(quote.get('change', 0), 2)
            else:
                raise ValueError("实时行情为空")
        except Exception:
            result['price'] = float(latest['close'])
            change_pct = (latest['close'] - prev['close']) / prev['close'] * 100 if prev['close'] != 0 else 0
            result['change_pct'] = round(change_pct, 2)
        result['signal_summary'] = signals.get('recommendation', signals.get('summary', '--'))

        # 提取指标快照
        indicators = {}
        for key in ('macd', 'macd_signal', 'rsi', 'kdj_k', 'kdj_d', 'kdj_j',
                    'boll_upper', 'boll_mid', 'boll_lower', 'ma5', 'ma10', 'ma20',
                    'main_accumulation', 'accumulation_risk', 'accumulation_trend'):
            val = latest.get(key)
            indicators[key] = round(float(val), 4) if val is not None and not (isinstance(val, float) and _pd.isna(val)) else None

        result['indicators'] = indicators

        # 生成入场提示
        if indicators['boll_upper'] is not None:
            result['entry_hint'] = get_entry_hint(
                result['price'], indicators, result['signal_summary'])

    except Exception as e:
        result['error'] = str(e)[:60]

    return result


def get_watchlist_summary(watchlist_items):
    """获取自选股列表中每只股票的技术摘要（并行获取）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not watchlist_items:
        return []

    # 并行获取，最多 8 个并发线程
    max_workers = min(len(watchlist_items), 8)
    results_map = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_fetch_single_stock, item): idx
            for idx, item in enumerate(watchlist_items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results_map[idx] = future.result()
            except Exception as e:
                item = watchlist_items[idx]
                results_map[idx] = {
                    'symbol': item['symbol'],
                    'name': item.get('name', item['symbol']),
                    'market': item.get('market', 'CN'),
                    'price': None,
                    'change_pct': None,
                    'signal_summary': '--',
                    'entry_hint': '--',
                    'indicators': {},
                    'error': str(e)[:60],
                }

    # 按原始顺序返回
    return [results_map[i] for i in range(len(watchlist_items))]


def _load_from_file():
    """从 JSON 文件加载自选股"""
    if not os.path.exists(_WATCHLIST_FILE):
        return []
    try:
        with get_thread_lock(_WATCHLIST_FILE):
            with open(_WATCHLIST_FILE, 'r', encoding='utf-8-sig') as f:
                payload = json.load(f)
        if not isinstance(payload, list):
            logger.warning(
                "自选股文件结构无效，按空列表处理: file=%s",
                os.path.basename(_WATCHLIST_FILE),
            )
            return []
        return payload
    except Exception as exc:
        logger.warning(
            "读取自选股文件失败，按空列表处理: file=%s error=%s",
            os.path.basename(_WATCHLIST_FILE),
            type(exc).__name__,
        )
        return []


def _save_to_file(watchlist):
    """原子保存自选股；失败时由调用方保留原 session 状态。"""
    try:
        content = json.dumps(watchlist, ensure_ascii=False, indent=2)
        with get_thread_lock(_WATCHLIST_FILE):
            with process_file_lock(_WATCHLIST_FILE):
                atomic_write_text(_WATCHLIST_FILE, content)
        try:
            file_mtime = os.path.getmtime(_WATCHLIST_FILE)
        except OSError as exc:
            logger.info(
                "自选股已保存但读取修改时间失败: file=%s error=%s",
                os.path.basename(_WATCHLIST_FILE),
                type(exc).__name__,
            )
            file_mtime = None
        st.session_state.watchlist_file_mtime = file_mtime
        return True
    except Exception as exc:
        logger.warning(
            "保存自选股文件失败: file=%s error=%s",
            os.path.basename(_WATCHLIST_FILE),
            type(exc).__name__,
        )
        return False


def _get_file_mtime():
    """读取自选股文件修改时间；异常时返回 None 并记录脱敏日志。"""
    if not os.path.exists(_WATCHLIST_FILE):
        return None
    try:
        return os.path.getmtime(_WATCHLIST_FILE)
    except OSError as exc:
        logger.warning(
            "读取自选股文件状态失败: file=%s error=%s",
            os.path.basename(_WATCHLIST_FILE),
            type(exc).__name__,
        )
        return None


def init_watchlist():
    """初始化自选股列表：文件变化时自动刷新 session_state。"""
    file_mtime = _get_file_mtime()
    if (
        'watchlist' not in st.session_state
        or st.session_state.get('watchlist_file_mtime') != file_mtime
    ):
        st.session_state.watchlist = _load_from_file()
        st.session_state.watchlist_file_mtime = file_mtime


def add_to_watchlist(symbol, name, market='CN'):
    """添加股票到自选股"""
    init_watchlist()
    for item in st.session_state.watchlist:
        if item['symbol'] == symbol and item['market'] == market:
            return False, "该股票已在自选股中"
    updated_watchlist = [*st.session_state.watchlist, {
        'symbol': symbol,
        'name': name,
        'market': market
    }]
    if not _save_to_file(updated_watchlist):
        return False, "保存失败，自选股未更改"
    st.session_state.watchlist = updated_watchlist
    return True, "添加成功"


def remove_from_watchlist(symbol, market='CN'):
    """从自选股中移除"""
    init_watchlist()
    updated_watchlist = [
        item for item in st.session_state.watchlist
        if not (item['symbol'] == symbol and item['market'] == market)
    ]
    if not _save_to_file(updated_watchlist):
        return False, "保存失败，自选股未更改"
    st.session_state.watchlist = updated_watchlist
    return True, "移除成功"


def get_watchlist():
    """获取自选股列表"""
    init_watchlist()
    return st.session_state.watchlist


def clear_watchlist():
    """清空自选股"""
    init_watchlist()
    if not _save_to_file([]):
        return False, "保存失败，自选股未更改"
    st.session_state.watchlist = []
    return True, "已清空"


def is_in_watchlist(symbol, market='CN'):
    """检查股票是否在自选股中"""
    init_watchlist()
    return any(
        item['symbol'] == symbol and item['market'] == market
        for item in st.session_state.watchlist
    )
