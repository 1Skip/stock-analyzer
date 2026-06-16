"""
热门股票和推荐股票模块
涨跌幅榜/行业/概念板块优先使用同花顺公开页，个股排行失败时回退新浪财经，港股美股使用yfinance
"""
import requests
import re
import yfinance as yf
import pandas as pd
import json
import os
import subprocess
import sys
import math
import io
import inspect
try:
    import akshare as ak
except Exception:  # pragma: no cover - depends on optional runtime package
    ak = None
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 导入热门股票列表
from data_fetcher import StockDataFetcher, get_popular_cn_stocks, POPULAR_US_STOCKS, POPULAR_HK_STOCKS
from stock_names import CN_STOCK_NAMES_EXTENDED
from stock_names import SECTOR_STOCKS
from technical_indicators import TechnicalIndicators
from data.services.info_service import StockInfoService
from data.services.fundamental_service import FundamentalDataService
from data.providers.akshare_provider import _find_profile_index_item
from recommendation_modules import auxiliary_data, board_rankings, hot_stocks, market_rankings, strategy_cache
from config import CACHE_TTL_STRATEGY_KLINE, RUNTIME_CACHE_DIR

# 板块股票定义 - 短线龙头股
# 评分权重配置
_STANDARD_WEIGHTS = {
    'macd': [("金叉", 15), ("多头", 10), ("死叉", -10)],
    'rsi': [(30, 15), (40, 10), (70, -10), (60, -5)],
    'kdj': [("强金叉", 20), ("金叉", 15), ("超卖", 10), ("强死叉", -20), ("死叉", -15), ("超买", -10)],
    'boll': [("反弹", 15), ("偏多", 10), ("回调", -10), ("偏空", -5)],
    'ma': ('ma5', 'ma20', 10, 10),  # (short, long, cross_bonus, trend_bonus)
}

_SHORT_TERM_WEIGHTS = {
    'macd': [("金叉", 10), ("多头", 5), ("死叉", -15)],
    'rsi': [(25, 25), (35, 20), (45, 10), (75, -15), (65, -10)],
    'kdj': [("强金叉", 30), ("金叉", 25), ("超卖", 20), ("强死叉", -30), ("死叉", -25), ("超买", -20)],
    'boll': [("反弹", 20), ("偏多", 10), ("回调", -15), ("偏空", -10)],
    'ma': ('ma5', 'ma10', 15, 15),
}

_LONG_TERM_WEIGHTS = {
    'macd': [("金叉", 20), ("多头", 12), ("死叉", -15)],
    'rsi': [(30, 10), (40, 8), (50, 5), (70, -8), (60, -5)],
    'kdj': [("强金叉", 15), ("金叉", 10), ("超卖", 8), ("强死叉", -15), ("死叉", -10), ("超买", -8)],
    'boll': [("反弹", 12), ("偏多", 8), ("回调", -10), ("偏空", -5)],
    'ma': ('ma20', 'ma60', 15, 15),
}

MAX_STRATEGY_MARKET_CAP = 30_000_000_000
STRATEGY_KLINE_CACHE_DIR = os.path.join(RUNTIME_CACHE_DIR, "strategy_kline_daily")
POSITIVE_CATALYST_KEYWORDS = [
    "政策", "订单", "业绩", "回购", "增持", "合同", "机构覆盖",
]
RISK_CATALYST_KEYWORDS = [
    "减持", "处罚", "诉讼", "亏损", "退市风险",
]


def _score_from_signals(signals, latest, weights):
    """通用信号评分：根据 weights 配置计算信号得分"""
    score = 50

    # MACD
    for keyword, delta in weights['macd']:
        if keyword in signals['macd']:
            score += delta
            break

    # RSI（值越低越超卖，值越高越超买）
    rsi = latest['rsi']
    for threshold, delta in weights['rsi']:
        if delta > 0 and rsi < threshold:
            score += delta
            break
        if delta < 0 and rsi > threshold:
            score += delta
            break

    # KDJ
    for keyword, delta in weights['kdj']:
        if keyword.startswith("强"):
            cond = keyword[1:]
            if "强" in signals['kdj'] and cond in signals['kdj']:
                score += delta
                break
        else:
            if keyword in signals['kdj']:
                score += delta
                break

    # BOLL
    for keyword, delta in weights['boll']:
        if keyword in signals['boll']:
            score += delta
            break

    # MA 趋势
    ma_short, ma_long, cross_bonus, _ = weights['ma']
    if ma_short in latest.index and ma_long in latest.index:
        if latest[ma_short] > latest[ma_long]:
            score += cross_bonus
        else:
            score -= cross_bonus

    return score


def _score_rating(score):
    """评分→评级（使用 config.py 的 RATING_THRESHOLDS）"""
    if score >= 80:
        return "偏多信号（强）"
    if score >= 65:
        return "偏多信号"
    if score >= 50:
        return "观望"
    if score >= 35:
        return "偏空信号"
    return "偏空信号（强）"


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _metric_value(metrics, aliases):
    for alias in aliases:
        for key, value in (metrics or {}).items():
            if alias == str(key) or alias in str(key):
                numeric = _safe_float(value)
                if numeric is not None:
                    return numeric
    return None


def _recent_items(items, days=2):
    if not items:
        return []
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    recent = []
    for item in items:
        raw_date = item.get("date") or item.get("announcement_date") or item.get("time")
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if pd.notna(parsed) and parsed.normalize() >= cutoff:
            recent.append(item)
    return recent


def _classify_catalyst_item(item):
    text = " ".join(str(item.get(key) or "") for key in ("title", "summary", "type", "rating"))
    risk_hits = [keyword for keyword in RISK_CATALYST_KEYWORDS if keyword in text]
    positive_hits = [keyword for keyword in POSITIVE_CATALYST_KEYWORDS if keyword in text]
    if risk_hits:
        return "风险", risk_hits
    if positive_hits:
        return "偏利好", positive_hits
    return "中性", []


def _format_catalyst_item(item):
    title = str(item.get("title") or item.get("summary") or "").strip()
    if not title:
        return ""
    date = str(item.get("date") or item.get("announcement_date") or item.get("time") or "").strip()
    source = str(item.get("source") or item.get("org") or item.get("type") or "").strip()
    sentiment, keywords = _classify_catalyst_item(item)
    prefix = f"{date} " if date else ""
    suffix_parts = [part for part in [source, sentiment, "/".join(keywords)] if part]
    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
    return f"{prefix}{title}{suffix}"


def _emit_progress(progress_callback, stage, percent, **metrics):
    if not callable(progress_callback):
        return
    try:
        progress_callback(stage, percent, metrics)
    except Exception:
        pass


def _safe_extended_info_failure(symbol, reason):
    return {
        "symbol": symbol,
        "financial": {},
        "fund_flow": {},
        "news": [],
        "market_news": [],
        "research": {"reports": [], "eps_consensus": {}},
        "risk_events": {"lhb": {}, "restricted_release": [], "announcements": []},
        "status": "source_failed",
        "reason": reason,
    }


def _has_usable_extended_layer(value):
    if not isinstance(value, dict) or not value:
        return False
    if value.get("status") in {"source_failed", "source_empty"}:
        return False
    return True


def _sanitize_for_json(value):
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if value is not None and not isinstance(value, (str, bytes, list, dict, tuple)):
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
    return value


def _fetch_extended_info_subprocess(symbol, market='CN', timeout_seconds=18):
    script = """
import json
import sys
from data.services.info_service import StockInfoService

symbol = sys.argv[1]
market = sys.argv[2]
payload = StockInfoService().get_stock_extended_info(symbol, market, include_deep_layers=True) or {}
print(json.dumps(payload, ensure_ascii=False, default=str))
"""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(symbol), str(market)],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        return _safe_extended_info_failure(symbol, "扩展数据子进程超时")
    except Exception as exc:
        return _safe_extended_info_failure(symbol, f"扩展数据子进程启动失败: {exc}")

    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout or f"退出码 {completed.returncode}").strip()
        return _safe_extended_info_failure(symbol, reason[:300])

    output = (completed.stdout or "").strip().splitlines()
    for line in reversed(output):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return _safe_extended_info_failure(symbol, "扩展数据子进程未返回JSON")


def _fetch_tencent_market_cap(symbol, timeout_seconds=2):
    return auxiliary_data.fetch_tencent_market_cap(
        symbol,
        requests_module=requests,
        safe_float=_safe_float,
        timeout_seconds=timeout_seconds,
    )


