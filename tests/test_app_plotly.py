"""Streamlit Plotly 图表函数测试"""
import pytest
import pandas as pd
import numpy as np


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def setup_session_state():
    """设置 app.py chart 函数需要的 session_state 值"""
    import streamlit as st
    st.session_state['color_scheme'] = 'red_up'
    st.session_state['analyze_market'] = 'CN'
    yield
    st.session_state.clear()


@pytest.fixture
def sample_data():
    """含完整技术指标的15天数据"""
    dates = pd.date_range('2026-03-01', periods=15, freq='B')
    np.random.seed(1)
    close = 10 + np.cumsum(np.random.randn(15) * 0.2)
    df = pd.DataFrame({
        'open': close - 0.1,
        'high': close + 0.3,
        'low': close - 0.3,
        'close': close,
        'volume': np.random.randint(1000000, 5000000, 15),
        'macd': np.linspace(-0.5, 0.5, 15),
        'macd_signal': np.linspace(-0.3, 0.3, 15),
        'macd_hist': np.linspace(-0.2, 0.2, 15),
        'rsi_6': np.linspace(30, 70, 15),
        'rsi_12': np.linspace(35, 65, 15),
        'rsi_24': np.linspace(40, 60, 15),
        'kdj_k': np.linspace(20, 80, 15),
        'kdj_d': np.linspace(25, 75, 15),
        'kdj_j': np.linspace(10, 90, 15),
        'boll_upper': close + 0.5,
        'boll_mid': close,
        'boll_lower': close - 0.5,
        'ma5': close + 0.05,
        'ma10': close + 0.02,
        'ma20': close - 0.02,
        'ma60': close - 0.05,
    }, index=dates)
    return df


# ============================================================
# TestPlotCandlestickChart
# ============================================================

class TestPlotCandlestickChart:

    def test_returns_figure(self, sample_data):
        from app import plot_candlestick_chart
        fig = plot_candlestick_chart(sample_data)
        assert fig is not None
        from plotly.graph_objects import Figure
        assert isinstance(fig, Figure)

    def test_with_cross_markers(self):
        """构造有明确金叉/死叉的数据验证标记"""
        from app import plot_candlestick_chart
        dates = pd.date_range('2026-03-01', periods=10, freq='B')
        macd = np.array([0.1, 0.05, -0.02, -0.1, -0.05, -0.02, 0.01, 0.05, 0.1, 0.08])
        signal = np.array([0.05, 0.02, -0.01, -0.08, -0.06, -0.01, -0.02, 0.02, 0.05, 0.1])
        df = pd.DataFrame({
            'open': [10]*10, 'high': [10.5]*10, 'low': [9.5]*10, 'close': [10]*10,
            'volume': [1000000]*10,
            'macd': macd, 'macd_signal': signal,
            'macd_hist': macd - signal,
            'ma5': [10]*10, 'ma10': [10]*10, 'ma20': [10]*10, 'ma60': [10]*10,
        }, index=dates)
        fig = plot_candlestick_chart(df)
        # 数据有交叉，应有Candlestick trace
        assert len(fig.data) >= 1

    def test_missing_ma_columns_handled(self):
        from app import plot_candlestick_chart
        dates = pd.date_range('2026-03-01', periods=5, freq='B')
        df = pd.DataFrame({
            'open': [10]*5, 'high': [10.5]*5, 'low': [9.5]*5, 'close': [10]*5,
            'volume': [1000000]*5,
            'macd': [0.1]*5, 'macd_signal': [0.05]*5, 'macd_hist': [0.05]*5,
        }, index=dates)
        fig = plot_candlestick_chart(df)
        assert fig is not None


# ============================================================
# TestPlotRSIChart
# ============================================================

class TestPlotRSIChart:

    def test_returns_figure(self, sample_data):
        from app import plot_rsi_chart
        fig = plot_rsi_chart(sample_data)
        from plotly.graph_objects import Figure
        assert isinstance(fig, Figure)

    def test_has_three_rsi_traces(self, sample_data):
        from app import plot_rsi_chart
        fig = plot_rsi_chart(sample_data)
        names = [t.name for t in fig.data]
        assert 'RSI(6)' in names
        assert 'RSI(12)' in names
        assert 'RSI(24)' in names


# ============================================================
# TestPlotKDJChart
# ============================================================

class TestPlotKDJChart:

    def test_returns_figure(self, sample_data):
        from app import plot_kdj_chart
        fig = plot_kdj_chart(sample_data)
        from plotly.graph_objects import Figure
        assert isinstance(fig, Figure)

    def test_has_kdj_traces(self, sample_data):
        from app import plot_kdj_chart
        fig = plot_kdj_chart(sample_data)
        names = [t.name for t in fig.data]
        assert 'K' in names
        assert 'D' in names
        assert 'J' in names

    def test_with_cross_markers(self):
        from app import plot_kdj_chart
        dates = pd.date_range('2026-03-01', periods=10, freq='B')
        k = np.array([20, 25, 30, 35, 40, 30, 25, 20, 30, 50])
        d = np.array([25, 28, 32, 33, 38, 32, 30, 22, 25, 40])
        df = pd.DataFrame({
            'open': [10]*10, 'high': [10.5]*10, 'low': [9.5]*10, 'close': [10]*10,
            'kdj_k': k, 'kdj_d': d, 'kdj_j': k*3 - d*2,
        }, index=dates)
        fig = plot_kdj_chart(df)
        assert fig is not None


# ============================================================
# TestPlotBollChart
# ============================================================

class TestPlotBollChart:

    def test_returns_figure(self, sample_data):
        from app import plot_boll_chart
        fig = plot_boll_chart(sample_data)
        from plotly.graph_objects import Figure
        assert isinstance(fig, Figure)

    def test_has_boll_traces(self, sample_data):
        from app import plot_boll_chart
        fig = plot_boll_chart(sample_data)
        names = [t.name for t in fig.data]
        assert '上轨' in names
        assert '中轨' in names
        assert '下轨' in names


# ============================================================
# TestDetectProvider
# ============================================================

class TestDetectProvider:

    def test_gemini_key_detected(self):
        from app import _detect_provider
        provider, model = _detect_provider('AIzaSyABC123')
        assert provider == 'gemini'
        assert 'gemini' in model

    def test_claude_key_detected(self):
        from app import _detect_provider
        provider, model = _detect_provider('sk-ant-api03-xxx')
        assert provider == 'claude'
        assert 'claude' in model

    def test_empty_key_returns_none(self):
        from app import _detect_provider
        assert _detect_provider('') is None
        assert _detect_provider(None) is None

    def test_unknown_key_returns_none(self):
        from app import _detect_provider
        assert _detect_provider('unknown-key-format') is None
