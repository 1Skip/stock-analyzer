"""CLI 主程序测试"""
import sys
import pytest
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_data():
    """含完整指标的 60 天数据"""
    dates = pd.date_range('2026-01-01', periods=60, freq='B')
    np.random.seed(0)
    close = 10 + np.cumsum(np.random.randn(60) * 0.3)
    df = pd.DataFrame({
        'open': close - 0.1,
        'high': close + 0.3,
        'low': close - 0.3,
        'close': close,
        'volume': np.random.randint(1000000, 5000000, 60),
        'macd': np.random.randn(60) * 0.3,
        'macd_signal': np.random.randn(60) * 0.2,
        'macd_hist': np.random.randn(60) * 0.1,
        'rsi': np.random.uniform(30, 70, 60),
        'rsi_6': np.random.uniform(30, 70, 60),
        'rsi_12': np.random.uniform(30, 70, 60),
        'rsi_24': np.random.uniform(30, 70, 60),
        'kdj_k': np.random.uniform(20, 80, 60),
        'kdj_d': np.random.uniform(20, 80, 60),
        'kdj_j': np.random.uniform(20, 80, 60),
        'boll_upper': close + 0.5,
        'boll_mid': close,
        'boll_lower': close - 0.5,
        'boll_width': np.full(60, 0.05),
        'boll_percent': np.random.uniform(0, 100, 60),
        'ma5': close + 0.05,
        'ma10': close + 0.02,
        'ma20': close - 0.02,
        'ma60': close - 0.05,
    }, index=dates)
    return df


@pytest.fixture
def mock_components(monkeypatch, sample_data):
    """Mock 数据获取和图表绘制组件"""
    from data_fetcher import StockDataFetcher
    from technical_indicators import TechnicalIndicators
    from chart_plotter import ChartPlotter

    # Mock get_stock_info
    monkeypatch.setattr(StockDataFetcher, 'get_stock_info',
                        lambda self, symbol, market: {
                            '股票简称': f'测试股{symbol}',
                            '行业': '测试行业',
                            '总市值': '100亿',
                        })

    # Mock get_realtime_quote
    monkeypatch.setattr(StockDataFetcher, 'get_realtime_quote',
                        lambda self, symbol, market: {
                            'price': 15.5,
                            'change': 2.5,
                            'volume': 5000000,
                            'high': 16.0,
                            'low': 15.0,
                        })

    # Mock get_stock_data
    monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                        lambda self, symbol, period='1y', interval='1d', market='CN': sample_data)

    # Mock calculate_all
    monkeypatch.setattr(TechnicalIndicators, 'calculate_all', lambda d: d)

    # Mock get_signals
    monkeypatch.setattr(TechnicalIndicators, 'get_signals', lambda d: {
        'macd': 'MACD金叉，偏多',
        'rsi': 'RSI 45，中性',
        'kdj': 'KDJ向上，偏多',
        'boll': '中轨附近',
        'recommendation': '偏多信号',
    })

    # Mock plot_with_indicators (no-op)
    monkeypatch.setattr(ChartPlotter, 'plot_with_indicators',
                        lambda self, data, title=None, save_path=None, color_scheme='red_up': None)


# ============================================================
# TestStockAnalyzerInit
# ============================================================

class TestStockAnalyzerInit:

    def test_creates_components(self):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        assert analyzer.data_fetcher is not None
        assert analyzer.chart_plotter is not None
        assert analyzer.recommender is not None


# ============================================================
# TestAnalyzeStock
# ============================================================