class StockRecommender:
    """股票推荐器"""

    def __init__(self):
        self._fundamental_service = FundamentalDataService()
        self._stock_info_service = StockInfoService()
        self.last_aggressive_diagnostics = {}
        self.last_multi_factor_diagnostics = {}

    def _merge_realtime_quote(self, data, fetcher, symbol, market, quote=None):
        """合并实时行情到最后一根K线"""
        try:
            data = self._drop_weekend_bars(data)
            quote = quote or fetcher.get_realtime_quote(symbol, market)
            if quote and quote.get('price'):
                today = pd.Timestamp.now().normalize()
                if data.index[-1].normalize() == today:
                    idx = data.index[-1]
                    data.loc[idx, 'close'] = quote['price']
                    data.loc[idx, 'high'] = max(data.loc[idx, 'high'], quote['high'])
                    data.loc[idx, 'low'] = min(data.loc[idx, 'low'], quote['low'])
                else:
                    if today.weekday() >= 5:
                        return data
                    if quote.get('volume', 0) <= 0:
                        return data
                    realtime_row = pd.DataFrame({
                        'open': [quote.get('open', quote['price'])],
                        'high': [quote.get('high', quote['price'])],
                        'low': [quote.get('low', quote['price'])],
                        'close': [quote['price']],
                        'volume': [quote.get('volume', 0)]
                    }, index=[pd.Timestamp.now()])
                    data = pd.concat([data, realtime_row])
        except Exception:
            pass
        return data

    @staticmethod
    def _drop_weekend_bars(data):
        """A股策略不使用周六/周日K线，避免非交易日实时价污染技术指标。"""
        if data is None or getattr(data, "empty", True):
            return data
        if not isinstance(data.index, pd.DatetimeIndex):
            return data
        filtered = data[data.index.dayofweek < 5].copy()
        if filtered.empty:
            return data
        filtered.attrs.update(getattr(data, "attrs", {}))
        return filtered

    @staticmethod
    def _strategy_cache_trade_date():
        return strategy_cache.strategy_cache_trade_date()

    @staticmethod
    def _strategy_kline_cache_path(cache_key):
        return strategy_cache.strategy_kline_cache_path(cache_key)

    def _load_strategy_kline_cache(self, cache_key):
        return strategy_cache.load_strategy_kline_cache(self, cache_key)

    def _get_strategy_stock_data(self, symbol, period='3mo', interval='1d', market='CN', fetcher=None):
        return strategy_cache.get_strategy_stock_data(
            self,
            symbol,
            period=period,
            interval=interval,
            market=market,
            fetcher=fetcher,
        )

    def _save_strategy_kline_cache(self, cache_key, data):
        return strategy_cache.save_strategy_kline_cache(cache_key, data)

    def refresh_strategy_kline_cache(self, stocks=None, period='3mo', interval='1d', market='CN', max_workers=8):
        return strategy_cache.refresh_strategy_kline_cache(
            self,
            stocks=stocks,
            period=period,
            interval=interval,
            market=market,
            max_workers=max_workers,
        )

    def _build_indicators_dict(self, latest):
        """从最新一行数据构建标准化指标字典"""
        return {
            'macd': round(latest['macd'], 3),
            'macd_signal': round(latest['macd_signal'], 3),
            'macd_hist': round(latest['macd_hist'], 3),
            'rsi': round(latest['rsi'], 2),
            'rsi_6': round(latest['rsi_6'], 2),
            'rsi_12': round(latest['rsi_12'], 2),
            'rsi_24': round(latest['rsi_24'], 2),
            'kdj_k': round(latest['kdj_k'], 2),
            'kdj_d': round(latest['kdj_d'], 2),
            'kdj_j': round(latest['kdj_j'], 2),
            'boll_upper': round(latest['boll_upper'], 2),
            'boll_mid': round(latest['boll_mid'], 2),
            'boll_lower': round(latest['boll_lower'], 2),
            'main_accumulation': round(latest.get('main_accumulation', 0), 2),
            'accumulation_risk': round(latest.get('accumulation_risk', 0), 2),
            'accumulation_trend': round(latest.get('accumulation_trend', 0), 2),
        }

    def get_hot_stocks_cn(self, limit=20):
        stocks = self._get_main_board_popular_cn_stocks(max(limit, 30))
        return hot_stocks.hot_stocks_cn(stocks, requests_module=requests, limit=limit)

    def get_hot_sectors_cn(self, limit=30):
        return board_rankings.hot_sectors(self, limit)

    def _get_hot_sectors_ths_html(self, limit=30):
        sectors = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            page = 1
            while len(sectors) < limit:
                url = f'https://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/'
                resp = requests.get(url, headers=headers, timeout=10)
                resp.encoding = 'gbk'
                soup = BeautifulSoup(resp.text, 'html.parser')
                table = soup.find('table', class_='m-table')
                if not table:
                    break
                rows = table.find_all('tr')[1:]  # 跳过表头
                if not rows:
                    break
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 12:
                        continue
                    try:
                        sectors.append({
                            '板块': cols[1].get_text(strip=True),
                            '涨跌幅': round(float(cols[2].get_text(strip=True).replace('%', '')), 2),
                            '领涨股': cols[9].get_text(strip=True),
                            '领涨股价格': round(float(cols[10].get_text(strip=True)), 2),
                            '领涨股涨幅': round(float(cols[11].get_text(strip=True).replace('%', '')), 2),
                            '上涨家数': int(cols[6].get_text(strip=True)),
                            '下跌家数': int(cols[7].get_text(strip=True)),
                            '总成交额(亿)': round(float(cols[4].get_text(strip=True)), 2),
                            '净流入(亿)': round(float(cols[5].get_text(strip=True)), 2),
                            '数据源': '同花顺行业板块',
                        })
                    except (ValueError, IndexError):
                        continue
                page += 1
                if page > 10:  # 安全上限
                    break
            return sectors[:limit]
        except Exception as e:
            print(f"获取行业板块排行失败: {e}")
            return sectors if sectors else []

    def get_hot_concepts_cn(self, limit=30):
        return board_rankings.hot_concepts(self, limit)

    def _get_hot_concepts_ths_html(self, limit=30):
        """同花顺概念资金流向，全量抓取后按涨跌幅排序。
        注意：同花顺web端概念板块页面(/gn/)是大事记而非排行，
        概念排行数据从概念资金流向页面抓取后客户端排序。
        """
        concepts = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            # 先获取首页确定总页数
            url = 'https://data.10jqka.com.cn/funds/gnzjl/order/desc/page/1/'
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'gbk'
            soup = BeautifulSoup(resp.text, 'html.parser')
            page_info = soup.find('span', class_='page_info')
            total_pages = 8  # 默认
            if page_info:
                match = re.search(r'/(\d+)', page_info.get_text(strip=True))
                if match:
                    total_pages = int(match.group(1))

            for page in range(1, total_pages + 1):
                if len(concepts) >= limit:
                    break
                if page > 1:
                    url = f'https://data.10jqka.com.cn/funds/gnzjl/order/desc/page/{page}/'
                    resp = requests.get(url, headers=headers, timeout=10)
                    resp.encoding = 'gbk'
                    soup = BeautifulSoup(resp.text, 'html.parser')
                table = soup.find('table')
                if not table:
                    break
                for row in table.find_all('tr')[1:]:  # 跳过表头
                    cols = row.find_all('td')
                    if len(cols) < 11:
                        continue
                    try:
                        change_str = cols[3].get_text(strip=True).replace('%', '')
                        lead_change_str = cols[9].get_text(strip=True).replace('%', '')
                        concepts.append({
                            '板块': cols[1].get_text(strip=True),
                            '涨跌幅': round(float(change_str), 2),
                            '领涨股': cols[8].get_text(strip=True),
                            '领涨股价格': round(float(cols[10].get_text(strip=True)), 2),
                            '领涨股涨幅': round(float(lead_change_str), 2),
                            '上涨家数': 0,
                            '下跌家数': 0,
                            '总成交额(亿)': 0,
                            '净流入(亿)': round(float(cols[6].get_text(strip=True)), 2),
                            '数据源': '同花顺概念资金流',
                        })
                    except (ValueError, IndexError):
                        continue

            # 按涨跌幅降序排列（资金流向页默认按主力资金排序）
            concepts.sort(key=lambda x: x['涨跌幅'], reverse=True)
            return concepts[:limit]
        except Exception as e:
            print(f"获取概念板块排行失败: {e}")
            return concepts if concepts else []

    def _get_hot_sectors_akshare_em(self, limit=30):
        return self._normalize_akshare_board_ranking(
            lambda: ak.stock_board_industry_name_em() if ak else None,
            limit,
            source='东方财富行业板块',
        )

    def _get_hot_sectors_akshare_ths(self, limit=30):
        return self._normalize_akshare_board_ranking(
            lambda: ak.stock_board_industry_name_ths() if ak else None,
            limit,
            source='同花顺行业板块AKShare',
        )

    def _get_hot_concepts_akshare_em(self, limit=30):
        return self._normalize_akshare_board_ranking(
            lambda: ak.stock_board_concept_name_em() if ak else None,
            limit,
            source='东方财富概念板块',
        )

    def _get_hot_concepts_akshare_ths(self, limit=30):
        return self._normalize_akshare_board_ranking(
            lambda: ak.stock_board_concept_name_ths() if ak else None,
            limit,
            source='同花顺概念板块AKShare',
        )

    def _normalize_akshare_board_ranking(self, fetcher, limit=30, source='AKShare板块'):
        if ak is None:
            return []
        try:
            df = fetcher()
            if df is None or df.empty:
                return []
            rows = []
            for _, row in df.head(max(limit, 30)).iterrows():
                name = self._first_board_value(row, ['板块名称', '行业名称', '概念名称', '名称'])
                if not name:
                    continue
                rows.append({
                    '板块': str(name),
                    '涨跌幅': self._safe_board_float(self._first_board_value(row, ['涨跌幅', '涨跌幅%', '最新涨跌幅'])),
                    '领涨股': str(self._first_board_value(row, ['领涨股票', '领涨股', '龙头股']) or ''),
                    '领涨股价格': self._safe_board_float(self._first_board_value(row, ['领涨股最新价', '领涨股价格', '最新价'])),
                    '领涨股涨幅': self._safe_board_float(self._first_board_value(row, ['领涨股涨跌幅', '领涨股涨幅'])),
                    '上涨家数': int(self._safe_board_float(self._first_board_value(row, ['上涨家数', '上涨数'])) or 0),
                    '下跌家数': int(self._safe_board_float(self._first_board_value(row, ['下跌家数', '下跌数'])) or 0),
                    '总成交额(亿)': self._safe_board_money_yi(self._first_board_value(row, ['成交额', '总成交额'])),
                    '净流入(亿)': self._safe_board_money_yi(self._first_board_value(row, ['净流入', '主力净流入', '资金净流入'])),
                    '数据源': source,
                })
            rows.sort(key=lambda item: item['涨跌幅'] if item['涨跌幅'] is not None else -999, reverse=True)
            return rows[:limit]
        except Exception as e:
            print(f"{source}兜底失败: {e}")
            return []

    @staticmethod
    def _first_board_value(row, candidates):
        for candidate in candidates:
            for key, value in row.items():
                if candidate == str(key) or candidate in str(key):
                    if pd.notna(value):
                        return value
        return None

    @staticmethod
    def _safe_board_float(value):
        try:
            if value is None or value == '':
                return None
            text = str(value).replace('%', '').replace(',', '').strip()
            return round(float(text), 2)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _safe_board_money_yi(cls, value):
        numeric = cls._safe_board_float(value)
        if numeric is None:
            return 0
        text = str(value)
        if '亿' in text:
            return numeric
        if '万' in text:
            return round(numeric / 10000, 2)
        if abs(numeric) > 1000000:
            return round(numeric / 100000000, 2)
        return numeric

    @staticmethod
    def _is_main_board(code):
        """判断是否为沪深主板股票（排除创业板/科创板/北交所）"""
        return code.startswith(('600', '601', '603', '605',     # 沪市主板
                                '000', '001', '002', '003'))    # 深市主板

    @staticmethod
    def _is_recommendable_board(code):
        """智能推荐股票池：沪深主板 + 创业板，排除科创板/北交所/ST。"""
        return str(code).startswith((
            '600', '601', '603', '605',
            '000', '001', '002', '003',
            '300', '301',
        ))

    @staticmethod
    def _board_label(code):
        code = str(code)
        if code.startswith(('300', '301')):
            return '创业板'
        if code.startswith('6'):
            return '沪市主板'
        return '深市主板'

    def _get_main_board_popular_cn_stocks(self, limit=None):
        """获取主板推荐股票池，过滤创业板、科创板和北交所。"""
        stocks = [s for s in get_popular_cn_stocks() if self._is_main_board(s['code'])]
        return stocks[:limit] if limit else stocks

    def _get_main_board_sector_stocks(self, sector_name):
        """获取指定板块的主板股票池，过滤创业板、科创板和北交所。"""
        return [s for s in SECTOR_STOCKS.get(sector_name, []) if self._is_main_board(s['code'])]

    def _get_strategy_popular_cn_stocks(self, limit=None):
        """获取策略推荐股票池：沪深主板 + 创业板，优先使用全量A股名称索引。"""
        merged = {s['code']: s for s in get_popular_cn_stocks()}
        try:
            for item in StockDataFetcher._load_stock_name_index(max_age_hours=48):
                code = str(item.get('code', '')).strip()
                name = str(item.get('name', '')).strip()
                if code and name:
                    merged.setdefault(code, {'code': code, 'name': name})
        except Exception:
            pass
        for code, name in CN_STOCK_NAMES_EXTENDED.items():
            merged.setdefault(code, {'code': code, 'name': name})
        stocks = [
            s for s in merged.values()
            if self._is_recommendable_board(s['code']) and 'ST' not in str(s.get('name', '')).upper()
        ]
        return stocks[:limit] if limit else stocks

    def _get_strategy_sector_stocks(self, sector_name):
        """获取指定板块策略股票池：沪深主板 + 创业板。"""
        return [
            s for s in SECTOR_STOCKS.get(sector_name, [])
            if self._is_recommendable_board(s['code']) and 'ST' not in str(s.get('name', '')).upper()
        ]

    # 行业缓存（东方财富F10 API，首次查询后复用）
    _sector_cache = {}

    @classmethod
    def _get_stock_sector(cls, code):
        return auxiliary_data.stock_sector(code, cache=cls._sector_cache, requests_module=requests)

    def _get_market_ranking_ths(self, sort_asc=False, limit=10, enrich_sector=True):
        """获取同花顺全市场涨跌幅榜（公开页，含沪深京）。"""
        try:
            order = "asc" if sort_asc else "desc"
            url = f'https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/{order}/page/1/ajax/1/'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://q.10jqka.com.cn/',
            }
            resp = requests.get(url, params=None, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []
            resp.encoding = 'gbk'
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table')
            if not table:
                return []
            results = []
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 6:
                    continue
                try:
                    code = cols[1].get_text(strip=True)
                    name = cols[2].get_text(strip=True)
                    if not code or not name:
                        continue
                    results.append({
                        '代码': code,
                        '名称': name,
                        '最新价': round(float(cols[3].get_text(strip=True)), 2),
                        '涨跌幅': round(float(cols[4].get_text(strip=True).replace('%', '')), 2),
                        '换手率': round(float(cols[8].get_text(strip=True).replace('%', '')), 2) if len(cols) > 8 and cols[8].get_text(strip=True) else None,
                    })
                except (ValueError, TypeError, IndexError):
                    continue
                if len(results) >= limit:
                    break
            for item in results:
                item['所属板块'] = self._get_stock_sector(item['代码']) if enrich_sector else item.get('所属板块', '')
            return results
        except Exception:
            return []

    def _get_market_ranking_sina(self, sort_asc=False, limit=10, enrich_sector=True):
        """获取新浪财经全市场涨跌幅榜（兜底源，沪深京全市场）。"""
        try:
            url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
            params = {
                'page': 1,
                'num': min(limit + 20, 80),
                'sort': 'changepercent',
                'asc': 1 if sort_asc else 0,
                'node': 'hs_a',
                'symbol': '',
                '_s_r_a': 'init',
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []
            resp.encoding = 'gbk'
            data = resp.json()
            if not isinstance(data, list):
                return []
            results = []
            for item in data:
                try:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    if not code or not name:
                        continue
                    turnover = item.get('turnoverratio')
                    results.append({
                        '代码': code,
                        '名称': name,
                        '最新价': round(float(item.get('trade', 0)), 2),
                        '涨跌幅': round(float(item.get('changepercent', 0)), 2),
                        '换手率': round(float(turnover), 2) if turnover and turnover != '0.0000' else None,
                    })
                except (ValueError, TypeError):
                    continue
                if len(results) >= limit:
                    break
            for s in results:
                s['所属板块'] = self._get_stock_sector(s['代码']) if enrich_sector else s.get('所属板块', '')
            return results
        except Exception:
            return []

    def _get_market_ranking(self, sort_asc=False, limit=10, enrich_sector=True):
        """获取全市场涨跌幅榜：同花顺优先，新浪兜底。"""
        return market_rankings.get_market_ranking(
            self,
            sort_asc=sort_asc,
            limit=limit,
            enrich_sector=enrich_sector,
        )

    def get_top_gainers_cn(self, limit=10):
        """获取A股全市场涨幅榜（同花顺实时排行）"""
        ranking = self._get_market_ranking(sort_asc=False, limit=limit + 5, enrich_sector=False)
        return market_rankings.top_gainers(ranking, limit)

    def get_top_losers_cn(self, limit=10):
        """获取A股全市场跌幅榜（同花顺实时排行）"""
        ranking = self._get_market_ranking(sort_asc=True, limit=limit + 5, enrich_sector=False)
        return market_rankings.top_losers(ranking, limit)

    def get_hot_stocks_hk(self, limit=20):
        return hot_stocks.hot_stocks_hk(POPULAR_HK_STOCKS, yf_module=yf, ak_module=ak, limit=limit)

    def get_top_gainers_hk(self, limit=10, hot_stocks=None):
        """获取港股涨幅榜（可传入预取的 hot_stocks 避免重复请求）"""
        stocks = hot_stocks if hot_stocks is not None else self.get_hot_stocks_hk(limit=30)
        gainers = [s for s in stocks if s['涨跌幅'] > 0]
        gainers.sort(key=lambda x: x['涨跌幅'], reverse=True)
        return gainers[:limit]

    def get_top_losers_hk(self, limit=10, hot_stocks=None):
        """获取港股跌幅榜（可传入预取的 hot_stocks 避免重复请求）"""
        stocks = hot_stocks if hot_stocks is not None else self.get_hot_stocks_hk(limit=30)
        losers = [s for s in stocks if s['涨跌幅'] < 0]
        losers.sort(key=lambda x: x['涨跌幅'])
        return losers[:limit]

    def get_top_gainers_us(self, limit=10, hot_stocks=None):
        """获取美股涨幅榜（可传入预取的 hot_stocks 避免重复请求）"""
        stocks = hot_stocks if hot_stocks is not None else self.get_hot_stocks_us(limit=30)
        gainers = [s for s in stocks if s['change'] > 0]
        gainers.sort(key=lambda x: x['change'], reverse=True)
        return gainers[:limit]

    def get_top_losers_us(self, limit=10, hot_stocks=None):
        """获取美股跌幅榜（可传入预取的 hot_stocks 避免重复请求）"""
        stocks = hot_stocks if hot_stocks is not None else self.get_hot_stocks_us(limit=30)
        losers = [s for s in stocks if s['change'] < 0]
        losers.sort(key=lambda x: x['change'])
        return losers[:limit]

    def get_hot_stocks_us(self, limit=20):
        return hot_stocks.hot_stocks_us(POPULAR_US_STOCKS, yf_module=yf, limit=limit)

    def analyze_stock(self, symbol, market='CN', period='3mo'):
        """
        分析单个股票的技术指标并评分
        """
        fetcher = StockDataFetcher()
        data = fetcher.get_stock_data(symbol, period='1y', market=market)

        if data is None or len(data) < 30:
            return None

        data = self._merge_realtime_quote(data, fetcher, symbol, market)

        # 计算指标
        df = TechnicalIndicators.calculate_all(data)
        signals = TechnicalIndicators.get_signals(df)

        if 'error' in signals:
            return None

        latest = df.iloc[-1]

        # 综合评分
        score = _score_from_signals(signals, latest, _STANDARD_WEIGHTS)
        score = max(0, min(100, score))

        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': _score_rating(score),
            'signals': signals,
            'latest_price': latest['close'],
            'indicators': self._build_indicators_dict(latest)
        }

    def get_recommended_stocks_hk(self, num_stocks=10):
        """
        获取港股推荐股票列表（基于技术分析）
        """
        results = []

        def analyze_one(stock):
            try:
                analysis = self.analyze_stock(stock['code'], market='HK', period='3mo')
                if analysis and analysis['score'] >= 60:
                    analysis['name'] = stock['name']
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_one, s): s for s in POPULAR_HK_STOCKS[:20]}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_recommended_stocks_us(self, num_stocks=10):
        """
        获取美股推荐股票列表（基于技术分析）
        """
        results = []

        def analyze_one(symbol):
            try:
                analysis = self.analyze_stock(symbol, market='US', period='3mo')
                if analysis and analysis['score'] >= 60:
                    analysis['name'] = symbol
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_one, s): s for s in POPULAR_US_STOCKS[:20]}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_recommended_stocks_cn(self, num_stocks=10):
        """
        获取推荐股票列表（基于技术分析）
        使用预设的热门股票池，并发分析加速
        """
        results = []

        def analyze_one(stock):
            try:
                analysis = self.analyze_stock(stock['code'], market='CN', period='3mo')
                if analysis and analysis['score'] >= 60:
                    analysis['name'] = stock['name']
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(analyze_one, s): s
                for s in self._get_main_board_popular_cn_stocks(20)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_short_term_recommendations(self, num_stocks=10):
        """
        获取短线推荐股票（基于短期动量指标），并发分析加速
        """
        results = []

        def analyze_one(stock):
            try:
                analysis = self._analyze_short_term(stock['code'], market='CN')
                if analysis:
                    analysis['name'] = stock['name']
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(analyze_one, s): s
                for s in self._get_main_board_popular_cn_stocks(25)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_long_term_recommendations(self, num_stocks=10):
        """
        获取长线推荐股票（基于1年趋势指标），并发分析加速
        """
        results = []

        def analyze_one(stock):
            try:
                analysis = self._analyze_long_term(stock['code'], market='CN')
                if analysis:
                    analysis['name'] = stock['name']
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(analyze_one, s): s
                for s in self._get_main_board_popular_cn_stocks(25)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_sector_short_term_recommendations(self, sector_name, num_stocks=5):
        """
        获取指定板块的短线龙头股推荐，并发分析加速
        """
        if sector_name not in SECTOR_STOCKS:
            return []

        results = []
        sector_stocks = self._get_main_board_sector_stocks(sector_name)

        def analyze_one(stock):
            try:
                analysis = self._analyze_short_term(stock['code'], market='CN')
                if analysis:
                    analysis['name'] = stock['name']
                    analysis['sector'] = sector_name
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_one, s): s for s in sector_stocks}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def _analyze_short_term(self, symbol, market='CN'):
        """
        短线分析 - 使用更短的周期和更敏感的指标权重
        """
        fetcher = StockDataFetcher()
        try:
            data = self._get_strategy_stock_data(symbol, period='1y', interval='1d', market=market, fetcher=fetcher)
        except Exception as e:
            print(f"获取股票 {symbol} 数据失败: {str(e)}")
            return None

        if data is None:
            print(f"股票 {symbol} 数据为None")
            return None

        if len(data) < 10:
            print(f"股票 {symbol} 数据不足: {len(data)} 天")
            return None

        data = self._merge_realtime_quote(data, fetcher, symbol, market)

        try:
            df = TechnicalIndicators.calculate_all(data)
            signals = TechnicalIndicators.get_signals(df)
        except Exception as e:
            print(f"股票 {symbol} 计算指标失败: {str(e)}")
            return None

        if 'error' in signals:
            print(f"股票 {symbol} 信号错误: {signals['error']}")
            return None

        latest = df.iloc[-1]

        # 短线评分：使用短线权重 + 波动率加成
        score = _score_from_signals(signals, latest, _SHORT_TERM_WEIGHTS)

        # 波动率加成：短线喜欢适中波动
        if len(data) > 5:
            volatility = data['close'].pct_change().std() * 100
            if 1.5 < volatility < 5:
                score += 5

        score = max(0, min(100, score))

        change_pct = (latest['close'] - data['close'].iloc[-2]) / data['close'].iloc[-2] * 100 if len(data) > 1 else 0.0
        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': _score_rating(score),
            'signals': signals,
            'latest_price': latest['close'],
            'change_pct': round(change_pct, 2),
            'strategy': '短线',
            'indicators': self._build_indicators_dict(latest)
        }

    def _evaluate_breakout_pattern(self, data):
        """激进突破型：MA5>MA10>MA20、20日新高、成交量>5日均量1.2倍。"""
        if data is None or len(data) < 25:
            return None
        df = TechnicalIndicators.calculate_all(data.copy())
        latest = df.iloc[-1]
        prev_volume_avg = df['volume'].iloc[-6:-1].mean()
        latest_volume = _safe_float(latest.get('volume')) or 0
        recent_high_20 = df['close'].iloc[-20:].max()
        prev_close = df['close'].iloc[-2] if len(df) > 1 else latest['close']
        conditions = {
            "均线多头排列": bool(latest.get('ma5', 0) > latest.get('ma10', 0) > latest.get('ma20', 0)),
            "突破20日新高": bool(latest['close'] >= recent_high_20),
            "明显放量": bool(prev_volume_avg and latest_volume > prev_volume_avg * 1.2),
        }
        volume_ratio = float(latest_volume / prev_volume_avg) if prev_volume_avg else 0.0
        matched = sum(1 for ok in conditions.values() if ok)
        return {
            "df": df,
            "latest": latest,
            "conditions": conditions,
            "matched": matched,
            "volume_ratio": round(volume_ratio, 2),
            "change_pct": round((latest['close'] - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
            "recent_high_20": round(float(recent_high_20), 2),
        }

    def _build_breakout_result(self, symbol, pattern, stock=None, sector_name=None):
        latest = pattern["latest"]
        conditions = pattern["conditions"]
        score = 55 + pattern["matched"] * 12
        score += min(8, max(0, (pattern["volume_ratio"] - 1.2) * 5))
        score = max(0, min(100, score))
        return {
            'symbol': symbol,
            'name': (stock or {}).get('name', symbol),
            'sector': sector_name,
            'board': self._board_label(symbol),
            'score': round(score, 1),
            'rating': '强突破候选' if pattern["matched"] == 3 else '观察候选',
            'signals': {
                '技术形态': f"命中 {pattern['matched']}/3",
                '卖出纪律': '次日低开-5%止损；跌破前收5分钟不反弹退出；高开冲高分批止盈；平开30分钟走弱退出',
            },
            'latest_price': float(latest['close']),
            'change_pct': pattern["change_pct"],
            'strategy': '激进突破型',
            'strategy_checks': conditions,
            'strategy_details': {
                '20日新高': pattern["recent_high_20"],
                '量比': pattern["volume_ratio"],
                '买入观察': '突破确认后观察买入，不承诺实时打板能力',
                '卖出纪律': '低开-5%止损 / 跌破前收5分钟不反弹退出 / 高开冲高分批止盈 / 平开30分钟走弱退出',
            },
            'indicators': self._build_indicators_dict(latest),
        }

    def _analyze_aggressive_breakout(self, symbol, market='CN', stock=None, sector_name=None):
        fetcher = StockDataFetcher()
        small_cap_ok = bool((stock or {}).get("_market_cap") is not None)
        market_cap = (stock or {}).get("_market_cap")
        cap_note = (stock or {}).get("_cap_note")
        profile = (stock or {}).get("_profile") or {}
        if not small_cap_ok:
            small_cap_ok, market_cap, cap_note, profile = self._passes_small_cap_filter(symbol, market)
        if not small_cap_ok:
            return None
        try:
            data = self._get_strategy_stock_data(symbol, period='3mo', interval='1d', market=market, fetcher=fetcher)
        except Exception:
            return None
        if data is None or len(data) < 25:
            return None
        data = self._merge_realtime_quote(data, fetcher, symbol, market)
        pattern = self._evaluate_breakout_pattern(data)
        if not pattern or pattern["matched"] < 3:
            return None
        result = self._build_breakout_result(symbol, pattern, stock=stock, sector_name=sector_name)
        result["market_cap"] = market_cap
        result["profile"] = profile
        result.setdefault("strategy_checks", {})["市值<300亿"] = True
        result.setdefault("strategy_details", {})["市值过滤"] = cap_note
        return result

    def _analyze_aggressive_breakout_technical(self, stock, market='CN', sector_name=None, realtime_quotes=None, fetcher=None):
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return None
        fetcher = fetcher or StockDataFetcher()
        try:
            data = self._get_strategy_stock_data(symbol, period='3mo', interval='1d', market=market, fetcher=fetcher)
        except Exception:
            return None
        if data is None or len(data) < 25:
            return None
        data = self._merge_realtime_quote(data, fetcher, symbol, market, quote=(realtime_quotes or {}).get(symbol))
        pattern = self._evaluate_breakout_pattern(data)
        if not pattern or pattern["matched"] < 3:
            return None
        return {
            "stock": dict(stock or {}),
            "symbol": symbol,
            "sector_name": sector_name,
            "pattern": pattern,
        }

    def _finalize_aggressive_breakout_candidate(self, candidate, market='CN'):
        stock = dict(candidate.get("stock") or {})
        symbol = candidate.get("symbol") or stock.get("code")
        small_cap_ok, market_cap, cap_note, profile = self._passes_small_cap_filter(symbol, market)
        if not small_cap_ok:
            return None
        result = self._build_breakout_result(
            symbol,
            candidate["pattern"],
            stock=stock,
            sector_name=candidate.get("sector_name"),
        )
        result["market_cap"] = market_cap
        result["profile"] = profile
        result.setdefault("strategy_checks", {})["市值<300亿"] = True
        result.setdefault("strategy_details", {})["市值过滤"] = cap_note
        return result

    def _run_aggressive_breakout_pool(self, stocks, num_stocks, market='CN', sector_name=None, diagnostics=None, progress_callback=None):
        diagnostics = diagnostics if isinstance(diagnostics, dict) else None
        stocks = list(stocks or [])
        if diagnostics is not None:
            diagnostics["raw_pool"] = len(stocks)
        _emit_progress(progress_callback, "股票池", 20, raw_pool=len(stocks))
        realtime_quotes = {}
        try:
            realtime_quotes = StockDataFetcher().get_batch_realtime_quotes(
                [str(stock.get("code")) for stock in stocks if stock.get("code")],
                market,
            )
        except Exception:
            realtime_quotes = {}
        if diagnostics is not None:
            diagnostics["realtime_quotes"] = len(realtime_quotes)
        _emit_progress(progress_callback, "当日实时价量", 35, raw_pool=len(stocks), realtime_quotes=len(realtime_quotes))
        candidates = []
        technical_failures = 0
        fetcher = StockDataFetcher()
        try:
            accepts_fetcher = "fetcher" in inspect.signature(self._analyze_aggressive_breakout_technical).parameters
        except Exception:
            accepts_fetcher = True

        def analyze_technical(stock):
            if accepts_fetcher:
                return self._analyze_aggressive_breakout_technical(stock, market, sector_name, realtime_quotes, fetcher)
            return self._analyze_aggressive_breakout_technical(stock, market, sector_name, realtime_quotes)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(analyze_technical, stock): stock for stock in stocks}
            for future in as_completed(futures):
                try:
                    candidate = future.result()
                except Exception:
                    candidate = None
                if candidate:
                    candidates.append(candidate)
                else:
                    technical_failures += 1
        if diagnostics is not None:
            diagnostics["technical_passed"] = len(candidates)
            diagnostics["technical_failed"] = technical_failures
        _emit_progress(
            progress_callback,
            "K线轻筛",
            75,
            raw_pool=len(stocks),
            technical_passed=len(candidates),
            technical_failed=technical_failures,
        )
        candidates.sort(key=lambda item: item["pattern"]["volume_ratio"], reverse=True)
        results = []
        cap_failed = 0
        for candidate in candidates:
            result = self._finalize_aggressive_breakout_candidate(candidate, market=market)
            if result:
                results.append(result)
                if len(results) >= num_stocks:
                    break
            else:
                cap_failed += 1
        results.sort(key=lambda item: item["score"], reverse=True)
        if diagnostics is not None:
            diagnostics["market_cap_failed"] = cap_failed
            diagnostics["result_count"] = len(results[:num_stocks])
        _emit_progress(
            progress_callback,
            "市值过滤",
            90,
            technical_passed=len(candidates),
            market_cap_failed=cap_failed,
            result_count=len(results[:num_stocks]),
        )
        return results[:num_stocks]

    def _has_recent_limit_up(self, data, days=30):
        if data is None or len(data) < 2:
            return False
        recent = data.tail(days + 1).copy()
        pct = recent['close'].pct_change() * 100
        return bool((pct.tail(days) >= 9.8).any())

    def _has_recent_limit_up_touch(self, data, days=15):
        """既往 N 日是否出现涨停：盘中最高价触及涨停即算。"""
        if data is None or len(data) < 2:
            return False, "K线数据不足"
        recent = data.tail(days + 1).copy()
        events = 0
        for idx in range(1, len(recent)):
            prev_close = _safe_float(recent['close'].iloc[idx - 1])
            close = _safe_float(recent['close'].iloc[idx])
            high = _safe_float(recent['high'].iloc[idx]) if 'high' in recent.columns else close
            if not prev_close or prev_close <= 0 or close is None or high is None:
                continue
            limit_threshold = prev_close * 1.098
            if high >= limit_threshold:
                events += 1
        if events:
            return True, f"近{days}日出现涨停 {events} 次"
        return False, f"近{days}日未出现涨停"

    @staticmethod
    def _has_three_day_rise(data):
        if data is None or len(data) < 4:
            return False, "K线数据不足"
        closes = data['close'].tail(4)
        ok = bool(closes.iloc[-1] > closes.iloc[-2] > closes.iloc[-3] > closes.iloc[-4])
        if ok:
            total_pct = (closes.iloc[-1] / closes.iloc[-4] - 1) * 100 if closes.iloc[-4] else 0
            return True, f"连续3日上涨，累计 {total_pct:.2f}%"
        return False, "未满足连续3日上涨"

    @staticmethod
    def _main_fund_trend_value(fund_flow):
        values = []
        for key in ["five_day_main_net_inflow", "main_net_inflow"]:
            value = _safe_float((fund_flow or {}).get(key))
            if value is not None:
                values.append(value)
        history = (fund_flow or {}).get("history") or []
        if isinstance(history, list):
            for item in history[:5]:
                if isinstance(item, dict):
                    value = _metric_value(item, ["主力净流入", "主力净流入-净额", "main_net_inflow", "net_inflow"])
                    if value is not None:
                        values.append(value)
        if not values:
            return None
        return sum(values)

    def _latest_limit_status(self, data):
        """判断最新交易日是否涨停或破板。"""
        if data is None or len(data) < 2:
            return {"limit_up": False, "broken_limit": False, "note": "K线数据不足"}
        prev_close = _safe_float(data['close'].iloc[-2])
        latest_close = _safe_float(data['close'].iloc[-1])
        latest_high = _safe_float(data['high'].iloc[-1]) if 'high' in data.columns else latest_close
        if not prev_close or prev_close <= 0 or latest_close is None or latest_high is None:
            return {"limit_up": False, "broken_limit": False, "note": "价格数据不足"}
        limit_threshold = prev_close * 1.098
        close_limit_up = latest_close >= limit_threshold
        touched_limit = latest_high >= limit_threshold
        broken_limit = bool(touched_limit and not close_limit_up)
        if close_limit_up:
            note = "最新交易日收盘接近/达到涨停"
        elif broken_limit:
            note = "最新交易日盘中触及涨停后回落"
        else:
            note = "最新交易日未涨停/未破板"
        return {"limit_up": bool(close_limit_up), "broken_limit": broken_limit, "note": note}

    def _get_market_cap_profile(self, symbol, market='CN'):
        market_cap, name, source = _fetch_tencent_market_cap(symbol)
        profile = {
            "symbol": symbol,
            "name": name or symbol,
            "market": market,
            "market_cap": market_cap,
            "source": source,
        }
        return market_cap, profile

    def _passes_small_cap_filter(self, symbol, market='CN'):
        market_cap, profile = self._get_market_cap_profile(symbol, market)
        passed = bool(market_cap is not None and market_cap < MAX_STRATEGY_MARKET_CAP)
        if market_cap is None:
            note = "市值数据缺失/接口失败"
        else:
            note = f"总市值 {market_cap / 100000000:.2f} 亿"
        return passed, market_cap, note, profile

    def _stock_with_small_cap_profile(self, stock, market='CN'):
        """给候选股补充小市值过滤信息，便于在拉K线前先过滤。"""
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return None
        small_cap_ok, market_cap, cap_note, profile = self._passes_small_cap_filter(symbol, market)
        if not small_cap_ok:
            return None
        enriched = dict(stock or {})
        enriched["_market_cap"] = market_cap
        enriched["_cap_note"] = cap_note
        enriched["_profile"] = profile
        return enriched

    def _stock_with_small_cap_from_tencent(self, stock, market='CN'):
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return None
        market_cap, name, source = _fetch_tencent_market_cap(symbol)
        if market_cap is None or market_cap >= MAX_STRATEGY_MARKET_CAP:
            return None
        enriched = dict(stock or {})
        if name:
            enriched["name"] = name
        enriched["_market_cap"] = market_cap
        enriched["_cap_note"] = f"总市值 {market_cap / 100000000:.2f} 亿"
        enriched["_profile"] = {
            "symbol": symbol,
            "name": enriched.get("name"),
            "market": market,
            "market_cap": market_cap,
            "source": source,
        }
        return enriched

    def _stock_with_small_cap_from_index(self, stock, profile_index):
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return None
        item = _find_profile_index_item(profile_index, symbol, (stock or {}).get("name"))
        if not isinstance(item, dict):
            return None
        market_cap = _safe_float(item.get("market_cap"))
        if market_cap is None or market_cap >= MAX_STRATEGY_MARKET_CAP:
            return None
        enriched = dict(stock or {})
        enriched["_market_cap"] = market_cap
        enriched["_cap_note"] = f"总市值 {market_cap / 100000000:.2f} 亿"
        enriched["_profile"] = {
            "symbol": symbol,
            "name": item.get("name") or enriched.get("name"),
            "industry": item.get("industry"),
            "listing_date": item.get("listing_date"),
            "market_cap": market_cap,
            "float_market_cap": item.get("float_market_cap"),
            "source": item.get("source") or "A股全量基础资料索引",
        }
        if enriched["_profile"].get("name"):
            enriched["name"] = enriched["_profile"]["name"]
        return enriched

    def _prefilter_small_cap_stocks(self, stocks, market='CN', max_workers=8):
        """市值前置过滤：优先缓存索引，缺市值时只用腾讯轻量行情，避免主进程调用AKShare深接口。"""
        stocks = list(stocks or [])
        if not stocks:
            return []
        try:
            profile_index = self._fundamental_service.get_stock_profile_index()
        except Exception:
            profile_index = {}
        indexed_results = []
        if isinstance(profile_index, dict) and profile_index:
            missing_stocks = []
            for stock in stocks:
                symbol = str((stock or {}).get("code") or "").strip()
                item = _find_profile_index_item(profile_index, symbol, (stock or {}).get("name"))
                market_cap = _safe_float(item.get("market_cap")) if isinstance(item, dict) else None
                if market_cap is None:
                    missing_stocks.append(stock)
                elif market_cap < MAX_STRATEGY_MARKET_CAP:
                    result = self._stock_with_small_cap_from_index(stock, profile_index)
                    if result:
                        indexed_results.append(result)
                else:
                    continue
            if not missing_stocks:
                return indexed_results
            stocks = missing_stocks
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._stock_with_small_cap_from_tencent, s, market): s for s in stocks}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result:
                    results.append(result)
        return indexed_results + results

    def _evaluate_fundamental_condition(self, financial):
        metrics = (financial or {}).get("metrics") or {}
        profit = _metric_value(metrics, ["归母净利润", "净利润", "PARENT_NETPROFIT"])
        profit_growth = _metric_value(metrics, ["净利润同比", "归母净利润同比", "PARENT_NETPROFIT_YOY"])
        if profit_growth is not None and profit_growth > 20:
            return True, f"净利润同比 {profit_growth:.2f}%"
        if profit is not None and profit >= 0:
            return True, f"最新净利润未亏损（{profit:.0f}）"
        if profit is not None:
            return False, f"最新净利润亏损（{profit:.0f}）"
        return False, "财务数据缺失"

    def _evaluate_ma_volume_condition(self, data):
        """多因子稳健型技术项：均线金叉/多头 + 放量。"""
        if data is None or len(data) < 25:
            return False, "K线数据不足", 0
        df = TechnicalIndicators.calculate_all(data.copy())
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        prev_volume_avg = df['volume'].iloc[-6:-1].mean()
        latest_volume = _safe_float(latest.get('volume')) or 0
        ma_cross = bool(
            latest.get('ma5', 0) > latest.get('ma10', 0)
            and prev.get('ma5', 0) <= prev.get('ma10', 0)
        )
        ma_bullish = bool(latest.get('ma5', 0) > latest.get('ma10', 0) > latest.get('ma20', 0))
        volume_ok = bool(prev_volume_avg and latest_volume > prev_volume_avg * 1.2)
        volume_ratio = (latest_volume / prev_volume_avg) if prev_volume_avg else 0
        ok = bool((ma_cross or ma_bullish) and volume_ok)
        if ok:
            note = f"{'均线金叉' if ma_cross else '均线多头'}，量比 {volume_ratio:.2f}"
        elif ma_cross or ma_bullish:
            note = f"均线满足，量比 {volume_ratio:.2f} 未达 1.2"
        elif volume_ok:
            note = f"放量满足，均线未金叉/多头"
        else:
            note = f"均线和量能均未满足，量比 {volume_ratio:.2f}"
        return ok, note, volume_ratio

    def _risk_events_blocked(self, risk_events):
        risky_announcements = [
            item for item in (risk_events or {}).get("announcements", [])
            if any(word in str(item.get("title", "")) for word in ["减持", "立案", "处罚", "风险", "诉讼", "亏损", "退市"])
        ]
        return bool(risky_announcements), risky_announcements

    def _analyze_multi_factor_light(self, stock, market='CN', sector_name=None, realtime_quotes=None, fetcher=None):
        """多因子第一阶段：只用市值+K线做轻量预筛，避免逐股拉深度资料。"""
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return {"passed": False, "reason": "代码缺失"}
        fetcher = fetcher or StockDataFetcher()
        try:
            data = self._get_strategy_stock_data(symbol, period='3mo', interval='1d', market=market, fetcher=fetcher)
        except Exception:
            return {"passed": False, "reason": "K线接口失败"}
        if data is None or len(data) < 35:
            return {"passed": False, "reason": "K线数据不足"}
        data = self._merge_realtime_quote(data, fetcher, symbol, market, quote=(realtime_quotes or {}).get(symbol))
        technical_ok, technical_note, volume_ratio = self._evaluate_ma_volume_condition(data)
        limit_event_ok, _ = self._has_recent_limit_up_touch(data, days=15)
        three_day_rise_ok, _ = self._has_three_day_rise(data)
        short_rise = (data['close'].iloc[-1] / data['close'].tail(11).iloc[0] - 1) * 100 if len(data) >= 11 else 0
        kline_core_matched = sum(1 for ok in (technical_ok, three_day_rise_ok, limit_event_ok) if ok)
        if short_rise > 35:
            return {"passed": False, "reason": "非短期过热"}
        if kline_core_matched == 0:
            return {"passed": False, "reason": "K线核心因子不足"}
        light_score = 0
        light_score += 60 if technical_ok else 0
        light_score += 20 if three_day_rise_ok else 0
        light_score += 25 if limit_event_ok else 0
        light_score += min(15, max(0, (volume_ratio - 1.2) * 8))
        light_score += max(0, 20 - max(0, short_rise))
        enriched_stock = dict(stock)
        enriched_stock["_prefetched_data"] = data
        return {
            "passed": True,
            "stock": enriched_stock,
            "symbol": symbol,
            "sector_name": sector_name,
            "light_score": light_score,
            "technical_ok": technical_ok,
            "technical_note": technical_note,
            "volume_ratio": volume_ratio,
            "limit_event_ok": limit_event_ok,
            "three_day_rise_ok": three_day_rise_ok,
            "kline_core_matched": kline_core_matched,
        }

    def _shortlist_multi_factor_candidates(self, stocks, num_stocks, market='CN', sector_name=None, diagnostics=None, progress_callback=None):
        diagnostics = diagnostics if isinstance(diagnostics, dict) else None
        if diagnostics is not None:
            diagnostics["raw_pool"] = len(stocks or [])
        _emit_progress(progress_callback, "股票池", 20, raw_pool=len(stocks or []))
        small_cap_stocks = self._prefilter_small_cap_stocks(stocks, market=market)
        if diagnostics is not None:
            diagnostics["small_cap_pool"] = len(small_cap_stocks)
        _emit_progress(
            progress_callback,
            "市值过滤",
            40,
            raw_pool=len(stocks or []),
            small_cap_pool=len(small_cap_stocks),
        )
        if not small_cap_stocks:
            return []
        realtime_quotes = {}
        try:
            realtime_quotes = StockDataFetcher().get_batch_realtime_quotes(
                [str(stock.get("code")) for stock in small_cap_stocks if stock.get("code")],
                market,
            )
        except Exception:
            realtime_quotes = {}
        if diagnostics is not None:
            diagnostics["realtime_quotes"] = len(realtime_quotes)
        _emit_progress(
            progress_callback,
            "当日实时价量",
            50,
            small_cap_pool=len(small_cap_stocks),
            realtime_quotes=len(realtime_quotes),
        )
        light_results = []
        light_failures = {}
        fetcher = StockDataFetcher()
        try:
            accepts_fetcher = "fetcher" in inspect.signature(self._analyze_multi_factor_light).parameters
        except Exception:
            accepts_fetcher = True

        def analyze_light(stock):
            if accepts_fetcher:
                return self._analyze_multi_factor_light(stock, market, sector_name, realtime_quotes, fetcher)
            return self._analyze_multi_factor_light(stock, market, sector_name, realtime_quotes)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(analyze_light, stock): stock for stock in small_cap_stocks}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result and result.get("passed", "stock" in result):
                    light_results.append(result)
                else:
                    reason = (result or {}).get("reason") or "轻筛异常"
                    light_failures[reason] = light_failures.get(reason, 0) + 1
        light_results.sort(key=lambda item: item["light_score"], reverse=True)
        shortlist = [item["stock"] for item in light_results]
        if diagnostics is not None:
            diagnostics["light_passed"] = len(light_results)
            diagnostics["light_failures"] = light_failures
            diagnostics["shortlist"] = len(shortlist)
        _emit_progress(
            progress_callback,
            "K线轻筛",
            75,
            small_cap_pool=len(small_cap_stocks),
            light_passed=len(light_results),
            shortlist=len(shortlist),
        )
        return shortlist

    def _analyze_multi_factor(self, symbol, market='CN', stock=None, sector_name=None, diagnostics=None):
        fetcher = StockDataFetcher()
        small_cap_ok = bool((stock or {}).get("_market_cap") is not None)
        market_cap = (stock or {}).get("_market_cap")
        cap_note = (stock or {}).get("_cap_note")
        profile = (stock or {}).get("_profile") or {}
        if not small_cap_ok:
            small_cap_ok, market_cap, cap_note, profile = self._passes_small_cap_filter(symbol, market)
        if not small_cap_ok:
            self._record_multi_factor_failure(diagnostics, "市值<300亿")
            return None
        data = (stock or {}).get("_prefetched_data")
        if data is None:
            try:
                data = self._get_strategy_stock_data(symbol, period='3mo', interval='1d', market=market, fetcher=fetcher)
            except Exception:
                self._record_multi_factor_failure(diagnostics, "K线接口失败")
                return None
        if data is None or len(data) < 35:
            self._record_multi_factor_failure(diagnostics, "K线数据不足")
            return None
        if "_prefetched_data" not in (stock or {}):
            data = self._merge_realtime_quote(data, fetcher, symbol, market)
        df = TechnicalIndicators.calculate_all(data.copy())
        latest = df.iloc[-1]
        prev_close = df['close'].iloc[-2] if len(df) > 1 else latest['close']
        change_pct = round((latest['close'] - prev_close) / prev_close * 100, 2) if prev_close else 0.0
        technical_ok, technical_note, volume_ratio = self._evaluate_ma_volume_condition(data)

        extended = self._get_multi_factor_extended_info(symbol, market)

        fund_flow = extended.get("fund_flow") or {}
        financial = extended.get("financial") or {}
        risk_events = extended.get("risk_events") or {}

        fund_trend_value = self._main_fund_trend_value(fund_flow)
        fund_trend_ok = bool(fund_trend_value is not None and fund_trend_value >= 30_000_000)
        financial_ok, financial_note = self._evaluate_fundamental_condition(financial)
        three_day_rise_ok, three_day_rise_note = self._has_three_day_rise(data)
        limit_event_ok, limit_event_note = self._has_recent_limit_up_touch(data, days=15)
        short_rise = (data['close'].iloc[-1] / data['close'].tail(11).iloc[0] - 1) * 100 if len(data) >= 11 else 0
        overheated = short_rise > 35
        risk_blocked, risky_announcements = self._risk_events_blocked(risk_events)

        core_checks = {
            "均线金叉+放量": technical_ok,
            "财务确认": financial_ok,
            "连涨3日": three_day_rise_ok,
            "主力净流入趋势≥3000万": fund_trend_ok,
            "15日内涨停": limit_event_ok,
        }
        checks = {
            "市值<300亿": small_cap_ok,
            **core_checks,
        }
        hard_filters = {
            "市值<300亿": small_cap_ok,
            "非短期过热": not overheated,
            "无重大风险事件": not risk_blocked,
        }
        details = {
            "市值过滤": cap_note,
            "技术说明": technical_note,
            "财务确认": financial_note,
            "连涨3日": three_day_rise_note,
            "主力净流入趋势": f"{fund_trend_value / 10000:.0f} 万" if fund_trend_value is not None else "数据缺失/接口失败",
            "15日涨停": limit_event_note,
        }
        self._record_multi_factor_core_diagnostics(
            diagnostics,
            core_checks,
            {
                "financial": financial,
                "fund_flow": fund_flow,
                "risk_events": risk_events,
            },
        )
        if not all(hard_filters.values()):
            for reason, passed in hard_filters.items():
                if not passed:
                    self._record_multi_factor_failure(diagnostics, reason)
            return None

        core_matched = sum(1 for ok in core_checks.values() if ok)
        score = 42
        score += 20 if technical_ok else 0
        score += 16 if financial_ok else 0
        score += 14 if three_day_rise_ok else 0
        score += 16 if fund_trend_ok else 0
        score += 10 if limit_event_ok else 0
        score += min(6, max(0, (volume_ratio - 1.2) * 4))
        score = max(0, min(100, score))
        if core_matched < 3 or score < 70:
            self._record_multi_factor_failure(diagnostics, f"评分不足({core_matched}/5,{score:.1f})")
            return None

        return {
            'symbol': symbol,
            'name': (stock or {}).get('name', symbol),
            'sector': sector_name,
            'board': self._board_label(symbol),
            'score': round(score, 1),
            'rating': '多因子共振' if core_matched >= 4 and score >= 80 else '稳健观察候选',
            'signals': {
                '技术形态': technical_note,
                '卖出纪律': '跌破关键均线或风险事件触发时降仓；冲高乏力分批止盈',
            },
            'latest_price': float(latest['close']),
            'change_pct': change_pct,
            'strategy': '多因子稳健型',
            'strategy_checks': checks,
            'required_checks': hard_filters,
            'core_checks': core_checks,
            'core_matched': core_matched,
            'bonus_checks': {},
            'strategy_details': {
                **details,
                '买入观察': '多因子共振时进入观察/候选，结合买卖计划卡片确认买入区间',
                '卖出纪律': '跌破关键均线/资金转弱/风险事件触发时退出或降仓',
                '命中因子': f"核心因子 {core_matched}/5，综合评分 {score:.1f}",
                '风险排除': '已排除短期过热/重大风险事件',
            },
            'indicators': self._build_indicators_dict(latest),
            'extended_info': extended,
            'profile': profile,
            'market_cap': market_cap,
        }

    def _get_multi_factor_extended_info(self, symbol, market='CN'):
        """稳健型深度资料隔离到子进程，避免AKShare原生依赖崩溃拖垮Streamlit。"""
        try:
            cached = self._stock_info_service.get_cached_stock_extended_info(
                symbol,
                market,
                include_deep_layers=True,
            )
            if isinstance(cached, dict):
                return cached
        except Exception:
            pass
        return _fetch_extended_info_subprocess(symbol, market=market)

    def _record_multi_factor_failure(self, diagnostics, reason):
        if not isinstance(diagnostics, dict):
            return
        failures = diagnostics.setdefault("deep_failures", {})
        failures[reason] = failures.get(reason, 0) + 1

    def _record_multi_factor_core_diagnostics(self, diagnostics, core_checks, layers):
        if not isinstance(diagnostics, dict):
            return
        summary = diagnostics.setdefault("core_factor_summary", {})
        for name, passed in (core_checks or {}).items():
            item = summary.setdefault(name, {"passed": 0, "failed": 0})
            key = "passed" if passed else "failed"
            item[key] = item.get(key, 0) + 1

        data_quality = diagnostics.setdefault("deep_data_quality", {})
        for key, label in {
            "financial": "财务数据",
            "fund_flow": "资金流数据",
            "risk_events": "风险事件数据",
        }.items():
            item = data_quality.setdefault(label, {"available": 0, "missing": 0, "source_failed": 0, "source_empty": 0})
            layer = (layers or {}).get(key)
            if _has_usable_extended_layer(layer):
                item["available"] = item.get("available", 0) + 1
                continue
            status = layer.get("status") if isinstance(layer, dict) else None
            if status == "source_failed":
                item["source_failed"] = item.get("source_failed", 0) + 1
            elif status == "source_empty":
                item["source_empty"] = item.get("source_empty", 0) + 1
            else:
                item["missing"] = item.get("missing", 0) + 1

    def _run_strategy_pool(self, strategy_name, stocks, num_stocks, analyzer, progress_callback=None, progress_stage=None):
        results = []
        completed = 0
        total = len(stocks or [])

        def analyze_one(stock):
            try:
                return analyzer(stock)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_one, s): s for s in stocks}
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                if result:
                    results.append(result)
                if progress_callback and progress_stage and (completed == total or completed % 25 == 0):
                    percent = 85 + int(10 * completed / total) if total else 95
                    _emit_progress(
                        progress_callback,
                        progress_stage,
                        min(percent, 95),
                        deep_total=total,
                        deep_done=completed,
                        result_count=len(results),
                    )

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_aggressive_breakout_recommendations(self, num_stocks=10, progress_callback=None):
        """激进突破型：沪深主板 + 创业板，纯量价突破。"""
        diagnostics = {"strategy": "激进突破型"}
        stocks = self._get_strategy_popular_cn_stocks()
        results = self._run_aggressive_breakout_pool(stocks, num_stocks, diagnostics=diagnostics, progress_callback=progress_callback)
        self.last_aggressive_diagnostics = diagnostics
        _emit_progress(progress_callback, "完成", 100, result_count=len(results))
        return results

    def get_sector_aggressive_breakout_recommendations(self, sector_name, num_stocks=5, progress_callback=None):
        """指定板块激进突破型推荐。"""
        if sector_name not in SECTOR_STOCKS:
            return []
        diagnostics = {"strategy": "激进突破型", "sector": sector_name}
        stocks = self._get_strategy_sector_stocks(sector_name)
        results = self._run_aggressive_breakout_pool(stocks, num_stocks, sector_name=sector_name, diagnostics=diagnostics, progress_callback=progress_callback)
        self.last_aggressive_diagnostics = diagnostics
        _emit_progress(progress_callback, "完成", 100, result_count=len(results))
        return results

    def get_multi_factor_recommendations(self, num_stocks=10, progress_callback=None):
        """多因子稳健型：技术 + 财务 + 连涨3日 + 主力净流入趋势 + 15日内涨停。"""
        diagnostics = {"strategy": "多因子稳健型"}
        stocks = self._get_strategy_popular_cn_stocks()
        stocks = self._shortlist_multi_factor_candidates(stocks, num_stocks, diagnostics=diagnostics, progress_callback=progress_callback)
        diagnostics["deep_checked"] = len(stocks)
        _emit_progress(
            progress_callback,
            "深度检查",
            85,
            deep_checked=len(stocks),
            deep_total=len(stocks),
            deep_done=0,
            result_count=0,
        )
        results = self._run_strategy_pool(
            '多因子稳健型',
            stocks,
            num_stocks,
            lambda stock: self._analyze_multi_factor(stock['code'], stock=stock, diagnostics=diagnostics),
            progress_callback=progress_callback,
            progress_stage="深度检查",
        )
        diagnostics["result_count"] = len(results)
        self.last_multi_factor_diagnostics = diagnostics
        _emit_progress(progress_callback, "完成", 100, deep_checked=len(stocks), result_count=len(results))
        return results

    def get_sector_multi_factor_recommendations(self, sector_name, num_stocks=5, progress_callback=None):
        """指定板块多因子稳健型推荐。"""
        if sector_name not in SECTOR_STOCKS:
            return []
        diagnostics = {"strategy": "多因子稳健型", "sector": sector_name}
        stocks = self._get_strategy_sector_stocks(sector_name)
        stocks = self._shortlist_multi_factor_candidates(stocks, num_stocks, sector_name=sector_name, diagnostics=diagnostics, progress_callback=progress_callback)
        diagnostics["deep_checked"] = len(stocks)
        _emit_progress(
            progress_callback,
            "深度检查",
            85,
            deep_checked=len(stocks),
            deep_total=len(stocks),
            deep_done=0,
            result_count=0,
        )
        results = self._run_strategy_pool(
            '多因子稳健型',
            stocks,
            num_stocks,
            lambda stock: self._analyze_multi_factor(stock['code'], stock=stock, sector_name=sector_name, diagnostics=diagnostics),
            progress_callback=progress_callback,
            progress_stage="深度检查",
        )
        diagnostics["result_count"] = len(results)
        self.last_multi_factor_diagnostics = diagnostics
        _emit_progress(progress_callback, "完成", 100, deep_checked=len(stocks), result_count=len(results))
        return results


    def get_sector_long_term_recommendations(self, sector_name, num_stocks=5):
        """
        获取指定板块的长线龙头股推荐，并发分析加速
        """
        if sector_name not in SECTOR_STOCKS:
            return []

        results = []
        sector_stocks = self._get_main_board_sector_stocks(sector_name)

        def analyze_one(stock):
            try:
                analysis = self._analyze_long_term(stock['code'], market='CN')
                if analysis:
                    analysis['name'] = stock['name']
                    analysis['sector'] = sector_name
                    return analysis
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_one, s): s for s in sector_stocks}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def _analyze_long_term(self, symbol, market='CN'):
        """
        长线分析 - 使用1年数据，侧重MA60趋势和MACD趋势，降低RSI/KDJ权重
        """
        fetcher = StockDataFetcher()
        try:
            data = self._get_strategy_stock_data(symbol, period='1y', interval='1d', market=market, fetcher=fetcher)
        except Exception as e:
            print(f"获取股票 {symbol} 长线数据失败: {str(e)}")
            return None

        if data is None or len(data) < 50:
            return None

        data = self._merge_realtime_quote(data, fetcher, symbol, market)

        try:
            df = TechnicalIndicators.calculate_all(data)
            signals = TechnicalIndicators.get_signals(df)
        except Exception as e:
            print(f"股票 {symbol} 长线指标计算失败: {str(e)}")
            return None

        if 'error' in signals:
            return None

        latest = df.iloc[-1]

        # 长线评分：使用长线权重 + MA60趋势加成
        score = _score_from_signals(signals, latest, _LONG_TERM_WEIGHTS)

        # MA60自身趋势（长线核心指标）
        if 'ma60' in df.columns and len(df) > 20:
            ma60_now = latest['ma60']
            ma60_20d_ago = df['ma60'].iloc[-21]
            if ma60_now > ma60_20d_ago:
                score += 8
            else:
                score -= 8

        score = max(0, min(100, score))

        change_pct = (latest['close'] - data['close'].iloc[-2]) / data['close'].iloc[-2] * 100 if len(data) > 1 else 0.0
        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': _score_rating(score),
            'signals': signals,
            'latest_price': latest['close'],
            'change_pct': round(change_pct, 2),
            'strategy': '长线',
            'indicators': self._build_indicators_dict(latest)
        }

if __name__ == "__main__":
    # 测试代码
    recommender = StockRecommender()

    print("=== A股热门股票 ===")
    hot_stocks = recommender.get_hot_stocks_cn(limit=10)
    for stock in hot_stocks:
        print(f"{stock['代码']} {stock['名称']}: 价格{stock['最新价']}, "
              f"涨跌{stock['涨跌幅']}%")

    print("\n=== 推荐股票 ===")
    recommended = recommender.get_recommended_stocks_cn(num_stocks=5)
    for stock in recommended:
        print(f"{stock['symbol']} {stock['name']}: 评分{stock['score']}, 建议{stock['rating']}")
