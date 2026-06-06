from datetime import datetime

import pandas as pd

from decision_committee import build_a_share_decision


def _sample_decision_inputs():
    data = pd.DataFrame([{
        "close": 42.86,
        "boll_upper": 45.79,
        "boll_mid": 42.25,
        "boll_lower": 38.71,
        "ma20": 42.25,
        "ma60": 40.50,
    }])
    signals = {
        "recommendation": "bullish signal",
        "macd": "golden cross",
        "rsi": "neutral",
        "kdj": "golden cross",
        "boll": "above middle band",
    }
    quote = {"price": 42.86, "change": 3.55, "volume": 56_134_000}
    extended_info = {
        "fund_flow": {
            "main_net_inflow": 12_000_000,
            "main_net_inflow_ratio": 1.6,
            "five_day_main_net_inflow": 23_000_000,
        },
        "financial": {"metrics": {
            "revenue": 100_000_000,
            "net_profit": 20_000_000,
            "operating_cash_flow": 15_000_000,
            "eps": 0.6,
        }},
        "research": {"reports": [{"title": "sample report"}]},
        "sector_attribution": {
            "industry": {"name": "electronics", "change_pct": 1.2},
            "concepts": [{"name": "chips", "change_pct": 2.1}],
        },
        "risk_events": {"announcements": []},
    }
    profile = {"pe_ttm": 18.5, "pb": 1.8, "turnover_rate": 3.5, "market_cap": 20_000_000_000}
    return data, signals, quote, extended_info, profile


def test_a_share_decision_is_stable_for_identical_inputs():
    data, signals, quote, extended_info, profile = _sample_decision_inputs()

    first = build_a_share_decision(data, signals, quote, extended_info, symbol="002541", stock_name="sample", profile=profile)
    second = build_a_share_decision(data, signals, quote, extended_info, symbol="002541", stock_name="sample", profile=profile)

    assert second["score"] == first["score"]
    assert second["confidence"] == first["confidence"]
    assert second["action"] == first["action"]
    assert second["position"] == first["position"]
    assert second["key_levels"] == first["key_levels"]
    assert second["agents"] == first["agents"]


def test_cn_daily_kline_cache_version_is_stable_for_same_day_after_close(monkeypatch):
    import ui.cached_data as cached_data

    class FakeDateTime:
        current = None

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(cached_data, "datetime", FakeDateTime)

    versions = []
    for current in (
        datetime(2026, 5, 21, 15, 31),
        datetime(2026, 5, 21, 17, 11),
        datetime(2026, 5, 21, 21, 54),
        datetime(2026, 5, 21, 22, 1),
        datetime(2026, 5, 21, 23, 59),
    ):
        FakeDateTime.current = current
        versions.append(cached_data.stock_data_cache_version("CN"))

    assert len(set(versions)) == 1
    assert versions[0].endswith("20260521-closed")


def test_cn_daily_kline_cache_version_refreshes_by_minute_during_trading(monkeypatch):
    import ui.cached_data as cached_data

    class FakeDateTime:
        current = None

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(cached_data, "datetime", FakeDateTime)

    FakeDateTime.current = datetime(2026, 5, 21, 14, 11)
    first = cached_data.stock_data_cache_version("CN")
    FakeDateTime.current = datetime(2026, 5, 21, 14, 12)
    second = cached_data.stock_data_cache_version("CN")

    assert first != second
    assert first.endswith("202605211411")
    assert second.endswith("202605211412")
