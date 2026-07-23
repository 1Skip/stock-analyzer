from unittest.mock import MagicMock

import pandas as pd

from analysis_signal_tracker import AnalysisSignalTracker
from data.cache import JsonFileCache


def _frame(closes):
    dates = pd.date_range("2026-01-05", periods=len(closes), freq="B")
    return pd.DataFrame({
        "open": closes,
        "high": [value + 0.2 for value in closes],
        "low": [value - 0.2 for value in closes],
        "close": closes,
        "volume": [100_000] * len(closes),
    }, index=dates)


def _tracker(tmp_path):
    cache = JsonFileCache("analysis_signals_test", 86400 * 365, cache_dir=tmp_path)
    return AnalysisSignalTracker(cache=cache)


def test_signal_tracker_freezes_then_settles_true_future_qfq_closes(tmp_path):
    tracker = _tracker(tmp_path)
    history = _frame([10, 10.1, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2, 11.4, 11.6, 11.8, 12.0,
                      12.2, 12.4, 12.6, 12.8, 13.0, 13.2, 13.4, 13.6, 13.8, 14.0, 14.2, 14.4, 14.6])
    observed = history.iloc[:5]
    record = tracker.record_snapshot(
        symbol="000001",
        name="测试股",
        market="CN",
        data=observed,
        signals={"recommendation": "偏多信号"},
        quant_snapshot={"score": 75, "version": "stock_quant_v1"},
        decision_snapshot={"score": 70, "confidence": 80, "risk_level": "低", "action": "观察"},
    )

    updated = tracker.settle_symbol_with_frame("000001", history)
    summary = tracker.summarize(symbol="000001")

    assert record["status"] == "pending"
    assert updated == 1
    assert summary["models"]["technical"][0]["success_rate_pct"] == 100.0
    assert summary["models"]["decision"][2]["sample_count"] == 1
    assert summary["score_buckets"][3]["sample_count"] == 1


def test_signal_tracker_snapshot_is_immutable_for_same_stock_and_trade_date(tmp_path):
    tracker = _tracker(tmp_path)
    data = _frame([10, 10.1, 10.2])
    first = tracker.record_snapshot(
        symbol="000001",
        name="测试股",
        market="CN",
        data=data,
        signals={"recommendation": "偏多信号"},
    )
    second = tracker.record_snapshot(
        symbol="000001",
        name="测试股",
        market="CN",
        data=data,
        signals={"recommendation": "偏空信号"},
    )

    assert first["technical_direction"] == "bullish"
    assert second["technical_direction"] == "bullish"
    assert tracker.summarize()["total_snapshots"] == 1


def test_signal_tracker_bearish_direction_counts_falling_price_as_success(tmp_path):
    tracker = _tracker(tmp_path)
    history = _frame([10, 9.9, 9.8, 9.7, 9.6, 9.4, 9.2])
    tracker.record_snapshot(
        symbol="000002",
        name="测试股2",
        market="CN",
        data=history.iloc[:2],
        signals={"recommendation": "偏空信号"},
        decision_snapshot={"score": 30, "risk_level": "高"},
    )

    tracker.settle_symbol_with_frame("000002", history)
    summary = tracker.summarize(symbol="000002")

    assert summary["models"]["technical"][0]["success_rate_pct"] == 100.0
    assert summary["models"]["technical"][1]["avg_directional_return_pct"] > 0


def test_refresh_history_fetches_real_qfq_frame_and_settles_pending_snapshot(tmp_path):
    quote_service = MagicMock()
    full_history = _frame([10, 10.1, 10.2, 10.4, 10.6, 10.8, 11.0])
    quote_service.get_stock_data.return_value = full_history
    tracker = AnalysisSignalTracker(
        cache=JsonFileCache("analysis_signals_refresh_test", 86400 * 365, cache_dir=tmp_path),
        quote_service=quote_service,
    )
    tracker.record_snapshot(
        symbol="000001",
        name="测试股",
        market="CN",
        data=full_history.iloc[:2],
        signals={"recommendation": "偏多信号"},
    )

    result = tracker.refresh_history(max_symbols=1)

    quote_service.get_stock_data.assert_called_once_with(
        "000001",
        period="1y",
        market="CN",
        adjust="qfq",
    )
    assert result["status"] == "success"
    assert result["symbols"] == 1
    assert result["updated_records"] == 1
    assert result["failed_symbols"] == 0
    assert result["summary"]["models"]["technical"][0]["success_rate_pct"] == 100.0


def test_refresh_history_reports_failed_symbol_without_inventing_outcome(tmp_path):
    quote_service = MagicMock()
    quote_service.get_stock_data.side_effect = RuntimeError("source unavailable")
    tracker = AnalysisSignalTracker(
        cache=JsonFileCache("analysis_signals_refresh_failure", 86400 * 365, cache_dir=tmp_path),
        quote_service=quote_service,
    )
    tracker.record_snapshot(
        symbol="000002",
        name="测试股2",
        market="CN",
        data=_frame([10, 10.1]),
        signals={"recommendation": "偏多信号"},
    )

    result = tracker.refresh_history(max_symbols=1)

    assert result["status"] == "partial"
    assert result["updated_records"] == 0
    assert result["failed_symbols"] == 1
    assert result["summary"]["pending_snapshots"] == 1
    assert result["summary"]["models"]["technical"][0]["sample_count"] == 0


def test_refresh_history_does_not_report_update_before_future_trade_day(tmp_path):
    quote_service = MagicMock()
    observed = _frame([10, 10.1])
    quote_service.get_stock_data.return_value = observed
    tracker = AnalysisSignalTracker(
        cache=JsonFileCache("analysis_signals_no_future", 86400 * 365, cache_dir=tmp_path),
        quote_service=quote_service,
    )
    tracker.record_snapshot(
        symbol="000003",
        name="测试股3",
        market="CN",
        data=observed,
        signals={"recommendation": "偏多信号"},
    )

    result = tracker.refresh_history(max_symbols=1)

    assert result["status"] == "success"
    assert result["updated_records"] == 0
    assert result["summary"]["pending_snapshots"] == 1
    assert result["summary"]["models"]["technical"][0]["sample_count"] == 0
