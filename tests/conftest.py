"""
测试夹具和共享工具
"""
import sys
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============================================================
# Streamlit Mock — 在收集阶段设置，供所有测试使用
# ============================================================

class _MockSessionState(dict):
    def get(self, key, default=None):
        return super().get(key, default)
    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError(key)
    def __setattr__(self, key, value):
        self[key] = value


if 'streamlit' not in sys.modules:
    _mock_st = type(sys)('streamlit')
    _mock_st.__path__ = []  # 标记为 package
    _mock_st.session_state = _MockSessionState()
    _mock_st.cache_data = lambda f=None, **kw: (lambda g: g) if f is None else f
    _mock_st.set_page_config = lambda **kw: None
    _mock_st.markdown = lambda *args, **kw: None
    _mock_st.sidebar = type(sys)('sidebar')
    _mock_st.columns = lambda n, **kw: [type(sys)('col') for _ in range(n)]
    _mock_st.button = lambda label, **kw: False
    _mock_st.selectbox = lambda label, options, **kw: options[0] if options else None
    _mock_st.text_input = lambda label, **kw: ''
    _mock_st.info = lambda *args, **kw: None
    _mock_st.warning = lambda *args, **kw: None
    _mock_st.error = lambda *args, **kw: None
    _mock_st.success = lambda *args, **kw: None
    _mock_st.empty = lambda: type(sys)('empty')
    _mock_st.spinner = lambda text: type(sys)('spinner')
    _mock_st.form = lambda key: type(sys)('form')
    _mock_st.form_submit_button = lambda label, **kw: False
    _mock_st.tabs = lambda labels: [type(sys)('tab') for _ in labels]
    _mock_st.get_option = lambda key: "light"  # 默认亮色主题
    _mock_st.plotly_chart = lambda fig, **kw: None

    # streamlit.components 子模块
    _mock_components = type(sys)('streamlit.components')
    _mock_components.__path__ = []

    # streamlit.components.v1 子模块 (被 streamlit_lightweight_charts 导入)
    _mock_v1 = type(sys)('streamlit.components.v1')
    _mock_v1.__path__ = []
    _mock_v1.html = lambda html, height=None, width=None, scrolling=False: None
    _mock_v1.iframe = lambda src, height=None, width=None, scrolling=False: None
    _mock_v1.declare_component = lambda name, path=None, url=None: (lambda **kw: None)

    _mock_components.v1 = _mock_v1
    _mock_st.components = _mock_components

    sys.modules['streamlit'] = _mock_st
    sys.modules['streamlit.components'] = _mock_components
    sys.modules['streamlit.components.v1'] = _mock_v1


def _make_data(prices, start_date=None):
    """从收盘价序列构建OHLCV DataFrame"""
    if start_date is None:
        start_date = datetime(2025, 1, 6)
    dates = [start_date + timedelta(days=i) for i in range(len(prices))]
    data = []
    for i, close in enumerate(prices):
        open_p = close * (1 + np.random.uniform(-0.01, 0.01))
        high = max(open_p, close) * (1 + abs(np.random.uniform(0, 0.02)))
        low = min(open_p, close) * (1 - abs(np.random.uniform(0, 0.02)))
        data.append({
            'open': round(open_p, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': np.random.randint(1000000, 10000000),
        })
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df


@pytest.fixture
def uptrend_data():
    """上涨趋势数据：30天持续上涨，高低开收一致确保信号明确"""
    prices = [10.0 + i * 0.2 for i in range(30)]
    df = _make_data(prices)
    # 确保每天收阳线（收盘>开盘）以产生明确信号
    for i in range(len(df)):
        df.iloc[i, df.columns.get_loc('open')] = prices[i] - 0.05
        df.iloc[i, df.columns.get_loc('close')] = prices[i]
        df.iloc[i, df.columns.get_loc('high')] = prices[i] + 0.1
        df.iloc[i, df.columns.get_loc('low')] = prices[i] - 0.15
    return df


@pytest.fixture
def downtrend_data():
    """下跌趋势数据：30天持续下跌，高低开收一致确保信号明确"""
    prices = [20.0 - i * 0.15 for i in range(30)]
    df = _make_data(prices)
    # 确保每天收阴线（收盘<开盘）以产生明确信号
    for i in range(len(df)):
        df.iloc[i, df.columns.get_loc('open')] = prices[i] + 0.05
        df.iloc[i, df.columns.get_loc('close')] = prices[i]
        df.iloc[i, df.columns.get_loc('high')] = prices[i] + 0.15
        df.iloc[i, df.columns.get_loc('low')] = prices[i] - 0.1
    return df


@pytest.fixture
def sideways_data():
    """横盘数据：30天窄幅震荡"""
    np.random.seed(42)
    prices = [10.0 + np.random.uniform(-0.05, 0.05) for _ in range(30)]
    return _make_data(prices)


@pytest.fixture
def flat_price_data():
    """一字横盘数据：价格完全不变（停牌/一字板）"""
    prices = [10.0] * 30
    df = _make_data(prices)
    df['open'] = 10.0
    df['high'] = 10.0
    df['low'] = 10.0
    df['close'] = 10.0
    return df


@pytest.fixture
def short_data():
    """数据不足（少于10天）"""
    prices = [10.0 + i * 0.1 for i in range(5)]
    return _make_data(prices)


@pytest.fixture
def known_macd_data():
    """已知MACD验证数据：简单线性序列用于手工验证"""
    prices = list(range(10, 40)) + list(range(40, 50)) + list(range(50, 30, -1))
    return _make_data(prices)


@pytest.fixture
def nan_data():
    """包含NaN的数据"""
    df = uptrend_data()
    df.iloc[10:12] = np.nan
    return df