class TestAnalyzeStock:

    def test_returns_dict(self, mock_components):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('000001', market='CN', period='3mo', show_chart=False)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self, mock_components):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('000001', show_chart=False)
        for key in ['symbol', 'data', 'signals', 'info']:
            assert key in result

    def test_symbol_in_result(self, mock_components):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('000001', show_chart=False)
        assert result['symbol'] == '000001'

    def test_no_data_returns_none(self, monkeypatch):
        from main import StockAnalyzer
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_info',
                            lambda self, symbol, market: {'股票简称': '测试'})
        monkeypatch.setattr(StockDataFetcher, 'get_realtime_quote',
                            lambda self, symbol, market: {'price': 10.0, 'change': 0, 'volume': 0, 'high': 10, 'low': 10})
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                            lambda self, symbol, period='1y', interval='1d', market='CN': pd.DataFrame())

        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('000001', show_chart=False)
        assert result is None

    def test_show_chart_calls_plotter(self, mock_components, monkeypatch):
        from main import StockAnalyzer
        from chart_plotter import ChartPlotter

        called_with_title = {}

        def capture_plot(self, data, title=None, save_path=None, color_scheme='red_up'):
            called_with_title['title'] = title

        monkeypatch.setattr(ChartPlotter, 'plot_with_indicators', capture_plot)

        analyzer = StockAnalyzer()
        analyzer.analyze_stock('000001', show_chart=True)
        assert '000001' in called_with_title.get('title', '')

    def test_hk_market_works(self, mock_components, monkeypatch):
        from main import StockAnalyzer
        from data_fetcher import StockDataFetcher
        # HK market uses different info format
        monkeypatch.setattr(StockDataFetcher, 'get_stock_info',
                            lambda self, symbol, market: {
                                'shortName': 'Tencent',
                                'sector': 'Technology',
                                'marketCap': 500000000000,
                            })
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('00700', market='HK', show_chart=False)
        assert result is not None
        assert result['symbol'] == '00700'

    def test_us_market_works(self, mock_components, monkeypatch):
        from main import StockAnalyzer
        from data_fetcher import StockDataFetcher
        monkeypatch.setattr(StockDataFetcher, 'get_stock_info',
                            lambda self, symbol, market: {
                                'shortName': 'Apple Inc.',
                                'sector': 'Technology',
                                'marketCap': 3000000000000,
                            })
        analyzer = StockAnalyzer()
        result = analyzer.analyze_stock('AAPL', market='US', show_chart=False)
        assert result is not None
        assert result['symbol'] == 'AAPL'


# ============================================================
# TestArgparse
# ============================================================

class TestArgparse:

    def test_symbol_flag(self):
        """--symbol / -s 参数"""
        import argparse
        parser = argparse.ArgumentParser(description='股票分析系统')
        parser.add_argument('--symbol', '-s', help='股票代码')
        parser.add_argument('--market', '-m', default='CN', help='市场')
        parser.add_argument('--period', '-p', default='1y', help='周期')
        parser.add_argument('--hot', action='store_true', help='热门')
        parser.add_argument('--recommend', action='store_true', help='推荐')
        parser.add_argument('--demo', action='store_true', help='演示')
        parser.add_argument('--interactive', '-i', action='store_true', help='交互')

        args = parser.parse_args(['-s', '000001'])
        assert args.symbol == '000001'
        assert args.market == 'CN'

    def test_market_flag(self):
        import argparse
        parser = argparse.ArgumentParser(description='股票分析系统')
        parser.add_argument('--symbol', '-s')
        parser.add_argument('--market', '-m', default='CN')
        parser.add_argument('--period', '-p', default='1y')
        parser.add_argument('--hot', action='store_true')
        parser.add_argument('--recommend', action='store_true')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--interactive', '-i', action='store_true')

        args = parser.parse_args(['-m', 'HK', '--symbol', '00700'])
        assert args.market == 'HK'

    def test_hot_flag(self):
        import argparse
        parser = argparse.ArgumentParser(description='股票分析系统')
        parser.add_argument('--symbol', '-s')
        parser.add_argument('--market', '-m', default='CN')
        parser.add_argument('--period', '-p', default='1y')
        parser.add_argument('--hot', action='store_true')
        parser.add_argument('--recommend', action='store_true')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--interactive', '-i', action='store_true')

        args = parser.parse_args(['--hot'])
        assert args.hot is True

    def test_interactive_short_flag(self):
        import argparse
        parser = argparse.ArgumentParser(description='股票分析系统')
        parser.add_argument('--symbol', '-s')
        parser.add_argument('--market', '-m', default='CN')
        parser.add_argument('--period', '-p', default='1y')
        parser.add_argument('--hot', action='store_true')
        parser.add_argument('--recommend', action='store_true')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--interactive', '-i', action='store_true')

        args = parser.parse_args(['-i'])
        assert args.interactive is True

    def test_defaults(self):
        import argparse
        parser = argparse.ArgumentParser(description='股票分析系统')
        parser.add_argument('--symbol', '-s')
        parser.add_argument('--market', '-m', default='CN')
        parser.add_argument('--period', '-p', default='1y')
        parser.add_argument('--hot', action='store_true')
        parser.add_argument('--recommend', action='store_true')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--interactive', '-i', action='store_true')

        args = parser.parse_args([])
        assert args.market == 'CN'
        assert args.period == '1y'
        assert args.hot is False
        assert args.interactive is False


