import pandas as pd

from data.providers.yahoo_kline_provider import YahooKlineProvider


def _df():
    return pd.DataFrame(
        {
            "Open": range(12),
            "High": range(12),
            "Low": range(12),
            "Close": range(12),
            "Volume": range(12),
        },
        index=pd.date_range("2026-01-01", periods=12, freq="B"),
    )


class _Ticker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period="1y", interval="1d"):
        return _df()


class _YF:
    Ticker = _Ticker


def test_fetch_hk_normalizes_columns_and_attrs():
    result = YahooKlineProvider(_YF).fetch("00700", "1y", market="HK")

    assert result is not None
    assert "close" in result.columns
    assert result.attrs["volume_unit"] == "share"


def test_cn_symbol_uses_exchange_suffix():
    assert YahooKlineProvider.cn_symbol("600519") == "600519.SS"
    assert YahooKlineProvider.cn_symbol("300750") == "300750.SZ"
