"""回测引擎测试"""
import pytest
from datetime import date

from backtest_engine import (
    BacktestEngine, EvaluationConfig,
    map_signal_to_direction, map_signal_to_position,
)


# ============================================================
# Fixtures
# ============================================================

def _make_forward(days=20, start=10.0, step=0.1):
    """生成上升趋势的前向数据"""
    highs = [start + i * step + 0.2 for i in range(1, days + 1)]
    lows = [start + i * step - 0.2 for i in range(1, days + 1)]
    closes = [start + i * step for i in range(1, days + 1)]
    dt = date(2025, 6, 2)
    dates = [dt.replace(day=min(dt.day + i, 28)) for i in range(days)]
    return highs, lows, closes, dates


def _make_forward_down(days=20, start=10.0, step=0.1):
    """生成下降趋势的前向数据"""
    highs = [start - i * step + 0.2 for i in range(1, days + 1)]
    lows = [start - i * step - 0.2 for i in range(1, days + 1)]
    closes = [start - i * step for i in range(1, days + 1)]
    dt = date(2025, 6, 2)
    dates = [dt.replace(day=min(dt.day + i, 28)) for i in range(days)]
    return highs, lows, closes, dates


# ============================================================
# TestSignalMapping
# ============================================================

class TestSignalMapping:

    def test_buy_signal_to_direction(self):
        assert map_signal_to_direction("偏多信号（强）") == "up"
        assert map_signal_to_direction("偏多信号") == "up"

    def test_sell_signal_to_direction(self):
        assert map_signal_to_direction("偏空信号（强）") == "down"
        assert map_signal_to_direction("偏空信号") == "down"

    def test_neutral_signal_to_direction(self):
        assert map_signal_to_direction("观望") == "flat"

    def test_unknown_signal_defaults_flat(self):
        assert map_signal_to_direction("random") == "flat"

    def test_buy_signal_to_position(self):
        assert map_signal_to_position("偏多信号") == "long"
        assert map_signal_to_position("偏多信号（强）") == "long"

    def test_other_signals_to_cash(self):
        assert map_signal_to_position("偏空信号") == "cash"
        assert map_signal_to_position("观望") == "cash"


# ============================================================
# TestEvaluateSingle
# ============================================================

class TestEvaluateSingle:

    def test_bullish_signal_with_uptrend(self):
        """偏多信号 + 上升趋势 → win"""
        highs, lows, closes, dates = _make_forward(days=20, step=0.3)
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["eval_status"] == "completed"
        assert result["position_recommendation"] == "long"
        assert result["direction_expected"] == "up"
        assert result["outcome"] == "win"
        assert result["direction_correct"] is True
        assert result["stock_return_pct"] > 0

    def test_bearish_signal_with_downtrend(self):
        """偏空信号 + 下跌趋势 → win"""
        highs, lows, closes, dates = _make_forward_down(days=20, step=0.3)
        result = BacktestEngine.evaluate_single(
            signal="偏空信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["eval_status"] == "completed"
        assert result["direction_expected"] == "down"
        assert result["position_recommendation"] == "cash"
        assert result["outcome"] == "win"
        assert result["direction_correct"] is True

    def test_bullish_signal_with_downtrend(self):
        """偏多信号 + 下跌趋势 → loss"""
        highs, lows, closes, dates = _make_forward_down(days=20, step=0.3)
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["outcome"] == "loss"
        assert result["direction_correct"] is False

    def test_neutral_small_move(self):
        """观望信号 + 小幅波动 → win（正确预测横盘）"""
        highs = [10.05, 10.08, 10.03, 10.06, 10.02, 10.05, 10.04, 10.03,
                 10.06, 10.02, 10.05, 10.04, 10.03, 10.05, 10.02, 10.06,
                 10.04, 10.03, 10.05, 10.04]
        lows = [9.95, 9.92, 9.97, 9.94, 9.98, 9.95, 9.96, 9.97,
                9.94, 9.98, 9.95, 9.96, 9.97, 9.95, 9.98, 9.94,
                9.96, 9.97, 9.95, 9.96]
        closes = [10.0] * 20
        dates = [date(2025, 6, i + 2) for i in range(20)]
        result = BacktestEngine.evaluate_single(
            signal="观望",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["outcome"] == "win"

    def test_stop_loss_hit(self):
        """止损触发"""
        highs, lows, closes, dates = [], [], [], []
        start = date(2025, 6, 2)
        for i in range(20):
            closes.append(9.0 - i * 0.1)  # 持续下跌
            highs.append(closes[-1] + 0.3)
            lows.append(closes[-1] - 0.3)
            dates.append(date(2025, 6, 2 + min(i, 25)))
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
            stop_loss=9.0,  # 止损线
        )
        assert result["hit_stop_loss"] is True
        assert result["first_hit"] == "stop_loss"

    def test_take_profit_hit(self):
        """止盈触发"""
        highs, lows, closes, dates = [], [], [], []
        for i in range(20):
            closes.append(10.0 + i * 0.2)
            highs.append(closes[-1] + 0.5)
            lows.append(closes[-1] - 0.2)
            dates.append(date(2025, 6, 2 + min(i, 25)))
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
            take_profit=12.0,
        )
        assert result["hit_take_profit"] is True
        assert result["first_hit"] == "take_profit"

    def test_zero_or_negative_price_returns_error(self):
        highs, lows, closes, dates = _make_forward()
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["eval_status"] == "error"

    def test_insufficient_forward_data(self):
        highs, lows, closes, dates = _make_forward(days=10)
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["eval_status"] == "insufficient_data"

    def test_cash_position_has_zero_sim_return(self):
        """空仓信号模拟收益为 0"""
        highs, lows, closes, dates = _make_forward_down(days=20, step=0.2)
        result = BacktestEngine.evaluate_single(
            signal="偏空信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
        )
        assert result["position_recommendation"] == "cash"
        assert result["simulated_return_pct"] == 0.0

    def test_custom_config(self):
        config = EvaluationConfig(eval_window_days=10, neutral_band_pct=3.0)
        highs, lows, closes, dates = _make_forward(days=10, step=0.1)
        result = BacktestEngine.evaluate_single(
            signal="偏多信号",
            analysis_date=date(2025, 6, 1),
            start_price=10.0,
            forward_highs=highs,
            forward_lows=lows,
            forward_closes=closes,
            forward_dates=dates,
            config=config,
        )
        assert result["eval_window_days"] == 10


