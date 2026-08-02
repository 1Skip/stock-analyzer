from concurrent.futures import ThreadPoolExecutor
import os
import time

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


def test_long_period_cache_requires_real_date_coverage():
    partial = _df(rows=140)
    complete = _df(rows=1300)

    assert strategy_cache._has_requested_period_coverage(partial, "5y") is False
    assert strategy_cache._has_requested_period_coverage(complete, "5y") is True
    assert strategy_cache._has_requested_period_coverage(partial, "3mo") is True


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


def test_refresh_strategy_kline_cache_counts_success_and_failure(monkeypatch, tmp_path):
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
    monkeypatch.setattr(strategy_cache, "STRATEGY_KLINE_CACHE_DIR", str(tmp_path))

    result = strategy_cache.refresh_strategy_kline_cache(owner, max_workers=1)

    assert result == {"total": 2, "refreshed": 1, "failed": 1}
    assert owner.saved[0][0] == "CN:000001:3mo:1d:2026-06-04"


def test_preheat_strategy_kline_cache_fetches_longest_period_once_and_derives_others(monkeypatch, tmp_path):
    owner = _Owner()
    stored = {}
    calls = []
    data = _df(rows=260)

    owner._load_strategy_kline_cache = lambda cache_key: stored.get(cache_key)

    def save(cache_key, frame):
        stored[cache_key] = frame
        owner.saved.append((cache_key, frame))

    owner._save_strategy_kline_cache = save

    class Fetcher:
        def _get_cn_stock_data_mootdx(self, symbol, period):
            calls.append((symbol, period))
            return data

        def _get_cn_stock_data_akshare(self, symbol, period):
            raise AssertionError("首选真实数据源成功后不应继续回退")

        def _get_cn_stock_data_ths(self, symbol, period):
            raise AssertionError("首选真实数据源成功后不应继续回退")

        def _get_cn_stock_data_akshare_em(self, symbol, period):
            raise AssertionError("首选真实数据源成功后不应继续回退")

        def _get_cn_stock_data_sina_fallback(self, symbol, period):
            raise AssertionError("首选真实数据源成功后不应继续回退")

    monkeypatch.setattr(strategy_cache, "StockDataFetcher", Fetcher)
    monkeypatch.setattr(strategy_cache, "STRATEGY_KLINE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(strategy_cache, "strategy_kline_cache_is_fresh", lambda cache_key: cache_key in stored)

    first = strategy_cache.preheat_strategy_kline_cache(owner, max_workers=2)
    second = strategy_cache.preheat_strategy_kline_cache(owner, max_workers=2)

    assert first == {
        "total": 2,
        "refreshed": 2,
        "cached": 0,
        "failed": 0,
        "periods": ["1y", "6mo", "3mo"],
    }
    assert second == {
        "total": 2,
        "refreshed": 0,
        "cached": 2,
        "failed": 0,
        "periods": ["1y", "6mo", "3mo"],
    }
    assert sorted(calls) == [("000001", "1y"), ("000002", "1y")]
    assert len(stored) == 6
    assert len(stored["CN:000001:3mo:1d:2026-06-04"]) < len(stored["CN:000001:1y:1d:2026-06-04"])


def test_preheat_memory_cache_parses_primary_file_once_and_reuses_derived_period(monkeypatch, tmp_path):
    class DiskOwner(_Owner):
        def __init__(self):
            super().__init__()
            self.stocks = [{"code": "000001"}]

        def _load_strategy_kline_cache(self, cache_key):
            return strategy_cache.load_strategy_kline_cache(self, cache_key)

        def _save_strategy_kline_cache(self, cache_key, data):
            strategy_cache.save_strategy_kline_cache(cache_key, data)

    owner = DiskOwner()
    primary = _df(rows=260)
    monkeypatch.setattr(strategy_cache, "STRATEGY_KLINE_CACHE_DIR", str(tmp_path))
    for period in ("1y", "6mo", "3mo"):
        frame = primary if period == "1y" else strategy_cache.slice_period(primary, period)
        strategy_cache.save_strategy_kline_cache(
            f"CN:000001:{period}:1d:2026-06-04",
            frame,
        )

    original_read_json = strategy_cache.pd.read_json
    reads = []

    def tracked_read_json(*args, **kwargs):
        reads.append(args[0])
        return original_read_json(*args, **kwargs)

    class Fetcher:
        def get_stock_data(self, *args, **kwargs):
            raise AssertionError("内存预热完成后不应访问实时接口")

    monkeypatch.setattr(strategy_cache.pd, "read_json", tracked_read_json)

    with strategy_cache.strategy_kline_memory_cache():
        result = strategy_cache.preheat_strategy_kline_cache(owner, max_workers=1)
        first = strategy_cache.get_strategy_stock_data(
            owner,
            "000001",
            period="3mo",
            fetcher=Fetcher(),
        )
        second = strategy_cache.get_strategy_stock_data(
            owner,
            "000001",
            period="3mo",
            fetcher=Fetcher(),
        )

    assert result["cached"] == 1
    assert len(reads) == 1
    assert first.equals(second)
    assert len(first) < len(primary)


def test_strategy_kline_cache_concurrent_writes_remain_loadable(tmp_path, monkeypatch):
    owner = _Owner()
    monkeypatch.setattr(strategy_cache, "STRATEGY_KLINE_CACHE_DIR", str(tmp_path))
    cache_key = "CN:000001:3mo:1d:2026-06-04"
    frames = [_df(rows=20 + index) for index in range(4)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda frame: strategy_cache.save_strategy_kline_cache(cache_key, frame), frames))

    loaded = strategy_cache.load_strategy_kline_cache(owner, cache_key)

    assert loaded is not None
    assert len(loaded) in {20, 21, 22, 23}
    assert loaded.attrs["data_source"] == strategy_cache.LOCAL_CACHE_SOURCE
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("*.lock"))


def test_prune_strategy_kline_cache_removes_only_expired_json(tmp_path):
    stale = tmp_path / "stale.json"
    fresh = tmp_path / "fresh.json"
    ignored = tmp_path / "notes.txt"
    for path in (stale, fresh, ignored):
        path.write_text("{}", encoding="utf-8")
    now = time.time()
    os.utime(stale, (now - 7200, now - 7200))

    result = strategy_cache.prune_strategy_kline_cache(
        tmp_path,
        max_age_seconds=3600,
        now=now,
    )

    assert result == {"removed": 1, "bytes_removed": 2, "errors": 0}
    assert not stale.exists()
    assert fresh.exists()
    assert ignored.exists()
