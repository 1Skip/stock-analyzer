import pandas as pd

from quality_monitor import (
    build_backtest_risk_summary,
    build_compare_scorecard,
    build_hot_data_status,
    build_stock_data_quality_summary,
)


def test_stock_data_quality_flags_missing_extended_info():
    data = pd.DataFrame({"close": [1, 2, 3]})

    summary = build_stock_data_quality_summary(data, quote=None, profile={"market_cap": 1}, extended_info={})

    assert summary["status"] in {"risk", "partial"}
    assert "实时行情缺失，当前价可能使用K线兜底" in summary["issues"]
    assert any("历史K线仅" in item for item in summary["warnings"])


def test_compare_scorecard_sorts_without_changing_source_metrics():
    metrics = [
        {"symbol": "A", "name": "弱", "return_20d": -5, "return_60d": -3, "max_drawdown": -30, "volatility": 80},
        {"symbol": "B", "name": "强", "return_20d": 8, "return_60d": 12, "max_drawdown": -8, "volatility": 20, "up_day_ratio": 60, "trend_slope_20d": 1},
    ]

    scorecard = build_compare_scorecard(metrics)

    assert [item["symbol"] for item in scorecard] == ["B", "A"]
    assert scorecard[0]["compare_score"] > scorecard[1]["compare_score"]


def test_backtest_risk_summary_extracts_worst_cases():
    results = [
        {"eval_status": "completed", "outcome": "win", "simulated_return_pct": 5},
        {"eval_status": "completed", "outcome": "loss", "simulated_return_pct": -4, "analysis_date": "2026-05-01"},
        {"eval_status": "insufficient_data", "outcome": None},
    ]

    summary = build_backtest_risk_summary(results)

    assert summary["completed"] == 2
    assert summary["loss_count"] == 1
    assert summary["worst_simulated_return_pct"] == -4
    assert summary["worst_cases"][0]["analysis_date"] == "2026-05-01"


def test_hot_data_status_reports_empty_sections():
    status = build_hot_data_status({"gainers": [{"代码": "000001"}], "losers": []})

    assert status["status"] == "partial"
    assert status["counts"]["gainers"] == 1
    assert status["missing"] == ["losers"]
