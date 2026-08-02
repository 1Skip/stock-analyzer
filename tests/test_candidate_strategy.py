import json

import pandas as pd

from candidate_strategy import (
    CANDIDATE_RULES,
    CANDIDATE_RULESET_VERSION,
    candidate_rule_fingerprint,
    candidate_signal_mask,
    evaluate_candidate_at,
)
from tools.research_candidate_strategies import (
    _eligible_on_date,
    _historical_status_symbols_in_window,
    _resolve_exit,
    build_trades,
    build_execution_sensitivity,
    build_walk_forward_analysis,
    load_daily_status_history,
    select_rule_for_promotion,
    select_rule_from_training,
    summarize_trades,
)


def _candidate_frame(rule_id):
    rule = CANDIDATE_RULES[rule_id]
    row = {
        "open": 10.0,
        "high": 10.3,
        "low": 9.8,
        "close": 10.1,
        "volume": 2_000_000,
        "amount_20d": 200_000_000,
        "volume_ratio_20d": 1.6,
        "amount_ratio_20d": 1.6,
        "turnover": 0.03,
        "turnover_ratio_20d": 1.4,
        "ma5": 10.0,
        "ma10": 9.9,
        "ma20": 10.0,
        "ma60": 9.5,
        "ma120": 9.0,
        "return_1d": 0.01,
        "return_3d": (rule.min_return_3d + rule.max_return_3d) / 2,
        "return_20d": 0.04,
        "return_60d": (rule.min_return_60d + rule.max_return_60d) / 2,
        "volatility_20d": rule.max_volatility_20d / 2,
        "rsi_6": (rule.min_rsi_6 + rule.max_rsi_6) / 2,
        "rsi_2": 5.0,
        "boll_mid": 10.0,
        "boll_upper": 10.8,
        "boll_lower": 9.2,
        "distance_to_high_60d": -0.03,
        "close_to_ma20": (rule.min_close_to_ma20 + rule.max_close_to_ma20) / 2,
        "ma20_to_ma60": 0.05,
        "ma60_slope_5d": 0.01,
        "down_days_3": 3,
        "intraday_return": 0.01,
        "close_location": 0.8,
    }
    return pd.DataFrame([row] * 80, index=pd.date_range("2026-01-01", periods=80, freq="B"))


def test_candidate_rule_fingerprint_is_stable_and_versioned():
    fingerprint = candidate_rule_fingerprint("capital_flow_pullback_regime_confirmed")

    assert CANDIDATE_RULESET_VERSION == "candidate_rules_v3_20260727"
    assert len(fingerprint) == 64
    assert fingerprint == candidate_rule_fingerprint(
        "capital_flow_pullback_regime_confirmed"
    )


def test_capital_flow_rule_requires_volume_amount_and_turnover_confirmation():
    rule_id = "capital_flow_pullback_regime_confirmed"
    frame = _candidate_frame(rule_id)

    assert evaluate_candidate_at(frame, rule_id=rule_id)["passed"] is True

    frame.loc[frame.index[-1], "volume_ratio_20d"] = 1.19
    result = evaluate_candidate_at(frame, rule_id=rule_id)
    assert result["passed"] is False
    assert result["checks"]["成交量相对20日中位数增强"] is False


def test_prepare_candidate_frame_builds_point_in_time_capital_flow_features():
    index = pd.date_range("2026-01-01", periods=25, freq="B")
    raw = pd.DataFrame(
        {
            "open": [10.0] * 25,
            "high": [10.5] * 25,
            "low": [9.8] * 25,
            "close": [10.2] * 25,
            "volume": [1_000_000.0] * 24 + [1_500_000.0],
            "amount": [10_000_000.0] * 24 + [15_000_000.0],
            "turnover": [0.02] * 24 + [0.03],
        },
        index=index,
    )

    prepared = __import__("candidate_strategy").prepare_candidate_frame(raw)
    latest = prepared.iloc[-1]

    assert latest["volume_ratio_20d"] == 1.5
    assert latest["amount_ratio_20d"] == 1.5
    assert latest["turnover_ratio_20d"] == 1.5


def test_prepare_candidate_frame_does_not_invent_missing_amount():
    index = pd.date_range("2026-01-01", periods=25, freq="B")
    raw = pd.DataFrame(
        {
            "open": [10.0] * 25,
            "high": [10.5] * 25,
            "low": [9.8] * 25,
            "close": [10.2] * 25,
            "volume": [1_000_000.0] * 25,
            "turnover": [0.02] * 25,
        },
        index=index,
    )

    prepared = __import__("candidate_strategy").prepare_candidate_frame(raw)

    assert prepared["amount_20d"].isna().all()
    assert prepared["amount_ratio_20d"].isna().all()


