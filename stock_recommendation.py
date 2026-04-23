"""
热门股票和推荐股票模块
基于技术指标和市场数据筛选优质股票
"""
import akshare as ak
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')


class StockRecommender:
    """股票推荐器"""

    def __init__(self):
        self.hot_stocks_cache = None
        self.hot_stocks_cache_time = None

    def get_hot_stocks_cn(self, limit=20):
        """
        获取A股热门股票
        基于成交量、涨跌幅等指标
        """
        try:
            # 获取A股实时行情
            df = ak.stock_zh_a_spot_em()

            # 筛选条件
            df = df[df['最新价'] > 0]  # 有交易的股票
            df = df[df['换手率'] > 1]   # 换手率大于1%
            df = df[df['成交量'] > 1000000]  # 成交量大于100万

            # 计算热度分数 (综合考虑成交量、涨跌幅、换手率)
            df['热度分数'] = (
                df['换手率'].rank(pct=True) * 0.3 +
                df['涨跌幅'].abs().rank(pct=True) * 0.3 +
                df['成交量'].rank(pct=True) * 0.2 +
                df['成交额'].rank(pct=True) * 0.2
            )

            # 排序并选择需要的列
            hot_stocks = df.nlargest(limit, '热度分数')[
                ['代码', '名称', '最新价', '涨跌幅', '换手率', '成交量', '成交额', '热度分数']
            ]

            return hot_stocks.to_dict('records')

        except Exception as e:
            print(f"获取热门股票失败: {e}")
            return []

    def get_top_gainers_cn(self, limit=10):
        """获取A股涨幅榜"""
        try:
            df = ak.stock_zh_a_spot_em()
            df = df[df['涨跌幅'] > 0]
            gainers = df.nlargest(limit, '涨跌幅')[
                ['代码', '名称', '最新价', '涨跌幅', '换手率']
            ]
            return gainers.to_dict('records')
        except Exception as e:
            print(f"获取涨幅榜失败: {e}")
            return []

    def get_top_losers_cn(self, limit=10):
        """获取A股跌幅榜"""
        try:
            df = ak.stock_zh_a_spot_em()
            df = df[df['涨跌幅'] < 0]
            losers = df.nsmallest(limit, '涨跌幅')[
                ['代码', '名称', '最新价', '涨跌幅', '换手率']
            ]
            return losers.to_dict('records')
        except Exception as e:
            print(f"获取跌幅榜失败: {e}")
            return []

    def get_volume_leaders_cn(self, limit=10):
        """获取A股成交量榜"""
        try:
            df = ak.stock_zh_a_spot_em()
            leaders = df.nlargest(limit, '成交量')[
                ['代码', '名称', '最新价', '涨跌幅', '成交量', '成交额']
            ]
            return leaders.to_dict('records')
        except Exception as e:
            print(f"获取成交量榜失败: {e}")
            return []

    def get_hot_stocks_us(self, limit=20):
        """获取美股热门股票"""
        # 一些常关注的美股代码
        popular_us_stocks = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'AMD', 'INTC', 'CRM', 'ADBE', 'PYPL', 'UBER', 'LYFT', 'ZM',
            'BABA', 'JD', 'PDD', 'TCEHY', 'BIDU', 'NIO', 'XPEV', 'LI',
            'SPY', 'QQQ', 'IWM', 'VTI', 'VOO', 'ARKK', 'XLF', 'XLK'
        ]

        results = []

        def fetch_stock_info(symbol):
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period="5d")

                if hist.empty or len(hist) < 2:
                    return None

                latest = hist.iloc[-1]
                prev_close = hist.iloc[-2]['Close']
                change_pct = ((latest['Close'] - prev_close) / prev_close) * 100

                return {
                    'symbol': symbol,
                    'name': info.get('shortName', symbol),
                    'price': latest['Close'],
                    'change': change_pct,
                    'volume': latest['Volume'],
                    'market_cap': info.get('marketCap', 0),
                    'sector': info.get('sector', 'N/A')
                }
            except:
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_stock_info, symbol): symbol
                      for symbol in popular_us_stocks}

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
        返回评分和建议
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

        # MACD评分 (+20)
        if "金叉" in signals['macd']:
            score += 15
        elif "多头" in signals['macd']:
            score += 10
        elif "死叉" in signals['macd']:
            score -= 10

        # RSI评分 (+20)
        rsi = latest['rsi']
        if rsi < 30:  # 超卖，可能反弹
            score += 15
        elif rsi < 40:
            score += 10
        elif rsi > 70:  # 超买
            score -= 10
        elif rsi > 60:
            score -= 5

        # KDJ评分 (+20)
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

        # 布林带评分 (+20)
        if "反弹" in signals['boll']:
            score += 15
        elif "偏多" in signals['boll']:
            score += 10
        elif "回调" in signals['boll']:
            score -= 10
        elif "偏空" in signals['boll']:
            score -= 5

        # 趋势评分 (+20)
        if 'ma5' in df.columns and 'ma20' in df.columns:
            if latest['ma5'] > latest['ma20']:
                score += 10
                # 检查金叉
                prev = df.iloc[-2]
                if prev['ma5'] <= prev['ma20']:
                    score += 10  # MA金叉
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
        获取推荐股票列表 (基于技术分析)
        """
        try:
            # 先获取热门股票池
            df = ak.stock_zh_a_spot_em()

            # 筛选条件 - 选择流动性好的股票
            df = df[
                (df['最新价'] > 5) &  # 价格大于5元
                (df['换手率'] > 1) &   # 有活跃度
                (df['成交量'] > 1000000) &
                (df['涨跌幅'] > -5) &  # 排除大跌股票
                (df['涨跌幅'] < 10)    # 排除涨停股票
            ]

            # 随机选择一部分股票进行分析 (避免分析太多)
            sample_size = min(50, len(df))
            sample_stocks = df.sample(n=sample_size)[['代码', '名称']].values.tolist()

            # 分析每只股票
            results = []
            for code, name in sample_stocks:
                try:
                    analysis = self.analyze_stock(code, market='CN', period='3mo')
                    if analysis and analysis['score'] >= 60:
                        analysis['name'] = name
                        results.append(analysis)
                except Exception as e:
                    continue

            # 按评分排序
            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:num_stocks]

        except Exception as e:
            print(f"获取推荐股票失败: {e}")
            return []

    def get_sector_performance_cn(self):
        """获取A股板块表现"""
        try:
            # 获取行业板块
            sectors = ak.stock_board_industry_name_em()

            sector_data = []
            for _, row in sectors.head(20).iterrows():
                try:
                    board_name = row['板块名称']
                    # 获取板块详情
                    board_df = ak.stock_board_industry_hist_em(
                        symbol=board_name,
                        period="日k",
                        adjust=""
                    )
                    if not board_df.empty:
                        latest = board_df.iloc[-1]
                        prev = board_df.iloc[-2] if len(board_df) > 1 else latest
                        change = ((latest['收盘'] - prev['收盘']) / prev['收盘'] * 100)

                        sector_data.append({
                            'name': board_name,
                            'change': round(change, 2),
                            'volume': latest.get('成交量', 0),
                            'leading_stock': row.get('领涨股', 'N/A')
                        })
                except:
                    continue

            # 按涨跌幅排序
            sector_data.sort(key=lambda x: x['change'], reverse=True)
            return sector_data[:10]

        except Exception as e:
            print(f"获取板块表现失败: {e}")
            return []


if __name__ == "__main__":
    # 测试代码
    recommender = StockRecommender()

    print("=== A股热门股票 ===")
    hot_stocks = recommender.get_hot_stocks_cn(limit=10)
    for stock in hot_stocks:
        print(f"{stock['代码']} {stock['名称']}: 价格{stock['最新价']}, "
              f"涨跌{stock['涨跌幅']}%, 换手{stock['换手率']}%")

    print("\n=== 推荐股票 ===")
    recommended = recommender.get_recommended_stocks_cn(num_stocks=5)
    for stock in recommended:
        print(f"{stock['symbol']} {stock['name']}: 评分{stock['score']}, 建议{stock['rating']}")
