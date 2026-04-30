"""
热门股票和推荐股票模块
A股使用新浪财经批量行情，港股美股使用yfinance
板块排行使用AKShare（同花顺数据源）
"""
import requests
import re
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import akshare as ak
warnings.filterwarnings('ignore')

# 导入热门股票列表
from data_fetcher import POPULAR_CN_STOCKS, POPULAR_US_STOCKS, POPULAR_HK_STOCKS

# 板块股票定义 - 短线龙头股
SECTOR_STOCKS = {
    "苹果概念": [
        {'code': '002475', 'name': '立讯精密'},  # AirPods主力供应商
        {'code': '300433', 'name': '蓝思科技'},  # 玻璃盖板龙头
        {'code': '601231', 'name': '环旭电子'},  # SiP模组龙头
        {'code': '002241', 'name': '歌尔股份'},  # 声学组件龙头
        {'code': '603501', 'name': '韦尔股份'},  # 摄像头芯片
        {'code': '000725', 'name': '京东方A'},   # 显示屏供应商
        {'code': '002600', 'name': '领益智造'},  # 精密功能件
        {'code': '300136', 'name': '信维通信'},  # 射频天线
    ],
    "特斯拉概念": [
        {'code': '002594', 'name': '比亚迪'},    # 新能源汽车对标
        {'code': '300750', 'name': '宁德时代'},  # 动力电池龙头
        {'code': '002050', 'name': '三花智控'},  # 热管理系统
        {'code': '600885', 'name': '宏发股份'},  # 继电器龙头
        {'code': '603305', 'name': '旭升集团'},  # 特斯拉零部件
        {'code': '002101', 'name': '广东鸿图'},  # 压铸零部件
        {'code': '300124', 'name': '汇川技术'},  # 电机电控
        {'code': '603596', 'name': '伯特利'},    # 汽车制动系统
    ],
    "电力": [
        {'code': '600900', 'name': '长江电力'},  # 水电龙头
        {'code': '600011', 'name': '华能国际'},  # 火电龙头
        {'code': '600795', 'name': '国电电力'},  # 大型发电集团
        {'code': '601985', 'name': '中国核电'},  # 核电运营
        {'code': '003816', 'name': '中国广核'},  # 核电双巨头之一
        {'code': '600023', 'name': '浙能电力'},  # 区域电力龙头
        {'code': '600886', 'name': '国投电力'},  # 水电+火电
        {'code': '600027', 'name': '华电国际'},  # 大型发电企业
    ],
    "算力租赁": [
        {'code': '603019', 'name': '中科曙光'},  # AI服务器龙头
        {'code': '000938', 'name': '中核科技'},  # 算力基础设施
        {'code': '300212', 'name': '易华录'},    # 数据湖+算力
        {'code': '600756', 'name': '浪潮软件'},  # 服务器相关
        {'code': '000977', 'name': '浪潮信息'},  # 服务器龙头
        {'code': '300383', 'name': '光环新网'},  # IDC+云计算
        {'code': '300738', 'name': '奥飞数据'},  # IDC服务商
        {'code': '603881', 'name': '数据港'},    # 数据中心运营
    ],
}


