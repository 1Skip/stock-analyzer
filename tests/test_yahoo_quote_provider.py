import pandas as pd

from data.providers.yahoo_quote_provider import YahooQuoteProvider


def _hist():
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.0, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )


class _Ticker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.info = {"shortName": f"name-{symbol}"}

    def history(self, period="5d"):
        return _hist()


class _YF:
    Ticker = _Ticker


def test_symbol_for_market_adds_suffixes():
    assert YahooQuoteProvider.symbol_for_market("00700", "HK") == "00700.HK"
    assert YahooQuoteProvider.symbol_for_market("600519", "CN") == "600519.SS"
    assert YahooQuoteProvider.symbol_for_market("300750", "CN") == "300750.SZ"
    assert YahooQuoteProvider.symbol_for_market("AAPL", "US") == "AAPL"


def test_fetch_quote_preserves_legacy_fields():
    quote = YahooQuoteProvider(_YF).fetch_quote("AAPL", "US")

    assert quote["symbol"] == "AAPL"
    assert quote["name"] == "name-AAPL"
    assert quote["price"] == 11.0
    assert quote["prev_close"] == 10.0
    assert abs(quote["change"] - 10.0) < 0.01


def test_fetch_index_quote_uses_index_symbol_mapping():
    quote = YahooQuoteProvider(_YF).fetch_index_quote("000001")

    assert quote["symbol"] == "000001"
    assert quote["name"] == "name-^SSEC"
    assert abs(quote["change_pct"] - 10.0) < 0.01
