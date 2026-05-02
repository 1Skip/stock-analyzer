"""图表绘制模块测试（matplotlib, non-interactive）"""
import pytest
import matplotlib
matplotlib.use('Agg')  # 必须在 import pyplot 之前设置

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def close_figures():
    """每个测试后关闭所有 matplotlib figures"""
    yield
    plt.close('all')


@pytest.fixture
def sample_ohlcv_data():
    """30天OHLCV数据（含所有技术指标）
    使用整数索引，因为 _draw_candlestick_bars 内部用 idx - 0.3 做 x 坐标偏移
    """
    np.random.seed(0)
    close = 10 + np.cumsum(np.random.randn(30) * 0.3)
    df = pd.DataFrame({
        'open': close - 0.1,
        'high': close + 0.3,
        'low': close - 0.3,
        'close': close,
        'volume': np.random.randint(1000000, 5000000, 30),
        'macd': np.random.randn(30) * 0.3,
        'macd_signal': np.random.randn(30) * 0.2,
        'macd_hist': np.random.randn(30) * 0.1,
        'rsi': np.random.uniform(30, 70, 30),
        'kdj_k': np.random.uniform(20, 80, 30),
        'kdj_d': np.random.uniform(20, 80, 30),
        'kdj_j': np.random.uniform(20, 80, 30),
        'boll_upper': close + 0.5,
        'boll_mid': close,
        'boll_lower': close - 0.5,
        'ma5': close + 0.05,
        'ma10': close + 0.02,
        'ma20': close - 0.02,
        'ma60': close - 0.05,
    }, index=range(30))
    return df


@pytest.fixture
def no_show(monkeypatch):
    """禁用 plt.show()"""
    monkeypatch.setattr(plt, 'show', lambda: None)
    monkeypatch.setattr('chart_plotter.plt.show', lambda: None)


# ============================================================
# TestDrawCandlestickBars
# ============================================================

class TestDrawCandlestickBars:

    def test_creates_patches(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        fig, ax = plt.subplots()
        ChartPlotter._draw_candlestick_bars(ax, sample_ohlcv_data, 'red', 'green')
        assert len(ax.patches) == len(sample_ohlcv_data)

    def test_empty_data_does_nothing(self, no_show):
        from chart_plotter import ChartPlotter
        fig, ax = plt.subplots()
        df = pd.DataFrame()
        ChartPlotter._draw_candlestick_bars(ax, df, 'red', 'green')
        assert len(ax.patches) == 0

    def test_single_row(self, no_show):
        from chart_plotter import ChartPlotter
        df = pd.DataFrame({
            'open': [10.0], 'high': [10.5], 'low': [9.5], 'close': [10.2],
        }, index=[0])
        fig, ax = plt.subplots()
        ChartPlotter._draw_candlestick_bars(ax, df, 'red', 'green')
        assert len(ax.patches) == 1


# ============================================================
# TestPlotCandlestick
# ============================================================

class TestPlotCandlestick:

    def test_with_volume_creates_two_axes(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(sample_ohlcv_data, show_volume=True)
        fig = plt.gcf()
        assert len(fig.axes) == 2

    def test_without_volume_creates_one_axis(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        df_no_vol = sample_ohlcv_data.drop(columns=['volume'])
        ChartPlotter.plot_candlestick(df_no_vol, show_volume=True)
        fig = plt.gcf()
        assert len(fig.axes) == 1

    def test_none_data_does_not_crash(self, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(None)  # 不应抛异常

    def test_empty_data_does_not_crash(self, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(pd.DataFrame())  # 不应抛异常

    def test_save_to_file(self, sample_ohlcv_data, no_show, tmp_path):
        from chart_plotter import ChartPlotter
        path = tmp_path / 'candlestick.png'
        ChartPlotter.plot_candlestick(sample_ohlcv_data, save_path=str(path))
        assert path.exists()
        assert path.stat().st_size > 0


# ============================================================
# TestPlotWithIndicators
# ============================================================

class TestPlotWithIndicators:

    def test_creates_six_subplots(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_with_indicators(sample_ohlcv_data)
        fig = plt.gcf()
        assert len(fig.axes) == 6

    def test_none_data_does_not_crash(self, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_with_indicators(None)

    def test_empty_data_does_not_crash(self, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_with_indicators(pd.DataFrame())

    def test_save_to_file(self, sample_ohlcv_data, no_show, tmp_path):
        from chart_plotter import ChartPlotter
        path = tmp_path / 'indicators.png'
        ChartPlotter.plot_with_indicators(sample_ohlcv_data, save_path=str(path))
        assert path.exists()
        assert path.stat().st_size > 0

    def test_missing_indicators_still_works(self, no_show):
        from chart_plotter import ChartPlotter
        df = pd.DataFrame({
            'open': [10]*10, 'high': [10.5]*10, 'low': [9.5]*10, 'close': [10]*10,
            'volume': [1000000]*10,
        }, index=range(10))
        ChartPlotter.plot_with_indicators(df)  # 不崩溃即可
        fig = plt.gcf()
        assert len(fig.axes) == 6


# ============================================================
# TestPlotSingleIndicator
# ============================================================

class TestPlotSingleIndicator:

    def test_macd_indicator(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='macd')
        fig = plt.gcf()
        assert len(fig.axes) == 2

    def test_rsi_indicator(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='rsi')
        fig = plt.gcf()
        assert len(fig.axes) == 2

    def test_kdj_indicator(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='kdj')
        fig = plt.gcf()
        assert len(fig.axes) == 2

    def test_boll_indicator(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='boll')
        fig = plt.gcf()
        assert len(fig.axes) == 2

    def test_invalid_indicator_falls_through(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='unknown')
        fig = plt.gcf()
        assert len(fig.axes) == 2  # 仍然创建2个子图，只是不画指标

    def test_none_data_does_not_crash(self, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(None)

    def test_save_to_file(self, sample_ohlcv_data, no_show, tmp_path):
        from chart_plotter import ChartPlotter
        path = tmp_path / 'macd_single.png'
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='macd', save_path=str(path))
        assert path.exists()
        assert path.stat().st_size > 0


# ============================================================
# TestColorSchemes
# ============================================================

class TestColorSchemes:

    def test_candlestick_green_up_scheme(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(sample_ohlcv_data, color_scheme='green_up')
        # 不抛异常即通过

    def test_candlestick_colorblind_scheme(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(sample_ohlcv_data, color_scheme='colorblind')
        # 不抛异常即通过

    def test_candlestick_default_red_up(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_candlestick(sample_ohlcv_data)  # 默认 red_up
        # 不抛异常即通过

    def test_with_indicators_green_up_scheme(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_with_indicators(sample_ohlcv_data, color_scheme='green_up')
        # 不抛异常即通过

    def test_single_indicator_colorblind(self, sample_ohlcv_data, no_show):
        from chart_plotter import ChartPlotter
        ChartPlotter.plot_single_indicator(sample_ohlcv_data, indicator='macd',
                                           color_scheme='colorblind')
        # 不抛异常即通过