class StockRecommender:
    """股票推荐器"""

    def __init__(self):
        self.hot_stocks_cache = None
        self.hot_stocks_cache_time = None

    def get_hot_stocks_cn(self, limit=20):
        """
        获取A股热门股票（使用新浪财经批量行情，一次请求全部获取）
        """
        results = []
        stocks = POPULAR_CN_STOCKS[:max(limit, 30)]  # 至少取30只用于涨跌幅榜

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
        """获取A股热门板块排行（同花顺行业板块实时数据）"""
        try:
            df = ak.stock_board_industry_summary_ths()
            sectors = []
            for _, row in df.head(limit).iterrows():
                sectors.append({
                    '板块': row['板块'],
                    '涨跌幅': round(float(row['涨跌幅']), 2),
                    '领涨股': row['领涨股'],
                    '领涨股价格': round(float(row['领涨股-最新价']), 2),
                    '领涨股涨幅': round(float(row['领涨股-涨跌幅']), 2),
                    '上涨家数': int(row['上涨家数']),
                    '下跌家数': int(row['下跌家数']),
                    '总成交额(亿)': round(float(row['总成交额']), 2),
                    '净流入(亿)': round(float(row['净流入']), 2),
                })
            return sectors
        except Exception as e:
            print(f"获取板块排行失败: {e}")
            return []

    def _get_market_ranking(self, sort_asc=False, limit=10):
        """获取全市场涨幅榜/跌幅榜（新浪财经数据源）"""
        try:
            url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
            params = {
                'page': 1,
                'num': limit + 5,  # 多取几条以防新股/异常数据
                'sort': 'changepercent',
                'asc': 1 if sort_asc else 0,
                'node': 'hs_a',
                'symbol': '',
                '_s_r_a': 'init'
            }
            headers = {
                'Referer': 'https://finance.sina.com.cn/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data:
                    try:
                        results.append({
                            '代码': item['code'],
                            '名称': item['name'],
                            '最新价': round(float(item['trade']), 2),
                            '涨跌幅': round(float(item['changepercent']), 2),
                            '换手率': round(float(item.get('turnoverratio', 0)), 2) if item.get('turnoverratio') else None,
                            '成交量': int(float(item['volume'])),
                            '成交额': int(float(item['amount'])),
                        })
                    except (ValueError, KeyError):
                        continue
                return results[:limit]
        except Exception:
            return []

    def get_top_gainers_cn(self, limit=10):
        """获取A股全市场涨幅榜（新浪财经实时排行，过滤非上涨股）"""
        ranking = self._get_market_ranking(sort_asc=False, limit=limit + 5)
        gainers = [s for s in ranking if s['涨跌幅'] > 0]
        return gainers[:limit]

    def get_top_losers_cn(self, limit=10):
        """获取A股全市场跌幅榜（新浪财经实时排行，过滤非下跌股）"""
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
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators

        fetcher = StockDataFetcher()
        data = fetcher.get_stock_data(symbol, period=period, market=market)

        if data is None or len(data) < 30:
            return None

        # 计算指标
        df = TechnicalIndicators.calculate_all(data)
        signals = TechnicalIndicators.get_signals(df)

        if 'error' in signals:
            return None

        latest = df.iloc[-1]

        # 综合评分系统
        score = 50  # 基础分50

        # MACD评分
        if "金叉" in signals['macd']:
            score += 15
        elif "多头" in signals['macd']:
            score += 10
        elif "死叉" in signals['macd']:
            score -= 10

        # RSI评分
        rsi = latest['rsi']
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 10
        elif rsi > 70:
            score -= 10
        elif rsi > 60:
            score -= 5

        # KDJ评分
        if "强" in signals['kdj'] and "金叉" in signals['kdj']:
            score += 20
        elif "金叉" in signals['kdj']:
            score += 15
        elif "超卖" in signals['kdj']:
            score += 10
        elif "强" in signals['kdj'] and "死叉" in signals['kdj']:
            score -= 20
        elif "死叉" in signals['kdj']:
            score -= 15
        elif "超买" in signals['kdj']:
            score -= 10

        # 布林带评分
        if "反弹" in signals['boll']:
            score += 15
        elif "偏多" in signals['boll']:
            score += 10
        elif "回调" in signals['boll']:
            score -= 10
        elif "偏空" in signals['boll']:
            score -= 5

        # 趋势评分
        if 'ma5' in df.columns and 'ma20' in df.columns:
            if latest['ma5'] > latest['ma20']:
                score += 10
                prev = df.iloc[-2]
                if prev['ma5'] <= prev['ma20']:
                    score += 10
            else:
                score -= 10

        # 归一化到0-100
        score = max(0, min(100, score))

        # 确定评级
        if score >= 80:
            rating = "偏多信号（强）"
        elif score >= 65:
            rating = "偏多信号"
        elif score >= 50:
            rating = "观望"
        elif score >= 35:
            rating = "偏空信号"
        else:
            rating = "偏空信号（强）"

        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': rating,
            'signals': signals,
            'latest_price': latest['close'],
            'indicators': {
                'macd': round(latest['macd'], 3),
                'macd_signal': round(latest['macd_signal'], 3),
                'rsi': round(latest['rsi'], 2),
                'kdj_k': round(latest['kdj_k'], 2),
                'kdj_d': round(latest['kdj_d'], 2),
                'kdj_j': round(latest['kdj_j'], 2),
                'boll_upper': round(latest['boll_upper'], 2),
                'boll_mid': round(latest['boll_mid'], 2),
                'boll_lower': round(latest['boll_lower'], 2)
            }
        }

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
            futures = {executor.submit(analyze_one, s): s for s in POPULAR_CN_STOCKS[:20]}
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
            futures = {executor.submit(analyze_one, s): s for s in POPULAR_CN_STOCKS[:25]}
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
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators

        fetcher = StockDataFetcher()
        try:
            data = fetcher.get_stock_data(symbol, period='1mo', interval='1d', market=market)
        except Exception as e:
            print(f"获取股票 {symbol} 数据失败: {str(e)}")
            return None

        if data is None:
            print(f"股票 {symbol} 数据为None")
            return None

        if len(data) < 10:
            print(f"股票 {symbol} 数据不足: {len(data)} 天")
            return None

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

        # 短线评分系统 - 更注重动量和短期反转
        score = 50

        # MACD评分（短线权重降低）
        if "金叉" in signals['macd']:
            score += 10
        elif "多头" in signals['macd']:
            score += 5
        elif "死叉" in signals['macd']:
            score -= 15

        # RSI评分（短线权重提高）- 超卖反弹机会
        rsi = latest['rsi']
        if rsi < 25:
            score += 25  # 强烈超卖，短线反弹机会
        elif rsi < 35:
            score += 20
        elif rsi < 45:
            score += 10
        elif rsi > 75:
            score -= 15  # 超买回调风险
        elif rsi > 65:
            score -= 10

        # KDJ评分（短线权重提高）- 最敏感的短线指标
        if "强" in signals['kdj'] and "金叉" in signals['kdj']:
            score += 30
        elif "金叉" in signals['kdj']:
            score += 25
        elif "超卖" in signals['kdj']:
            score += 20
        elif "强" in signals['kdj'] and "死叉" in signals['kdj']:
            score -= 30
        elif "死叉" in signals['kdj']:
            score -= 25
        elif "超买" in signals['kdj']:
            score -= 20

        # 布林带评分（短线权重提高）
        if "反弹" in signals['boll']:
            score += 20
        elif "偏多" in signals['boll']:
            score += 10
        elif "回调" in signals['boll']:
            score -= 15
        elif "偏空" in signals['boll']:
            score -= 10

        # 短期均线评分
        if 'ma5' in df.columns and 'ma10' in df.columns:
            if latest['ma5'] > latest['ma10']:
                score += 15
                # 金叉额外加分
                if len(df) > 1:
                    prev = df.iloc[-2]
                    if prev['ma5'] <= prev['ma10']:
                        score += 15
            else:
                score -= 15

        # 波动率评分 - 短线喜欢有一定波动性的股票
        if len(data) > 5:
            volatility = data['close'].pct_change().std() * 100
            if 1.5 < volatility < 5:  # 适中波动率
                score += 5

        score = max(0, min(100, score))

        if score >= 80:
            rating = "偏多信号（强）"
        elif score >= 65:
            rating = "偏多信号"
        elif score >= 50:
            rating = "观望"
        elif score >= 35:
            rating = "偏空信号"
        else:
            rating = "偏空信号（强）"

        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': rating,
            'signals': signals,
            'latest_price': latest['close'],
            'strategy': '短线',
            'indicators': {
                'macd': round(latest['macd'], 3),
                'macd_signal': round(latest['macd_signal'], 3),
                'rsi': round(latest['rsi'], 2),
                'kdj_k': round(latest['kdj_k'], 2),
                'kdj_d': round(latest['kdj_d'], 2),
                'kdj_j': round(latest['kdj_j'], 2),
                'boll_lower': round(latest['boll_lower'], 2),
                'boll_upper': round(latest['boll_upper'], 2),
            }
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