# ============================================================
# TestComputeSummary
# ============================================================

class TestComputeSummary:

    def test_empty_results(self):
        summary = BacktestEngine.compute_summary(results=[], symbol="TEST")
        assert summary["total_evaluations"] == 0
        assert summary["win_rate_pct"] is None

    def test_mixed_results(self):
        highs_u, lows_u, closes_u, dates_u = _make_forward(days=20, step=0.3)
        highs_d, lows_d, closes_d, dates_d = _make_forward_down(days=20, step=0.3)

        r1 = BacktestEngine.evaluate_single(
            signal="偏多信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=highs_u, forward_lows=lows_u,
            forward_closes=closes_u, forward_dates=dates_u,
        )
        r2 = BacktestEngine.evaluate_single(
            signal="偏多信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=highs_d, forward_lows=lows_d,
            forward_closes=closes_d, forward_dates=dates_d,
        )
        summary = BacktestEngine.compute_summary(
            results=[r1, r2], symbol="TEST",
        )
        assert summary["total_evaluations"] == 2
        assert summary["win_count"] == 1
        assert summary["loss_count"] == 1
        assert summary["direction_accuracy_pct"] == 50.0
        assert summary["win_rate_pct"] == 50.0

    def test_signal_breakdown(self):
        highs_u, lows_u, closes_u, dates_u = _make_forward(days=20, step=0.3)
        highs_d, lows_d, closes_d, dates_d = _make_forward_down(days=20, step=0.3)

        r1 = BacktestEngine.evaluate_single(
            signal="偏多信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=highs_u, forward_lows=lows_u,
            forward_closes=closes_u, forward_dates=dates_u,
        )
        r2 = BacktestEngine.evaluate_single(
            signal="偏空信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=highs_d, forward_lows=lows_d,
            forward_closes=closes_d, forward_dates=dates_d,
        )
        summary = BacktestEngine.compute_summary(
            results=[r1, r2], symbol="TEST",
        )
        bd = summary["signal_breakdown"]
        assert "偏多信号" in bd
        assert "偏空信号" in bd
        assert bd["偏多信号"]["win"] == 1
        assert bd["偏空信号"]["win"] == 1

    def test_all_completed_count(self):
        highs, lows, closes, dates = _make_forward(days=20, step=0.3)
        r1 = BacktestEngine.evaluate_single(
            signal="偏多信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=highs, forward_lows=lows,
            forward_closes=closes, forward_dates=dates,
        )
        # insufficient
        short_h, short_l, short_c, short_d = _make_forward(days=10)
        r2 = BacktestEngine.evaluate_single(
            signal="偏多信号", analysis_date=date(2025, 6, 1), start_price=10.0,
            forward_highs=short_h, forward_lows=short_l,
            forward_closes=short_c, forward_dates=short_d,
        )
        summary = BacktestEngine.compute_summary(
            results=[r1, r2], symbol="TEST",
        )
        assert summary["total_evaluations"] == 2
        assert summary["completed_count"] == 1
        assert summary["insufficient_count"] == 1
