"""
热门股票和推荐股票模块
针对Streamlit Cloud优化（使用yfinance数据源）
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 导入热门股票列表
from data_fetcher import POPULAR_CN_STOCKS, POPULAR_US_STOCKS


class StockRecommender:
    """股票推荐器"""

    def __init__(self):
        self.hot_stocks_cache = None
        self.hot_stocks_cache_time = None

    def get_hot_stocks_cn(self, limit=20):
        """
        获取A股热门股票（使用yfinance数据源）
        """
        results = []

        def fetch_stock_info(stock):
            try:
                symbol = stock['code']
                ticker = yf.Ticker(f"{symbol}.SS")
                hist = ticker.history(period="5d")
                info = ticker.info

                if hist.empty or len(hist) < 2:
                    # 尝试深圳交易所
                    ticker = yf.Ticker(f"{symbol}.SZ")
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
                    '换手率': round(np.random.uniform(1, 10), 2),  # 模拟数据
                    '成交量': int(latest['Volume']),
                    '成交额': int(latest['Volume'] * latest['Close']),
                    '热度分数': round(abs(change) + np.random.uniform(0, 5), 2)
                }
            except:
                return None

        # 使用线程池加速
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_stock_info, stock): stock
                      for stock in POPULAR_CN_STOCKS[:limit]}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # 按热度分数排序
        results.sort(key=lambda x: x['热度分数'], reverse=True)
        return results[:limit]

    def get_top_gainers_cn(self, limit=10):
        """获取A股涨幅榜"""
        stocks = self.get_hot_stocks_cn(limit=30)
        gainers = [s for s in stocks if s['涨跌幅'] > 0]
        gainers.sort(key=lambda x: x['涨跌幅'], reverse=True)
        return gainers[:limit]

    def get_top_losers_cn(self, limit=10):
        """获取A股跌幅榜"""
        stocks = self.get_hot_stocks_cn(limit=30)
        losers = [s for s in stocks if s['涨跌幅'] < 0]
        losers.sort(key=lambda x: x['涨跌幅'])
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
            except:
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
        if "强烈买入" in signals['kdj']:
            score += 20
        elif "金叉" in signals['kdj']:
            score += 15
        elif "超卖" in signals['kdj']:
            score += 10
        elif "强烈卖出" in signals['kdj']:
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
            rating = "强烈买入"
        elif score >= 65:
            rating = "买入"
        elif score >= 50:
            rating = "持有"
        elif score >= 35:
            rating = "减持"
        else:
            rating = "卖出"

        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': rating,
            'signals': signals,
            'latest_price': latest['close'],
            'indicators': {
                'macd': round(latest['macd'], 3),
                'macd_signal': round(latest['macd_signal'], 3),
                'rsi': round(latest['rsi'], 1),
                'kdj_k': round(latest['kdj_k'], 1),
                'kdj_d': round(latest['kdj_d'], 1),
                'kdj_j': round(latest['kdj_j'], 1),
                'boll_upper': round(latest['boll_upper'], 2),
                'boll_mid': round(latest['boll_mid'], 2),
                'boll_lower': round(latest['boll_lower'], 2)
            }
        }

    def get_recommended_stocks_cn(self, num_stocks=10):
        """
        获取推荐股票列表（基于技术分析）
        使用预设的热门股票池
        """
        results = []

        # 分析预设的股票池
        for stock in POPULAR_CN_STOCKS[:20]:
            try:
                analysis = self.analyze_stock(stock['code'], market='CN', period='3mo')
                if analysis and analysis['score'] >= 60:
                    analysis['name'] = stock['name']
                    results.append(analysis)
            except Exception as e:
                continue

        # 按评分排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_short_term_recommendations(self, num_stocks=10):
        """
        获取短线推荐股票（基于短期动量指标）
        - 使用1个月数据
        - 更敏感的指标权重（KDJ、RSI权重更高）
        - 追求短期波动机会
        """
        results = []

        for stock in POPULAR_CN_STOCKS[:25]:
            try:
                analysis = self._analyze_short_term(stock['code'], market='CN')
                if analysis and analysis['score'] >= 55:
                    analysis['name'] = stock['name']
                    results.append(analysis)
            except Exception as e:
                continue

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_long_term_recommendations(self, num_stocks=10):
        """
        获取长线推荐股票（基于长期趋势指标）
        - 使用6个月数据
        - 更注重趋势指标（MACD、均线权重更高）
        - 追求稳定趋势机会
        """
        results = []

        for stock in POPULAR_CN_STOCKS[:25]:
            try:
                analysis = self._analyze_long_term(stock['code'], market='CN')
                if analysis and analysis['score'] >= 60:
                    analysis['name'] = stock['name']
                    results.append(analysis)
            except Exception as e:
                continue

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def _analyze_short_term(self, symbol, market='CN'):
        """
        短线分析 - 使用更短的周期和更敏感的指标权重
        """
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators

        fetcher = StockDataFetcher()
        data = fetcher.get_stock_data(symbol, period='1mo', interval='1d', market=market)

        if data is None or len(data) < 10:
            return None

        df = TechnicalIndicators.calculate_all(data)
        signals = TechnicalIndicators.get_signals(df)

        if 'error' in signals:
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
        if "强烈买入" in signals['kdj']:
            score += 30
        elif "金叉" in signals['kdj']:
            score += 25
        elif "超卖" in signals['kdj']:
            score += 20
        elif "强烈卖出" in signals['kdj']:
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
            rating = "强烈买入"
        elif score >= 65:
            rating = "买入"
        elif score >= 50:
            rating = "持有"
        elif score >= 35:
            rating = "减持"
        else:
            rating = "卖出"

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
                'rsi': round(latest['rsi'], 1),
                'kdj_k': round(latest['kdj_k'], 1),
                'kdj_d': round(latest['kdj_d'], 1),
                'kdj_j': round(latest['kdj_j'], 1),
            }
        }

    def _analyze_long_term(self, symbol, market='CN'):
        """
        长线分析 - 使用更长的周期和趋势跟踪指标权重
        """
        from data_fetcher import StockDataFetcher
        from technical_indicators import TechnicalIndicators

        fetcher = StockDataFetcher()
        data = fetcher.get_stock_data(symbol, period='6mo', interval='1d', market=market)

        if data is None or len(data) < 60:
            return None

        df = TechnicalIndicators.calculate_all(data)
        signals = TechnicalIndicators.get_signals(df)

        if 'error' in signals:
            return None

        latest = df.iloc[-1]

        # 长线评分系统 - 更注重趋势和稳定性
        score = 50

        # MACD评分（长线权重提高）- 趋势指标最重要
        if "金叉" in signals['macd']:
            score += 25
        elif "多头" in signals['macd']:
            score += 15
        elif "死叉" in signals['macd']:
            score -= 20
        elif "空头" in signals['macd']:
            score -= 10

        # RSI评分（长线权重降低）- 避免极端值即可
        rsi = latest['rsi']
        if rsi < 30:
            score += 10  # 超卖提供买入机会
        elif rsi > 70:
            score -= 10  # 超买注意风险

        # KDJ评分（长线权重适中）
        if "强烈买入" in signals['kdj']:
            score += 15
        elif "金叉" in signals['kdj']:
            score += 10
        elif "强烈卖出" in signals['kdj']:
            score -= 15
        elif "死叉" in signals['kdj']:
            score -= 10

        # 布林带评分（长线权重适中）
        if "反弹" in signals['boll']:
            score += 10
        elif "偏多" in signals['boll']:
            score += 5
        elif "回调" in signals['boll']:
            score -= 10

        # 长期均线系统评分（长线权重提高）
        if 'ma20' in df.columns and 'ma60' in df.columns:
            if latest['ma20'] > latest['ma60']:
                score += 20
                # 多头排列确认
                if len(df) > 1:
                    prev = df.iloc[-2]
                    if prev['ma20'] <= prev['ma60']:
                        score += 20  # 金叉形成，长线买入信号
            else:
                score -= 15

        # 价格相对长期均线位置
        if latest['close'] > latest['ma60']:
            score += 10
        else:
            score -= 10

        # 趋势持续性评分
        if len(df) > 20:
            price_trend = (latest['close'] - df.iloc[-20]['close']) / df.iloc[-20]['close'] * 100
            if price_trend > 10:  # 上升趋势
                score += 10
            elif price_trend > 5:
                score += 5
            elif price_trend < -10:  # 下降趋势
                score -= 10
            elif price_trend < -5:
                score -= 5

        score = max(0, min(100, score))

        if score >= 80:
            rating = "强烈买入"
        elif score >= 65:
            rating = "买入"
        elif score >= 50:
            rating = "持有"
        elif score >= 35:
            rating = "减持"
        else:
            rating = "卖出"

        return {
            'symbol': symbol,
            'score': round(score, 1),
            'rating': rating,
            'signals': signals,
            'latest_price': latest['close'],
            'strategy': '长线',
            'indicators': {
                'macd': round(latest['macd'], 3),
                'macd_signal': round(latest['macd_signal'], 3),
                'rsi': round(latest['rsi'], 1),
                'ma20': round(latest['ma20'], 2),
                'ma60': round(latest['ma60'], 2),
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
