"""
股票分析系统主程序
支持A股、港股、美股分析
包含: K线、RSI、MACD、KDJ、BOLL指标
以及热门股票和推荐股票功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import StockDataFetcher
from technical_indicators import TechnicalIndicators
from chart_plotter import ChartPlotter
from stock_recommendation import StockRecommender

from datetime import datetime


class StockAnalyzer:
    """股票分析主类"""

    def __init__(self):
        self.data_fetcher = StockDataFetcher()
        self.chart_plotter = ChartPlotter()
        self.recommender = StockRecommender()

    def analyze_stock(self, symbol, market='CN', period='1y', show_chart=True):
        """
        分析单个股票

        参数:
            symbol: 股票代码 (A股如: 000001, 美股如: AAPL)
            market: 市场 (CN-中国, US-美国, HK-香港)
            period: 时间周期
            show_chart: 是否显示图表
        """
        print(f"\n{'='*60}")
        print(f"正在分析: {symbol} ({market}) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        # 1. 获取股票基本信息
        print("\n【基本信息】")
        info = self.data_fetcher.get_stock_info(symbol, market)
        if info:
            if market == 'CN':
                print(f"股票名称: {info.get('股票简称', 'N/A')}")
                print(f"所属行业: {info.get('行业', 'N/A')}")
                print(f"总市值: {info.get('总市值', 'N/A')}")
            else:
                print(f"股票名称: {info.get('shortName', info.get('longName', 'N/A'))}")
                print(f"所属行业: {info.get('sector', 'N/A')}")
                print(f"市值: {info.get('marketCap', 'N/A')}")

        # 2. 获取实时行情
        print("\n【实时行情】")
        quote = self.data_fetcher.get_realtime_quote(symbol, market)
        if quote:
            print(f"最新价格: {quote['price']:.2f}")
            if 'change' in quote:
                change_color = "↑" if quote['change'] > 0 else "↓" if quote['change'] < 0 else "-"
                print(f"涨跌幅: {change_color} {quote['change']:.2f}%")
            print(f"成交量: {quote.get('volume', 'N/A'):,.0f}")
            print(f"今日最高: {quote.get('high', 'N/A'):.2f}")
            print(f"今日最低: {quote.get('low', 'N/A'):.2f}")

        # 3. 获取历史数据
        print(f"\n【获取历史数据】周期: {period}")
        data = self.data_fetcher.get_stock_data(symbol, period=period, market=market)

        if data is None or data.empty:
            print("获取数据失败，请检查股票代码是否正确")
            return None

        print(f"获取到 {len(data)} 条数据")

        # 4. 计算技术指标
        print("\n【计算技术指标】")
        data_with_indicators = TechnicalIndicators.calculate_all(data)

        # 5. 获取交易信号
        signals = TechnicalIndicators.get_signals(data_with_indicators)

        print("\n┌" + "─"*50 + "┐")
        print("│" + "技术指标分析".center(48) + "│")
        print("├" + "─"*50 + "┤")

        # MACD
        latest = data_with_indicators.iloc[-1]
        print(f"│ MACD: {signals['macd']:20s} │")
        print(f"│   MACD值: {latest['macd']:>10.3f}  Signal: {latest['macd_signal']:.3f} │")

        # RSI
        print(f"├" + "─"*50 + "┤")
        print(f"│ RSI(6): {signals['rsi']:18s} │")

        # KDJ
        print(f"├" + "─"*50 + "┤")
        print(f"│ KDJ: {signals['kdj']:20s} │")
        print(f"│   K: {latest['kdj_k']:>8.1f}  D: {latest['kdj_d']:>8.1f}  J: {latest['kdj_j']:>8.1f} │")

        # BOLL
        print(f"├" + "─"*50 + "┤")
        print(f"│ BOLL: {signals['boll']:19s} │")
        print(f"│   上轨: {latest['boll_upper']:>10.2f} 中轨: {latest['boll_mid']:>10.2f} │")
        print(f"│   下轨: {latest['boll_lower']:>10.2f} 带宽: {latest['boll_width']*100:>8.2f}% │")

        # 移动平均线
        print(f"├" + "─"*50 + "┤")
        print(f"│ 移动平均线: │")
        for ma in [5, 10, 20, 60]:
            col = f'ma{ma}'
            if col in latest:
                print(f"│   MA{ma}: {latest[col]:>10.2f} │")

        # 综合建议
        print(f"├" + "─"*50 + "┤")
        recommendation = signals['recommendation']
        rec_symbol = "★" if "偏多" in recommendation else "▼" if "偏空" in recommendation else "○"
        print(f"│ 综合建议: {rec_symbol} {recommendation:15s} │")
        print(f"└" + "─"*50 + "┘")

        # 6. 绘制图表
        if show_chart:
            print("\n正在生成图表...")
            stock_name = info.get('股票简称', symbol) if market == 'CN' else info.get('shortName', symbol)
            title = f"{symbol} {stock_name} 技术分析"
            self.chart_plotter.plot_with_indicators(data_with_indicators, title=title)

        return {
            'symbol': symbol,
            'data': data_with_indicators,
            'signals': signals,
            'info': info
        }

    def show_hot_stocks(self, market='CN', limit=15):
        """显示热门股票"""
        print(f"\n{'='*60}")
        print(f"{'热门股票':^60}")
        print(f"{'='*60}")

        if market == 'CN':
            hot_stocks = self.recommender.get_hot_stocks_cn(limit=limit)

            print(f"\n{'排名':<4} {'代码':<8} {'名称':<10} {'价格':<10} {'涨跌幅':<10} {'换手率':<8}")
            print("-" * 60)

            for i, stock in enumerate(hot_stocks, 1):
                change = stock['涨跌幅']
                change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
                print(f"{i:<4} {stock['代码']:<8} {stock['名称']:<10} "
                      f"{stock['最新价']:<10.2f} {change_str:<10} {stock['换手率']:.2f}%")

            # 显示涨幅榜
            print(f"\n{'='*60}")
            print("涨幅榜 TOP 10")
            print(f"{'='*60}")
            gainers = self.recommender.get_top_gainers_cn(limit=10)
            print(f"{'代码':<8} {'名称':<12} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 50)
            for stock in gainers:
                print(f"{stock['代码']:<8} {stock['名称']:<12} "
                      f"{stock['最新价']:<10.2f} +{stock['涨跌幅']:.2f}%")

            # 显示跌幅榜
            print(f"\n{'='*60}")
            print("跌幅榜 TOP 10")
            print(f"{'='*60}")
            losers = self.recommender.get_top_losers_cn(limit=10)
            print(f"{'代码':<8} {'名称':<12} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 50)
            for stock in losers:
                print(f"{stock['代码']:<8} {stock['名称']:<12} "
                      f"{stock['最新价']:<10.2f} {stock['涨跌幅']:.2f}%")

        elif market == 'HK':
            hot_stocks = self.recommender.get_hot_stocks_hk(limit=limit)

            print(f"\n{'排名':<4} {'代码':<8} {'名称':<10} {'价格':<10} {'涨跌幅':<10} {'换手率':<8}")
            print("-" * 60)

            for i, stock in enumerate(hot_stocks, 1):
                change = stock['涨跌幅']
                change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
                turnover = stock['换手率'] or 0
                print(f"{i:<4} {stock['代码']:<8} {stock['名称']:<10} "
                      f"{stock['最新价']:<10.2f} {change_str:<10} {turnover:.2f}%")

            # 显示涨幅榜
            print(f"\n{'='*60}")
            print("涨幅榜 TOP 10")
            print(f"{'='*60}")
            gainers = self.recommender.get_top_gainers_hk(limit=10)
            print(f"{'代码':<8} {'名称':<12} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 50)
            for stock in gainers:
                print(f"{stock['代码']:<8} {stock['名称']:<12} "
                      f"{stock['最新价']:<10.2f} +{stock['涨跌幅']:.2f}%")

            # 显示跌幅榜
            print(f"\n{'='*60}")
            print("跌幅榜 TOP 10")
            print(f"{'='*60}")
            losers = self.recommender.get_top_losers_hk(limit=10)
            print(f"{'代码':<8} {'名称':<12} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 50)
            for stock in losers:
                print(f"{stock['代码']:<8} {stock['名称']:<12} "
                      f"{stock['最新价']:<10.2f} {stock['涨跌幅']:.2f}%")

        else:
            hot_stocks = self.recommender.get_hot_stocks_us(limit=limit)
            print(f"\n{'排名':<4} {'代码':<8} {'名称':<15} {'价格':<10} {'涨跌幅':<10} {'成交量':<12}")
            print("-" * 70)

            for i, stock in enumerate(hot_stocks, 1):
                change_str = f"+{stock['change']:.2f}%" if stock['change'] > 0 else f"{stock['change']:.2f}%"
                volume = stock['volume'] / 1000000  # 百万
                print(f"{i:<4} {stock['symbol']:<8} {stock['name']:<15} "
                      f"{stock['price']:<10.2f} {change_str:<10} {volume:.2f}M")

            # 显示涨幅榜
            print(f"\n{'='*60}")
            print("涨幅榜 TOP 10")
            print(f"{'='*60}")
            gainers = self.recommender.get_top_gainers_us(limit=10)
            print(f"{'代码':<8} {'名称':<15} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 55)
            for stock in gainers:
                print(f"{stock['symbol']:<8} {stock['name']:<15} "
                      f"{stock['price']:<10.2f} +{stock['change']:.2f}%")

            # 显示跌幅榜
            print(f"\n{'='*60}")
            print("跌幅榜 TOP 10")
            print(f"{'='*60}")
            losers = self.recommender.get_top_losers_us(limit=10)
            print(f"{'代码':<8} {'名称':<15} {'价格':<10} {'涨跌幅':<10}")
            print("-" * 55)
            for stock in losers:
                print(f"{stock['symbol']:<8} {stock['name']:<15} "
                      f"{stock['price']:<10.2f} {stock['change']:.2f}%")

    def show_recommended_stocks(self, num_stocks=10):
        """显示推荐股票"""
        print(f"\n{'='*70}")
        print(f"{'基于技术分析的推荐股票':^70}")
        print(f"{'='*70}")
        print("\n正在分析股票池中各股票的技术指标，请稍候...\n")

        recommended = self.recommender.get_recommended_stocks_cn(num_stocks=num_stocks)

        if not recommended:
            print("暂无推荐股票")
            return

        print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'评分':<8} {'建议':<10} {'关键信号':<20}")
        print("-" * 70)

        for i, stock in enumerate(recommended, 1):
            # 获取关键信号
            key_signals = []
            if "金叉" in stock['signals']['macd']:
                key_signals.append("MACD金叉")
            if "超卖" in stock['signals']['rsi']:
                key_signals.append("RSI超卖")
            if "金叉" in stock['signals']['kdj']:
                key_signals.append("KDJ金叉")

            key_signal_str = ", ".join(key_signals) if key_signals else "趋势向好"

            print(f"{i:<4} {stock['symbol']:<8} {stock['name']:<10} "
                  f"{stock['score']:<8.1f} {stock['rating']:<10} {key_signal_str:<20}")

        print(f"\n{'='*70}")
        print("详细推荐信息:")
        print(f"{'='*70}")

        for i, stock in enumerate(recommended[:5], 1):
            print(f"\n{i}. {stock['symbol']} {stock['name']} (评分: {stock['score']})")
            print(f"   当前价格: {stock['latest_price']:.2f}")
            print(f"   技术指标:")
            print(f"     - RSI(6): {stock['indicators']['rsi']}")
            print(f"     - MACD: {stock['indicators']['macd']:.3f} (Signal: {stock['indicators']['macd_signal']:.3f})")
            print(f"     - KDJ: K={stock['indicators']['kdj_k']:.1f}, D={stock['indicators']['kdj_d']:.1f}, J={stock['indicators']['kdj_j']:.1f}")
            print(f"     - BOLL: 上轨={stock['indicators']['boll_upper']:.2f}, 中轨={stock['indicators']['boll_mid']:.2f}, 下轨={stock['indicators']['boll_lower']:.2f}")
            print(f"   信号分析:")
            print(f"     - MACD: {stock['signals']['macd']}")
            print(f"     - RSI: {stock['signals']['rsi']}")
            print(f"     - KDJ: {stock['signals']['kdj']}")
            print(f"     - BOLL: {stock['signals']['boll']}")

    def interactive_menu(self):
        """交互式菜单"""
        while True:
            print(f"\n{'='*60}")
            print(f"{'股票分析系统':^60}")
            print(f"{'='*60}")
            print("1. 分析个股")
            print("2. 查看热门股票")
            print("3. 查看推荐股票")
            print("4. 对比多只股票")
            print("0. 退出")
            print(f"{'='*60}")

            choice = input("\n请选择功能 (0-4): ").strip()

            if choice == '1':
                symbol = input("请输入股票代码 (如: 000001 或 AAPL): ").strip()
                market = input("市场 (CN/US/HK, 默认CN): ").strip().upper() or 'CN'
                period = input("分析周期 (1mo/3mo/6mo/1y/2y, 默认1y): ").strip() or '1y'

                self.analyze_stock(symbol, market=market, period=period, show_chart=True)

            elif choice == '2':
                market = input("市场 (CN/US/HK, 默认CN): ").strip().upper() or 'CN'
                self.show_hot_stocks(market=market)

            elif choice == '3':
                self.show_recommended_stocks(num_stocks=10)

            elif choice == '4':
                symbols = input("请输入股票代码，用逗号分隔 (如: 000001,000002,000858): ").strip()
                market = input("市场 (CN/US/HK, 默认CN): ").strip().upper() or 'CN'
                symbol_list = [s.strip() for s in symbols.split(',')]

                for symbol in symbol_list:
                    self.analyze_stock(symbol, market=market, period='3mo', show_chart=False)

            elif choice == '0':
                print("感谢使用，再见！")
                break

            else:
                print("无效选择，请重试")


def quick_demo():
    """快速演示"""
    analyzer = StockAnalyzer()

    # 分析一只A股
    print("\n" + "="*60)
    print("快速演示: 分析平安银行(000001)")
    print("="*60)
    analyzer.analyze_stock('000001', market='CN', period='6mo', show_chart=True)

    # 显示热门股票
    # analyzer.show_hot_stocks(market='CN', limit=10)

    # 显示推荐股票
    # analyzer.show_recommended_stocks(num_stocks=5)


def _run_ai_analysis(result, args):
    """CLI AI 分析入口"""
    from config import AI_API_KEY, AI_MODEL, AI_BASE_URL
    from ai_analysis import build_indicator_snapshot, call_ai_analysis, run_multi_agent_analysis

    if not AI_API_KEY:
        print("错误：未设置 AI_API_KEY 环境变量")
        return

    data = result["data"]
    signals = result["signals"]
    symbol = result["symbol"]
    info = result.get("info", {})
    stock_name = info.get("股票简称", info.get("shortName", symbol))

    snapshot = build_indicator_snapshot(data, signals, symbol, stock_name)

    if args.multi_agent:
        print("\n【多Agent协作AI分析】")
        print("启动 技术分析Agent + 风险评估Agent → 决策综合Agent")
        try:
            output = run_multi_agent_analysis(snapshot, AI_MODEL, AI_API_KEY, AI_BASE_URL)
        except Exception as e:
            print(f"AI 分析失败：{e}")
            return

        tech = output.get("technical", {})
        risk = output.get("risk", {})
        decision = output.get("decision", {})

        # 技术分析结果
        tech_struct = tech.get("structured", {})
        if tech_struct:
            print("\n── 技术指标解读 ──")
            for key in ["MACD解读", "RSI解读", "KDJ解读", "布林带解读", "均线解读", "指标一致性"]:
                val = tech_struct.get(key, "")
                if val:
                    print(f"  {key}: {val}")

        # 风险评估结果
        risk_struct = risk.get("structured", {})
        if risk_struct:
            print("\n── 风险评估 ──")
            print(f"  风险等级: {risk_struct.get('风险等级', 'N/A')}")
            for f in risk_struct.get("风险因素", []):
                print(f"  - {f}")
            conflict = risk_struct.get("矛盾信号", "")
            if conflict:
                print(f"  矛盾信号: {conflict}")
            levels = risk_struct.get("关注点位", {})
            if levels:
                for name, val in levels.items():
                    print(f"  {name}: {val}")

        # 决策
        dec_struct = decision.get("structured", {})
        if dec_struct:
            print("\n── 综合决策 ──")
            print(f"  结论: {dec_struct.get('核心结论', 'N/A')}")
            print(f"  评分: {dec_struct.get('技术面评分', 'N/A')}")
            print(f"  信心度: {dec_struct.get('信心度', 'N/A')}")
            ref = dec_struct.get("操作参考", "")
            if ref:
                print(f"  操作参考: {ref}")
            points = dec_struct.get("关注要点", [])
            if points:
                print("  关注要点:")
                for p in points:
                    print(f"    - {p}")

        if tech.get("error"):
            print(f"  技术Agent错误: {tech['error']}")
        if risk.get("error"):
            print(f"  风险Agent错误: {risk['error']}")
        if decision.get("error"):
            print(f"  决策Agent错误: {decision['error']}")
    else:
        print("\n【AI 智能解读】")
        try:
            result_ai = call_ai_analysis(snapshot, AI_MODEL, AI_API_KEY, AI_BASE_URL)
        except Exception as e:
            print(f"AI 分析失败：{e}")
            return

        print(f"\n  核心结论: {result_ai.get('核心结论', 'N/A')}")
        risks = result_ai.get("风险提示", [])
        if risks:
            print("  风险提示:")
            for r in risks:
                print(f"    - {r}")
        levels = result_ai.get("关键点位", {})
        if levels:
            print("  关键点位:")
            for name, val in levels.items():
                print(f"    {name}: {val}")
        ref = result_ai.get("操作参考", "")
        if ref:
            print(f"  操作参考: {ref}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='股票分析系统')
    parser.add_argument('--symbol', '-s', help='股票代码')
    parser.add_argument('--market', '-m', default='CN', help='市场 (CN/US/HK)')
    parser.add_argument('--period', '-p', default='1y', help='分析周期')
    parser.add_argument('--hot', action='store_true', help='显示热门股票')
    parser.add_argument('--recommend', action='store_true', help='显示推荐股票')
    parser.add_argument('--demo', action='store_true', help='运行演示')
    parser.add_argument('--interactive', '-i', action='store_true', help='交互模式')
    parser.add_argument('--schedule', action='store_true', help='启动定时调度（需先配置环境变量）')
    parser.add_argument('--notify', action='store_true', help='运行一次分析并推送通知')
    parser.add_argument('--backtest', '-b', action='store_true', help='对指定股票执行回测')
    parser.add_argument('--ai', action='store_true', help='使用AI分析（单Agent模式）')
    parser.add_argument('--multi-agent', action='store_true', help='使用多Agent协作AI分析')

    args = parser.parse_args()

    analyzer = StockAnalyzer()

    if args.schedule:
        from scheduler import start_scheduler
        start_scheduler()
    elif args.notify:
        from scheduler import run_scheduled_analysis
        run_scheduled_analysis()
    elif args.backtest:
        from backtest_adapter import BacktestAdapter
        adapter = BacktestAdapter()
        symbol = args.symbol or input("请输入股票代码: ").strip()
        output = adapter.run(symbol=symbol, market=args.market, period=args.period)
        summary = output["summary"]
        results = output["results"]
        completed = [r for r in results if r.get("eval_status") == "completed"]

        print(f"\n{'='*60}")
        print(f"回测结果: {symbol} ({args.market})")
        print(f"{'='*60}")
        print(f"总信号数: {summary.get('total_evaluations', 0)}")
        print(f"做多/做空: {summary.get('long_count', 0)}/{summary.get('cash_count', 0)}")
        print(f"方向准确率: {summary.get('direction_accuracy_pct', 'N/A')}%")
        print(f"胜率(不含平): {summary.get('win_rate_pct', 'N/A')}%")
        print(f"赢/输/平: {summary.get('win_count', 0)}/{summary.get('loss_count', 0)}/{summary.get('neutral_count', 0)}")
        print(f"平均持仓收益: {summary.get('avg_stock_return_pct', 'N/A')}%")
        print(f"平均模拟收益: {summary.get('avg_simulated_return_pct', 'N/A')}%")
        print(f"止损触发率: {summary.get('stop_loss_trigger_rate', 'N/A')}%")
        print(f"止盈触发率: {summary.get('take_profit_trigger_rate', 'N/A')}%")

        signal_bd = summary.get("signal_breakdown", {})
        if signal_bd:
            print(f"\n信号分类:")
            for sig, stats in signal_bd.items():
                print(f"  {sig}: 总数{stats['total']} 胜{stats['win']} 负{stats['loss']} 胜率{stats['win_rate_pct']}%")

        if completed:
            print(f"\n最近5条明细:")
            for r in completed[-5:]:
                print(f"  {r.get('analysis_date')} | {r.get('signal', ''):12s} | 入场{r.get('start_price'):.2f} | "
                      f"收益{r.get('stock_return_pct', 0):+.2f}% | {r.get('outcome', '')}")

        adapter.save_results(symbol, args.market, output)
    elif args.demo:
        quick_demo()
    elif args.interactive:
        analyzer.interactive_menu()
    elif args.hot:
        analyzer.show_hot_stocks(market=args.market)
    elif args.recommend:
        analyzer.show_recommended_stocks()
    elif args.symbol:
        result = analyzer.analyze_stock(args.symbol, market=args.market, period=args.period, show_chart=True)

        # AI 分析
        if args.ai or args.multi_agent:
            _run_ai_analysis(result, args)

    else:
        # 默认进入交互模式
        analyzer.interactive_menu()