# ============================================================
# TestRunAIAnalysis
# ============================================================

class TestRunAIAnalysis:

    def test_no_api_key_returns_early(self, monkeypatch):
        """未设置 AI_API_KEY 时直接返回"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", None)
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        # 不应抛异常
        result = {"data": None, "signals": {}, "symbol": "000001", "info": {}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": False})())

    def test_single_agent_success(self, monkeypatch, capsys):
        """单Agent模式成功返回"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        mock_result_ai = {
            "核心结论": "短期看涨",
            "风险提示": ["成交量不足"],
            "关键点位": {"支撑": "10.0", "压力": "12.0"},
            "操作参考": "逢低吸纳",
        }
        monkeypatch.setattr("ai_analysis.call_ai_analysis",
                           lambda snapshot, model, key, base_url: mock_result_ai)
        monkeypatch.setattr("ai_analysis.build_indicator_snapshot",
                           lambda data, signals, symbol, stock_name: "snapshot")

        data = pd.DataFrame({"close": [10, 11, 12]})
        signals = {"recommendation": "偏多信号"}
        result = {"data": data, "signals": signals, "symbol": "000001",
                  "info": {"股票简称": "测试股"}}

        _run_ai_analysis(result, type("Args", (), {"multi_agent": False})())
        captured = capsys.readouterr().out
        assert "短期看涨" in captured

    def test_single_agent_exception(self, monkeypatch, capsys):
        """单Agent模式异常处理"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        monkeypatch.setattr("ai_analysis.call_ai_analysis",
                           lambda *a, **kw: (_ for _ in ()).throw(Exception("API error")))
        monkeypatch.setattr("ai_analysis.build_indicator_snapshot",
                           lambda data, signals, symbol, stock_name: "snapshot")

        result = {"data": pd.DataFrame({"close": [10]}), "signals": {},
                  "symbol": "000001", "info": {}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": False})())
        captured = capsys.readouterr().out
        assert "AI 分析失败" in captured

    def test_multi_agent_success(self, monkeypatch, capsys):
        """多Agent模式成功"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        mock_output = {
            "technical": {
                "structured": {
                    "MACD解读": "金叉形成",
                    "RSI解读": "中性偏强",
                    "KDJ解读": "向上发散",
                    "布林带解读": "上轨附近",
                    "均线解读": "多头排列",
                    "指标一致性": "一致偏多",
                },
                "error": None,
            },
            "risk": {
                "structured": {
                    "风险等级": "中等",
                    "风险因素": ["估值偏高"],
                    "矛盾信号": "无",
                    "关注点位": {"支撑": "10.0"},
                },
                "error": None,
            },
            "decision": {
                "structured": {
                    "核心结论": "逢低布局",
                    "技术面评分": "75",
                    "信心度": "中高",
                    "操作参考": "分批建仓",
                    "关注要点": ["量能变化", "20日线支撑"],
                },
                "error": None,
            },
        }
        monkeypatch.setattr("ai_analysis.run_multi_agent_analysis",
                           lambda snapshot, model, key, base_url: mock_output)
        monkeypatch.setattr("ai_analysis.build_indicator_snapshot",
                           lambda data, signals, symbol, stock_name: "snapshot")

        result = {"data": pd.DataFrame({"close": [10]}), "signals": {},
                  "symbol": "000001", "info": {"股票简称": "测试"}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": True})())
        captured = capsys.readouterr().out
        assert "逢低布局" in captured

    def test_multi_agent_exception(self, monkeypatch, capsys):
        """多Agent模式异常"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        monkeypatch.setattr("ai_analysis.run_multi_agent_analysis",
                           lambda *a, **kw: (_ for _ in ()).throw(Exception("multi-agent error")))
        monkeypatch.setattr("ai_analysis.build_indicator_snapshot",
                           lambda data, signals, symbol, stock_name: "snapshot")

        result = {"data": pd.DataFrame({"close": [10]}), "signals": {},
                  "symbol": "000001", "info": {}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": True})())
        captured = capsys.readouterr().out
        assert "AI 分析失败" in captured

    def test_multi_agent_partial_errors(self, monkeypatch, capsys):
        """多Agent中部分Agent报错"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        mock_output = {
            "technical": {"structured": {}, "error": "技术分析超时"},
            "risk": {"structured": {}, "error": "风险评估超时"},
            "decision": {"structured": {"核心结论": "观望"}, "error": None},
        }
        monkeypatch.setattr("ai_analysis.run_multi_agent_analysis",
                           lambda *a, **kw: mock_output)
        monkeypatch.setattr("ai_analysis.build_indicator_snapshot",
                           lambda data, signals, symbol, stock_name: "snapshot")
        result = {"data": pd.DataFrame({"close": [10]}), "signals": {},
                  "symbol": "000001", "info": {}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": True})())
        captured = capsys.readouterr().out
        assert "技术分析超时" in captured
        assert "风险评估超时" in captured

    def test_single_agent_from_stock_name_fallback(self, monkeypatch):
        """info 无股票名称时用 symbol 兜底 (single agent)"""
        from main import _run_ai_analysis
        monkeypatch.setattr("config.AI_API_KEY", "test-key")
        monkeypatch.setattr("config.AI_MODEL", "test-model")
        monkeypatch.setattr("config.AI_BASE_URL", None)

        called_snapshot = {}
        monkeypatch.setattr("ai_analysis.call_ai_analysis",
                           lambda snapshot, model, key, base_url: {"核心结论": "ok"})

        def capture_snapshot(data, signals, symbol, stock_name):
            called_snapshot["stock_name"] = stock_name
            return "mock snapshot"

        monkeypatch.setattr("ai_analysis.build_indicator_snapshot", capture_snapshot)

        result = {"data": pd.DataFrame({"close": [10]}), "signals": {},
                  "symbol": "000001", "info": {}}
        _run_ai_analysis(result, type("Args", (), {"multi_agent": False})())
        assert called_snapshot["stock_name"] == "000001"


# ============================================================
# TestShowHotStocks
# ============================================================

class TestShowHotStocks:

    def _make_stock_cn(self):
        return [
            {"代码": "000001", "名称": "平安银行", "最新价": 12.5, "涨跌幅": 2.5, "换手率": 1.2},
            {"代码": "000002", "名称": "万科A", "最新价": 15.0, "涨跌幅": -1.0, "换手率": 0.8},
        ]

    def _make_stock_us(self):
        return [
            {"symbol": "AAPL", "name": "Apple Inc.", "price": 180.0, "change": 1.5, "volume": 50000000},
        ]

    def test_cn_market(self, monkeypatch, capsys):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        monkeypatch.setattr(analyzer.recommender, "get_hot_stocks_cn",
                           lambda limit: self._make_stock_cn())
        monkeypatch.setattr(analyzer.recommender, "get_top_gainers_cn",
                           lambda limit: [self._make_stock_cn()[0]])
        monkeypatch.setattr(analyzer.recommender, "get_top_losers_cn",
                           lambda limit: [self._make_stock_cn()[1]])

        analyzer.show_hot_stocks(market="CN")
        captured = capsys.readouterr().out
        assert "热门股票" in captured
        assert "平安银行" in captured
        assert "涨幅榜" in captured
        assert "跌幅榜" in captured

    def test_hk_market(self, monkeypatch, capsys):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        hk_stocks = [
            {"代码": "00700", "名称": "腾讯", "最新价": 380.0, "涨跌幅": 2.0, "换手率": 0.5},
        ]
        monkeypatch.setattr(analyzer.recommender, "get_hot_stocks_hk",
                           lambda limit: hk_stocks)
        monkeypatch.setattr(analyzer.recommender, "get_top_gainers_hk",
                           lambda limit: hk_stocks)
        monkeypatch.setattr(analyzer.recommender, "get_top_losers_hk",
                           lambda limit: hk_stocks)

        analyzer.show_hot_stocks(market="HK")
        captured = capsys.readouterr().out
        assert "腾讯" in captured

    def test_hk_turnover_none_handled(self, monkeypatch, capsys):
        """港股换手率为 None 时不崩溃"""
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        hk_stocks = [
            {"代码": "00700", "名称": "腾讯", "最新价": 380.0, "涨跌幅": 2.0, "换手率": None},
        ]
        monkeypatch.setattr(analyzer.recommender, "get_hot_stocks_hk",
                           lambda limit: hk_stocks)
        monkeypatch.setattr(analyzer.recommender, "get_top_gainers_hk",
                           lambda limit: [])
        monkeypatch.setattr(analyzer.recommender, "get_top_losers_hk",
                           lambda limit: [])

        analyzer.show_hot_stocks(market="HK")
        captured = capsys.readouterr().out
        assert "腾讯" in captured

    def test_us_market(self, monkeypatch, capsys):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        us_stocks = self._make_stock_us()
        monkeypatch.setattr(analyzer.recommender, "get_hot_stocks_us",
                           lambda limit: us_stocks)
        monkeypatch.setattr(analyzer.recommender, "get_top_gainers_us",
                           lambda limit: us_stocks)
        monkeypatch.setattr(analyzer.recommender, "get_top_losers_us",
                           lambda limit: [])

        analyzer.show_hot_stocks(market="US")
        captured = capsys.readouterr().out
        assert "Apple" in captured
        assert "50.00M" in captured  # volume formatted

    def test_unknown_market_falls_to_us(self, monkeypatch, capsys):
        """未知市场代码走 US 分支"""
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        monkeypatch.setattr(analyzer.recommender, "get_hot_stocks_us",
                           lambda limit: self._make_stock_us())
        monkeypatch.setattr(analyzer.recommender, "get_top_gainers_us",
                           lambda limit: [])
        monkeypatch.setattr(analyzer.recommender, "get_top_losers_us",
                           lambda limit: [])

        analyzer.show_hot_stocks(market="XXX")
        captured = capsys.readouterr().out
        assert "Apple" in captured


# ============================================================
# TestInteractiveMenu
# ============================================================

class TestInteractiveMenu:

    def test_choice_0_exits(self, monkeypatch, capsys):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        monkeypatch.setattr("builtins.input", lambda _="": "0")
        analyzer.interactive_menu()
        captured = capsys.readouterr().out
        assert "再见" in captured

    def test_choice_1_analyze_stock(self, monkeypatch):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["1", "000001", "", "", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))

        called = {}
        def capture(self, symbol, market="CN", period="1y", show_chart=True):
            called["symbol"] = symbol
            called["market"] = market
        monkeypatch.setattr(StockAnalyzer, "analyze_stock", capture)

        analyzer.interactive_menu()
        assert called["symbol"] == "000001"
        assert called["market"] == "CN"  # default when empty

    def test_choice_2_hot_stocks(self, monkeypatch):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["2", "", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))

        called = {}
        monkeypatch.setattr(analyzer, "show_hot_stocks", lambda market: called.update({"market": market}))
        analyzer.interactive_menu()
        assert called["market"] == "CN"

    def test_choice_3_recommended(self, monkeypatch):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["3", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))

        called = {}
        monkeypatch.setattr(analyzer, "show_recommended_stocks", lambda num_stocks: called.update({"called": True}))
        analyzer.interactive_menu()
        assert called.get("called") is True

    def test_choice_4_compare(self, monkeypatch):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["4", "000001,000002", "", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))

        symbols_called = []
        monkeypatch.setattr(analyzer, "analyze_stock",
                           lambda symbol, market="CN", period="1y", show_chart=True: symbols_called.append(symbol))
        analyzer.interactive_menu()
        assert symbols_called == ["000001", "000002"]

    def test_invalid_choice_then_exit(self, monkeypatch, capsys):
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["9", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))
        analyzer.interactive_menu()
        captured = capsys.readouterr().out
        assert "无效选择" in captured


