"""
热门股票和推荐股票模块
涨跌幅榜使用新浪财经实时排行（沪深京全市场），行业/概念板块使用同花顺HTML抓取，港股美股使用yfinance
"""
import requests
import re
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 导入热门股票列表
from data_fetcher import StockDataFetcher, get_popular_cn_stocks, POPULAR_US_STOCKS, POPULAR_HK_STOCKS
from stock_names import SECTOR_STOCKS
from technical_indicators import TechnicalIndicators

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


class StockRecommender:
    """股票推荐器"""

    def __init__(self):
        pass

    def _merge_realtime_quote(self, data, fetcher, symbol, market):
        """合并实时行情到最后一根K线"""
        try:
            quote = fetcher.get_realtime_quote(symbol, market)
            if quote and quote.get('price'):
                today = pd.Timestamp.now().normalize()
                if data.index[-1].normalize() == today:
                    idx = data.index[-1]
                    data.loc[idx, 'close'] = quote['price']
                    data.loc[idx, 'high'] = max(data.loc[idx, 'high'], quote['high'])
                    data.loc[idx, 'low'] = min(data.loc[idx, 'low'], quote['low'])
                else:
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
        }

    def get_hot_stocks_cn(self, limit=20):
        """
        获取A股热门股票（使用新浪财经批量行情，一次请求全部获取）
        """
        results = []
        stocks = [s for s in get_popular_cn_stocks()[:max(limit, 30)]
                  if self._is_main_board(s['code'])]  # 排除创业板/科创板

        try:
            # 为每只股票构造新浪代码（优先上海，尝试深圳）
            headers = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # 先尝试批量获取上海（6开头）
            sh_stocks = [s for s in stocks if s['code'].startswith(('600', '601', '603', '605', '688'))]
            sz_stocks = [s for s in stocks if s not in sh_stocks]

            all_quotes = {}

            # 批量获取上海股票
            if sh_stocks:
                codes = [f"sh{s['code']}" for s in sh_stocks]
                url = f"https://hq.sinajs.cn/list={','.join(codes)}"
                try:
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        for line in resp.text.strip().split('\n'):
                            match = re.search(r'hq_str_sh(\d+)="([^"]*)"', line)
                            if match:
                                code = match.group(1)
                                data = match.group(2).split(',')
                                if len(data) >= 33:
                                    all_quotes[code] = data
                except Exception:
                    pass

            # 批量获取深圳股票
            if sz_stocks:
                codes = [f"sz{s['code']}" for s in sz_stocks]
                url = f"https://hq.sinajs.cn/list={','.join(codes)}"
                try:
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        for line in resp.text.strip().split('\n'):
                            match = re.search(r'hq_str_sz(\d+)="([^"]*)"', line)
                            if match:
                                code = match.group(1)
                                data = match.group(2).split(',')
                                if len(data) >= 33:
                                    all_quotes[code] = data
                except Exception:
                    pass

            # 解析行情数据
            for stock in stocks:
                code = stock['code']
                data = all_quotes.get(code)
                if not data:
                    continue

                try:
                    name = data[0]
                    open_price = float(data[1])
                    prev_close = float(data[2])
                    price = float(data[3])
                    high = float(data[4])
                    low = float(data[5])
                    volume = int(float(data[8]))  # 成交量（股）
                    # 自己算涨跌幅（新浪字段32不可靠，有时为"00"）
                    change = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0

                    results.append({
                        '代码': code,
                        '名称': name,
                        '最新价': round(price, 2),
                        '涨跌幅': round(change, 2),
                        '换手率': None,  # 新浪批量接口不含换手率
                        '成交量': volume,
                        '成交额': int(volume * price) if volume > 0 else 0,
                        '热度分数': round(abs(change), 2)
                    })
                except (ValueError, IndexError):
                    continue

        except Exception:
            pass

        # 按热度分数排序
        results.sort(key=lambda x: x['热度分数'], reverse=True)
        return results[:limit]

    def get_hot_sectors_cn(self, limit=30):
        """获取A股行业板块排行（同花顺实时数据，HTML抓取）"""
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
        """获取A股概念板块排行（同花顺概念资金流向，全量抓取后按涨跌幅排序）

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
                        })
                    except (ValueError, IndexError):
                        continue

            # 按涨跌幅降序排列（资金流向页默认按主力资金排序）
            concepts.sort(key=lambda x: x['涨跌幅'], reverse=True)
            return concepts[:limit]
        except Exception as e:
            print(f"获取概念板块排行失败: {e}")
            return concepts if concepts else []

    @staticmethod
    def _is_main_board(code):
        """判断是否为沪深主板股票（排除创业板/科创板/北交所）"""
        return code.startswith(('600', '601', '603', '605',     # 沪市主板
                                '000', '001', '002', '003'))    # 深市主板

    # 行业缓存（东方财富F10 API，首次查询后复用）
    _sector_cache = {}

    @classmethod
    def _get_stock_sector(cls, code):
        """获取股票所属行业板块（东方财富F10公司概况API，带缓存）"""
        if code in cls._sector_cache:
            return cls._sector_cache[code]
        try:
            if code.startswith(('8', '9')):
                mkt = 'BJ'
            elif code.startswith('6'):
                mkt = 'SH'
            else:
                mkt = 'SZ'
            url = 'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax'
            resp = requests.get(url, params={'code': f'{mkt}{code}'}, headers={
                'Referer': 'https://emweb.securities.eastmoney.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                jbzl = data.get('jbzl') or {}
                sector = (jbzl.get('sshy') or '').strip()
                if sector and sector != '--':
                    cls._sector_cache[code] = sector
                    return sector
        except Exception:
            pass
        # 回退：根据代码前缀判断交易所
        if code.startswith(('8', '9')):
            fallback = '北交所'
        elif code.startswith('68'):
            fallback = '科创板'
        elif code.startswith('30'):
            fallback = '创业板'
        elif code.startswith('6'):
            fallback = '沪市主板'
        else:
            fallback = '深市主板'
        cls._sector_cache[code] = fallback
        return fallback

    def _get_market_ranking(self, sort_asc=False, limit=10):
        """获取全市场涨跌幅榜（新浪财经实时排行，沪深京全市场含北交所）"""
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
                s['所属板块'] = self._get_stock_sector(s['代码'])
            return results
        except Exception:
            return []

    def get_top_gainers_cn(self, limit=10):
        """获取A股全市场涨幅榜（同花顺实时排行）"""
        ranking = self._get_market_ranking(sort_asc=False, limit=limit + 5)
        gainers = [s for s in ranking if s['涨跌幅'] > 0]
        return gainers[:limit]

    def get_top_losers_cn(self, limit=10):
        """获取A股全市场跌幅榜（同花顺实时排行）"""
        ranking = self._get_market_ranking(sort_asc=True, limit=limit + 5)
        losers = [s for s in ranking if s['涨跌幅'] < 0]
        return losers[:limit]

    def get_hot_stocks_hk(self, limit=20):
        """获取港股热门股票（使用yfinance数据源）"""
        results = []

        def fetch_stock_info(stock):
            try:
                symbol = stock['code']
                ticker = yf.Ticker(f"{symbol}.HK")
                hist = ticker.history(period="5d")
                info = ticker.info

                if hist.empty or len(hist) < 2:
                    return None

                latest = hist.iloc[-1]
                prev = hist.iloc[-2]
                change = ((latest['Close'] - prev['Close']) / prev['Close'] * 100)

                return {
                    '代码': symbol,
                    '名称': stock['name'],
                    '最新价': round(latest['Close'], 2),
                    '涨跌幅': round(change, 2),
                    '换手率': None,
                    '成交量': int(latest['Volume']),
                    '成交额': int(latest['Volume'] * latest['Close']),
                    '热度分数': round(abs(change), 2)
                }
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_stock_info, stock): stock
                      for stock in POPULAR_HK_STOCKS[:limit]}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda x: x['热度分数'], reverse=True)
        return results[:limit]

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
        """获取美股热门股票"""
        results = []

        def fetch_stock_info(symbol):
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                info = ticker.info

                if hist.empty or len(hist) < 2:
                    return None

                latest = hist.iloc[-1]
                prev = hist.iloc[-2]
                change = ((latest['Close'] - prev['Close']) / prev['Close'] * 100)

                return {
                    'symbol': symbol,
                    'name': info.get('shortName', symbol),
                    'price': round(latest['Close'], 2),
                    'change': round(change, 2),
                    'volume': int(latest['Volume']),
                    'market_cap': info.get('marketCap', 0)
                }
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_stock_info, symbol): symbol
                      for symbol in POPULAR_US_STOCKS[:limit]}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # 按成交量排序
        results.sort(key=lambda x: x['volume'], reverse=True)
        return results[:limit]

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
            futures = {executor.submit(analyze_one, s): s for s in get_popular_cn_stocks()[:20]
                       if self._is_main_board(s['code'])}
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
            futures = {executor.submit(analyze_one, s): s for s in get_popular_cn_stocks()[:25]
                       if self._is_main_board(s['code'])}
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
            futures = {executor.submit(analyze_one, s): s for s in get_popular_cn_stocks()[:25]
                       if self._is_main_board(s['code'])}
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
        sector_stocks = SECTOR_STOCKS[sector_name]

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
            futures = {executor.submit(analyze_one, s): s for s in sector_stocks
                       if self._is_main_board(s['code'])}
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
            data = fetcher.get_stock_data(symbol, period='1y', interval='1d', market=market)
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


    def get_sector_long_term_recommendations(self, sector_name, num_stocks=5):
        """
        获取指定板块的长线龙头股推荐，并发分析加速
        """
        if sector_name not in SECTOR_STOCKS:
            return []

        results = []
        sector_stocks = SECTOR_STOCKS[sector_name]

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
            futures = {executor.submit(analyze_one, s): s for s in sector_stocks
                       if self._is_main_board(s['code'])}
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
            data = fetcher.get_stock_data(symbol, period='1y', interval='1d', market=market)
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

    def get_all_sector_recommendations(self):
        """
        获取全部4个板块的短线+长线推荐，并发分析加速
        返回 {板块名: {'短线': [...], '长线': [...]}}
        """
        from config import SECTOR_PUSH_TOP_N

        result = {}
        top_n = SECTOR_PUSH_TOP_N

        def analyze_sector(sector_name):
            short = self.get_sector_short_term_recommendations(sector_name, num_stocks=top_n)
            long = self.get_sector_long_term_recommendations(sector_name, num_stocks=top_n)
            return sector_name, {'短线': short, '长线': long}

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(analyze_sector, s): s for s in SECTOR_STOCKS}
            for future in as_completed(futures):
                try:
                    sector_name, data = future.result()
                    result[sector_name] = data
                except Exception as e:
                    print(f"板块分析失败: {e}")

        return result


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
