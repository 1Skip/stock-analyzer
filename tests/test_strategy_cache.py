import pandas as pd

from recommendation_modules import strategy_cache


class _Owner:
    def __init__(self):
        self.loaded = None
        self.saved = []
        self.stocks = [{"code": "000001"}, {"code": "000002"}]

    def _drop_weekend_bars(self, data):
        return data

    def _get_strategy_popular_cn_stocks(self):
        return self.stocks

    def _strategy_cache_trade_date(self):
        return "2026-06-04"

    def _load_strategy_kline_cache(self, cache_key):
        return self.loaded

    def _save_strategy_kline_cache(self, cache_key, data):
        self.saved.append((cache_key, data))


def _df(rows=20):
    return pd.DataFrame(
        {
            "open": range(rows),
            "high": range(rows),
            "low": range(rows),
            "close": range(rows),
            "volume": range(rows),
        },
        index=pd.date_range("2026-01-01", periods=rows, freq="B"),
    )


def test_get_strategy_stock_data_uses_owner_cache_before_api():
    owner = _Owner()
    cached = _df()
    owner.loaded = cached

    class Fetcher:
        def get_stock_data(self, *args, **kwargs):
            raise AssertionError("cache should avoid API")

    result = strategy_cache.get_strategy_stock_data(owner, "000001", fetcher=Fetcher())

    assert result is cached
    assert result.attrs["data_source"] == strategy_cache.LOCAL_CACHE_SOURCE


def test_get_strategy_stock_data_preserves_source_order():
    owner = _Owner()
    calls = []
    data = _df()

    class Fetcher:
        def _get_cn_stock_data_mootdx(self, symbol, period):
            calls.append("mootdx")
            return None

        def _get_cn_stock_data_akshare(self, symbol, period):
            calls.append("tencent")
            return data

        def _get_cn_stock_data_ths(self, symbol, period):
            calls.append("ths")
            return None

        def _get_cn_stock_data_akshare_em(self, symbol, period):
            calls.append("eastmoney")
            return None

        def _get_cn_stock_data_sina_fallback(self, symbol, period):
            calls.append("sina")
            return None

        def _load_offline_cache(self, symbol):
            calls.append("offline")
            return None

    result = strategy_cache.get_strategy_stock_data(owner, "000001", fetcher=Fetcher())

    assert result is data
    assert calls == ["mootdx", "tencent"]
    assert result.attrs["data_source"] == strategy_cache.TENCENT_SOURCE
    assert owner.saved[0][0] == "CN:000001:3mo:1d:2026-06-04"


def test_refresh_strategy_kline_cache_counts_success_and_failure(monkeypatch):
    owner = _Owner()
    data = _df()

    class Fetcher:
        def _get_cn_stock_data_mootdx(self, symbol, period):
            return data if symbol == "000001" else None

        def _get_cn_stock_data_akshare(self, symbol, period):
            return None

        def _get_cn_stock_data_ths(self, symbol, period):
            return None

        def _get_cn_stock_data_akshare_em(self, symbol, period):
            return None

        def _get_cn_stock_data_sina_fallback(self, symbol, period):
            return None

    monkeypatch.setattr(strategy_cache, "StockDataFetcher", Fetcher)

    result = strategy_cache.refresh_strategy_kline_cache(owner, max_workers=1)

    assert result == {"total": 2, "refreshed": 1, "failed": 1}
    assert owner.saved[0][0] == "CN:000001:3mo:1d:2026-06-04"
