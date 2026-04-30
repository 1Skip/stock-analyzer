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