# ============================================================
# TestQuickDemo
# ============================================================

class TestQuickDemo:

    def test_demo_calls_analyze_stock(self, monkeypatch):
        from main import quick_demo, StockAnalyzer

        called = {}
        monkeypatch.setattr(StockAnalyzer, "analyze_stock",
                           lambda self, symbol, market="CN", period="1y", show_chart=True: called.update({
                               "symbol": symbol, "market": market, "period": period,
                           }))
        quick_demo()
        assert called["symbol"] == "000001"
        assert called["market"] == "CN"
        assert called["period"] == "6mo"


# ============================================================
# TestShowWatchlistSignals
# ============================================================

class TestShowWatchlistSignals:

    def test_empty_watchlist(self, monkeypatch, capsys):
        """空自选股 → 提示信息"""
        monkeypatch.setattr("watchlist.get_watchlist", lambda: [])
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        analyzer.show_watchlist_signals()
        captured = capsys.readouterr().out
        assert "为空" in captured

    def test_with_watchlist(self, monkeypatch, capsys):
        """有自选股 → 打印信号和入场提示"""
        import pandas as pd
        from data_fetcher import StockDataFetcher

        monkeypatch.setattr("watchlist.get_watchlist", lambda: [
            {'symbol': '000001', 'name': '平安银行', 'market': 'CN'}
        ])

        dates = pd.date_range('2025-06-01', periods=30, freq='B')
        n = 30
        mock_df = pd.DataFrame({
            'open': [10]*n, 'high': [10.5]*n, 'low': [9.5]*n, 'close': [10]*n,
            'volume': [1000000]*n,
        }, index=dates)
        monkeypatch.setattr(StockDataFetcher, 'get_stock_data',
                           lambda self, symbol, period, market: mock_df)

        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        analyzer.show_watchlist_signals()
        captured = capsys.readouterr().out
        assert '000001' in captured
        assert '平安银行' in captured

    def test_interactive_choice_5(self, monkeypatch, capsys):
        """交互菜单中选择5 → 自选股信号"""
        monkeypatch.setattr("watchlist.get_watchlist", lambda: [])
        from main import StockAnalyzer
        analyzer = StockAnalyzer()
        inputs = ["5", "0"]
        input_iter = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda _="": next(input_iter))
        analyzer.interactive_menu()
        captured = capsys.readouterr().out
        assert "为空" in captured
