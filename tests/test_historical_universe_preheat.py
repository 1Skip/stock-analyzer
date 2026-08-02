import json

import pandas as pd

from tools.preheat_historical_universe_kline import (
    _has_research_capital_fields,
    _save_research_kline,
    expected_symbols,
)


def test_expected_symbols_requires_enough_listing_history_and_active_window():
    membership = {
        "600001": [{"listed_date": "2000-01-01", "delisted_date": None}],
        "600002": [{"listed_date": "2026-07-01", "delisted_date": None}],
        "600003": [{"listed_date": "2000-01-01", "delisted_date": "2025-10-01"}],
        "600004": [{"listed_date": "2000-01-01", "delisted_date": "2026-01-01"}],
    }

    result = expected_symbols(
        membership,
        study_start="2025-11-01",
        study_end="2026-07-24",
        minimum_history_calendar_days=120,
    )

    assert result == {"600001", "600004"}


def test_baostock_fallback_saves_existing_split_cache_format(tmp_path):
    frame = pd.DataFrame(
        {
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [1000, 1200],
            "amount": [10100, 12240],
            "turnover": [0.01, 0.012],
        },
        index=pd.to_datetime(["2026-07-20", "2026-07-21"]),
    )

    path = _save_research_kline(
        tmp_path,
        symbol="600001",
        period="5y",
        frame=frame,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == "CN_600001_5y_1d_2026-07-21.json"
    assert payload["columns"][:4] == ["open", "high", "low", "close"]
    assert "turnover" in payload["columns"]
    assert len(payload["data"]) == 2


def test_research_capital_fields_require_real_amount_and_turnover_evidence():
    complete = pd.DataFrame(
        {
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.1],
            "volume": [1000],
            "amount": [10100],
            "outstanding_share": [1_000_000],
        }
    )
    missing_amount = complete.drop(columns=["amount"])
    missing_turnover_evidence = complete.drop(columns=["outstanding_share"])

    assert _has_research_capital_fields(complete) is True
    assert _has_research_capital_fields(missing_amount) is False
    assert _has_research_capital_fields(missing_turnover_evidence) is False
