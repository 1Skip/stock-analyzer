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
                if analysis:
                    analysis['name'] = stock['name']
                    results.append(analysis)
                    print(f"短线分析 {stock['code']}: 评分={analysis['score']}")
                else:
                    print(f"短线分析 {stock['code']}: 返回None")
            except Exception as e:
                print(f"短线分析 {stock['code']} 异常: {str(e)}")
                continue

        # 按评分排序，返回前num_stocks个
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:num_stocks]

    def get_sector_short_term_recommendations(self, sector_name, num_stocks=5):
        """
        获取指定板块的短线龙头股推荐
        """
        if sector_name not in SECTOR_STOCKS:
            return []

        results = []
        sector_stocks = SECTOR_STOCKS[sector_name]

        for stock in sector_stocks:
            try:
                analysis = self._analyze_short_term(stock['code'], market='CN')
                if analysis:
                    analysis['name'] = stock['name']
                    analysis['sector'] = sector_name
                    results.append(analysis)
                    print(f"板块{sector_name}分析 {stock['code']}: 评分={analysis['score']}")
                else:
                    print(f"板块{sector_name}分析 {stock['code']}: 返回None")
            except Exception as e:
                print(f"板块{sector_name}分析 {stock['code']} 异常: {str(e)}")
                continue

        # 按评分排序，返回前num_stocks个
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
