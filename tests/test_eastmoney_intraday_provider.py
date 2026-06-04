import pandas as pd

from data.providers.eastmoney_intraday_provider import EastmoneyIntradayProvider


class _Ak:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def stock_zh_a_hist_min_em(self, symbol, period, adjust):
        self.calls.append((symbol, period, adjust))
        return self.frame.copy()


def test_eastmoney_intraday_provider_renames_cn_columns():
    frame = pd.DataFrame({
        "时间": ["2026-06-04 09:31:00"],
        "开盘": [10.0],
        "收盘": [10.1],
        "最高": [10.2],
        "最低": [9.9],
        "成交量": [1000],
        "成交额": [101000],
        "均价": [10.1],
    })
    ak = _Ak(frame)
    provider = EastmoneyIntradayProvider(ak)

    result = provider.fetch_raw("601012")

    assert ak.calls == [("601012", "1", "")]
    assert list(result.columns) == ["time", "open", "close", "high", "low", "volume", "amount", "avg_price"]
    assert result.iloc[0]["close"] == 10.1


def test_eastmoney_intraday_provider_supports_positional_columns():
    frame = pd.DataFrame([["2026-06-04 09:31:00", 10.0, 10.1, 10.2, 9.9, 1000, 101000]])
    provider = EastmoneyIntradayProvider(_Ak(frame))

    result = provider.fetch_raw("601012")

    assert list(result.columns)[:7] == ["time", "open", "close", "high", "low", "volume", "amount"]