def test_research_ranking_uses_volume_amount_and_turnover_strength(monkeypatch):
    monkeypatch.setattr(
        "tools.research_candidate_strategies.REGIME_FILTERED_RULE_IDS",
        set(),
    )
    rule_id = "capital_flow_pullback_regime_confirmed"
    stronger = _candidate_frame(rule_id)
    weaker = _candidate_frame(rule_id)
    signal_date = stronger.index[-3]
    for frame in (stronger, weaker):
        frame["volume_ratio_20d"] = 0.5
        frame["amount_ratio_20d"] = 0.5
        frame["turnover_ratio_20d"] = 0.5
        frame.loc[signal_date, [
            "volume_ratio_20d",
            "amount_ratio_20d",
            "turnover_ratio_20d",
        ]] = [1.2, 1.2, 1.1]
    stronger.loc[signal_date, [
        "volume_ratio_20d",
        "amount_ratio_20d",
        "turnover_ratio_20d",
    ]] = [1.8, 1.8, 1.8]
    stronger.attrs["symbol"] = "600001"
    weaker.attrs["symbol"] = "600002"

    trades = build_trades(
        {"600001": stronger, "600002": weaker},
        rule_id=rule_id,
        top_n=1,
        cost_pct=0.2,
        study_start=str(signal_date.date()),
    )

    assert len(trades) == 1
    assert trades[0]["symbol"] == "600001"


def test_vectorized_candidate_mask_matches_single_point_evaluator():
    for rule_id in CANDIDATE_RULES:
        frame = _candidate_frame(rule_id)
        mask = candidate_signal_mask(frame, rule_id=rule_id)
        evaluated = evaluate_candidate_at(frame, rule_id=rule_id)

        assert bool(mask.iloc[-1]) is evaluated["passed"]

        frame.loc[frame.index[-1], "close"] = 8.0
        mask = candidate_signal_mask(frame, rule_id=rule_id)
        evaluated = evaluate_candidate_at(frame, rule_id=rule_id)
        assert bool(mask.iloc[-1]) is False
        assert evaluated["passed"] is False


