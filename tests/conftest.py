"""
测试夹具和共享工具
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


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