def test_research_exit_waits_until_limit_down_reopens():
    rows = pd.DataFrame(
        [
            {"open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0},
            {"open": 8.8, "high": 9.1, "low": 8.7, "close": 9.0},
        ],
        index=pd.to_datetime(["2026-07-02", "2026-07-03"]),
    )

    resolved = _resolve_exit(
        rows,
        horizon=1,
        stop_loss=9.5,
        take_profit=10.5,
        previous_close=10.0,
    )

    assert resolved == (8.8, "2026-07-03")


def test_research_does_not_formally_select_rule_below_win_rate_gate():
    rule_results = {
        "candidate": {
            "train": {
                "plan_dates": 26,
                "horizons": {
                    "1d": {
                        "samples": 112,
                        "win_rate_pct": 51.79,
                        "wilson_low_pct": 42.63,
                        "avg_net_return_pct": 0.086,
                        "profit_factor": 1.072,
                    }
                },
            }
        }
    }

    assert select_rule_from_training(rule_results) == ""

    stats = rule_results["candidate"]["train"]["horizons"]["1d"]
    stats["win_rate_pct"] = 56.0
    stats["wilson_low_pct"] = 51.0
    assert select_rule_from_training(rule_results) == "candidate"


def test_formal_promotion_requires_positive_out_of_sample_results():
    stats = {
        "samples": 120,
        "win_rate_pct": 58,
        "wilson_low_pct": 51,
        "avg_net_return_pct": 0.2,
        "profit_factor": 1.2,
        "max_drawdown_pct": -8,
        "avg_excess_return_pct": 0.1,
    }
    rule_results = {
        "candidate": {
            "train": {"plan_dates": 30, "horizons": {"1d": dict(stats)}},
            "test": {
                "plan_dates": 15,
                "horizons": {"1d": {**stats, "samples": 40}},
            },
        }
    }

    assert select_rule_for_promotion(rule_results) == "candidate"

    rule_results["candidate"]["test"]["horizons"]["1d"][
        "avg_net_return_pct"
    ] = -0.1
    assert select_rule_for_promotion(rule_results) == ""


def test_point_in_time_membership_excludes_prelisting_and_post_delisting_dates():
    membership = {
        "600001": [
            {"listed_date": "2026-01-01", "delisted_date": "2026-06-30"}
        ]
    }

    assert _eligible_on_date("600001", "2025-12-31", membership) is False
    assert _eligible_on_date("600001", "2026-03-01", membership) is True
    assert _eligible_on_date("600001", "2026-07-01", membership) is False
    assert _eligible_on_date("000001", "2026-03-01", membership) is False


def test_daily_status_excludes_historical_st_and_suspension_and_fails_closed():
    membership = {
        "600001": [{"listed_date": "2026-01-01", "delisted_date": None}],
        "600002": [{"listed_date": "2026-01-01", "delisted_date": None}],
    }
    daily_status = {
        "valid": True,
        "trade_dates": {"2026-07-20", "2026-07-21", "2026-07-22"},
        "symbols": {
            "600001": {
                "query_start": "2026-07-20",
                "query_end": "2026-07-22",
                "complete": True,
                "st_dates": {"2026-07-21"},
                "suspended_dates": {"2026-07-22"},
            },
            "600002": {
                "query_start": "2026-07-20",
                "query_end": "2026-07-22",
                "complete": False,
                "st_dates": set(),
                "suspended_dates": set(),
            },
        },
    }

    assert _eligible_on_date(
        "600001", "2026-07-20", membership, daily_status
    ) is True
    assert _eligible_on_date(
        "600001", "2026-07-21", membership, daily_status
    ) is False
    assert _eligible_on_date(
        "600001", "2026-07-22", membership, daily_status
    ) is False
    assert _eligible_on_date(
        "600002", "2026-07-20", membership, daily_status
    ) is False
    assert _eligible_on_date(
        "600003", "2026-07-20", membership, daily_status
    ) is False
    assert _eligible_on_date("600001", "2026-07-20", membership) is True


def test_daily_status_loader_rejects_unverified_payload_and_normalizes_dates(tmp_path):
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"real_data": False}), encoding="utf-8")
    invalid = load_daily_status_history(invalid_path)
    assert invalid["valid"] is False

    valid_path = tmp_path / "valid.json"
    valid_path.write_text(
        json.dumps(
            {
                "version": "daily_security_status_v1",
                "source": "Baostock",
                "real_data": True,
                "trade_dates": ["2026-07-20", "2026-07-21"],
                "symbols": {
                    "600001": {
                        "query_start": "2026-07-20",
                        "query_end": "2026-07-21",
                        "complete": True,
                        "st_dates": ["2026-07-21"],
                        "suspended_dates": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    valid = load_daily_status_history(valid_path)

    assert valid["valid"] is True
    assert valid["trade_dates"] == {"2026-07-20", "2026-07-21"}
    assert valid["symbols"]["600001"]["st_dates"] == {"2026-07-21"}


def test_daily_status_coverage_requires_complete_range_for_each_member():
    membership = {
        "600001": [{"listed_date": "2026-07-20", "delisted_date": None}],
        "600002": [{"listed_date": "2026-07-20", "delisted_date": None}],
    }
    daily_status = {
        "valid": True,
        "trade_dates": {"2026-07-20", "2026-07-21"},
        "symbols": {
            "600001": {
                "query_start": "2026-07-20",
                "query_end": "2026-07-21",
                "complete": True,
            },
            "600002": {
                "query_start": "2026-07-20",
                "query_end": "2026-07-20",
                "complete": True,
            },
        },
    }

    covered = _historical_status_symbols_in_window(
        set(membership),
        membership=membership,
        daily_status=daily_status,
        start_date="2026-07-20",
        end_date="2026-07-21",
    )

    assert covered == {"600001"}


def test_summary_calculates_real_benchmark_excess():
    benchmark = pd.DataFrame(
        {"close": [100, 101]},
        index=pd.to_datetime(["2026-07-02", "2026-07-03"]),
    )
    trades = [
        {
            "signal_date": "2026-07-01",
            "entry_date": "2026-07-02",
            "status": "completed",
            "returns": {"1d": 2.0, "5d": None, "20d": None},
            "exit_dates": {"1d": "2026-07-03", "5d": None, "20d": None},
        }
    ]

    stats = summarize_trades(trades, benchmark=benchmark)["horizons"]["1d"]

    assert stats["avg_benchmark_return_pct"] == 1.0
    assert stats["avg_excess_return_pct"] == 1.0


def test_walk_forward_and_execution_sensitivity_report_stability_without_promotion():
    trades = []
    for index, signal_date in enumerate(pd.date_range("2026-01-01", periods=180, freq="D")):
        trades.append({
            "symbol": f"600{index % 5:03d}",
            "score": 80 - index % 5,
            "signal_date": signal_date.date().isoformat(),
            "entry_date": (signal_date + pd.Timedelta(days=1)).date().isoformat(),
            "status": "completed",
            "returns": {"1d": 0.2, "5d": 0.3, "20d": 0.5},
            "exit_dates": {
                "1d": (signal_date + pd.Timedelta(days=2)).date().isoformat(),
                "5d": (signal_date + pd.Timedelta(days=6)).date().isoformat(),
                "20d": (signal_date + pd.Timedelta(days=21)).date().isoformat(),
            },
        })

    walk_forward = build_walk_forward_analysis(
        {"rule": trades},
        study_start="2026-01-01",
        benchmark=None,
    )
    sensitivity = build_execution_sensitivity(
        trades,
        base_top_n=5,
        base_cost_pct=0.2,
        train_end="2026-04-30",
        benchmark=None,
    )

    assert walk_forward["summary"]["folds"] >= 2
    assert walk_forward["summary"]["evaluable_folds"] >= 1
    assert sensitivity["summary"]["scenarios"] == 4
    assert sensitivity["summary"]["train_positive_scenarios"] >= 1
