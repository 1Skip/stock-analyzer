"""
回测引擎（纯逻辑，零外部依赖）
基于 daily_stock_analysis 引擎适配，对接本项目的信号体系
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Sequence


# ============================================================
# 信号 → 方向/仓位映射
# ============================================================

# 本项目的信号语言 → 引擎方向
_SIGNAL_TO_DIRECTION: dict[str, str] = {
    "偏多信号（强）": "up",
    "偏多信号": "up",
    "偏空信号（强）": "down",
    "偏空信号": "down",
    "观望": "flat",
}

# 引擎方向 → 仓位（本项目只做多）
_DIRECTION_TO_POSITION: dict[str, str] = {
    "up": "long",
    "down": "cash",
    "flat": "cash",
    "not_down": "long",
}


def map_signal_to_direction(signal: str) -> str:
    """将本项目信号映射为引擎方向"""
    return _SIGNAL_TO_DIRECTION.get(signal, "flat")


def map_signal_to_position(signal: str) -> str:
    """将本项目信号映射为仓位建议"""
    direction = map_signal_to_direction(signal)
    return _DIRECTION_TO_POSITION.get(direction, "cash")


# ============================================================
# 配置
# ============================================================

@dataclass(frozen=True)
class EvaluationConfig:
    eval_window_days: int = 20
    neutral_band_pct: float = 2.0
    engine_version: str = "v1"


# ============================================================
# 回测引擎
# ============================================================

class BacktestEngine:
    """日线做多回测引擎"""

    @classmethod
    def evaluate_single(
        cls,
        *,
        signal: str,
        analysis_date: date,
        start_price: float,
        forward_highs: Sequence[Optional[float]],
        forward_lows: Sequence[Optional[float]],
        forward_closes: Sequence[Optional[float]],
        forward_dates: Sequence[date],
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        config: Optional[EvaluationConfig] = None,
    ) -> dict[str, Any]:
        """评估单次信号在后续窗口中的表现

        Args:
            signal: 本项目信号（偏多信号/偏空信号/观望 等）
            analysis_date: 分析日期
            start_price: 当日收盘价
            forward_highs/lows/closes/dates: 后续 N 天的 OHLC
            stop_loss: 止损价（可选）
            take_profit: 止盈价（可选）
            config: 评估参数
        """
        cfg = config or EvaluationConfig()

        if start_price is None or start_price <= 0:
            return cls._error_result(analysis_date, signal)

        if len(forward_closes) < cfg.eval_window_days:
            return cls._insufficient_result(analysis_date, signal, cfg.eval_window_days)

        window_highs = list(forward_highs[:cfg.eval_window_days])
        window_lows = list(forward_lows[:cfg.eval_window_days])
        window_closes = list(forward_closes[:cfg.eval_window_days])
        window_dates = list(forward_dates[:cfg.eval_window_days])

        end_close = window_closes[-1]
        max_high = max((h for h in window_highs if h is not None), default=None)
        min_low = min((l for l in window_lows if l is not None), default=None)

        stock_return_pct: Optional[float]
        if end_close is None:
            stock_return_pct = None
        else:
            stock_return_pct = (end_close - start_price) / start_price * 100

        direction = map_signal_to_direction(signal)
        position = map_signal_to_position(signal)

        outcome, direction_correct = cls._classify_outcome(
            stock_return_pct=stock_return_pct,
            direction_expected=direction,
            neutral_band_pct=cfg.neutral_band_pct,
        )

        (
            hit_sl, hit_tp, first_hit, first_hit_date, first_hit_days,
            sim_exit_price, sim_exit_reason,
        ) = cls._evaluate_targets(
            position=position,
            stop_loss=stop_loss,
            take_profit=take_profit,
            window_highs=window_highs,
            window_lows=window_lows,
            window_dates=window_dates,
            end_close=end_close,
        )

        sim_return_pct: Optional[float]
        if position != "long":
            sim_return_pct = 0.0
        elif sim_exit_price is None:
            sim_return_pct = None
        else:
            sim_return_pct = (sim_exit_price - start_price) / start_price * 100

        return {
            "analysis_date": analysis_date,
            "eval_window_days": cfg.eval_window_days,
            "engine_version": cfg.engine_version,
            "eval_status": "completed",
            "signal": signal,
            "position_recommendation": position,
            "direction_expected": direction,
            "start_price": start_price,
            "end_close": end_close,
            "max_high": max_high,
            "min_low": min_low,
            "stock_return_pct": round(stock_return_pct, 2) if stock_return_pct is not None else None,
            "direction_correct": direction_correct,
            "outcome": outcome,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "hit_stop_loss": hit_sl,
            "hit_take_profit": hit_tp,
            "first_hit": first_hit,
            "first_hit_date": first_hit_date,
            "first_hit_trading_days": first_hit_days,
            "simulated_entry_price": start_price if position == "long" else None,
            "simulated_exit_price": sim_exit_price,
            "simulated_exit_reason": sim_exit_reason,
            "simulated_return_pct": round(sim_return_pct, 2) if sim_return_pct is not None else None,
        }

    @classmethod
    def compute_summary(
        cls,
        results: Sequence[dict[str, Any]],
        symbol: str = "",
        eval_window_days: int = 20,
    ) -> dict[str, Any]:
        """聚合多条回测结果为汇总指标"""
        completed = [r for r in results if r.get("eval_status") == "completed"]
        total = len(results)
        insufficient = total - len(completed)

        long_count = sum(1 for r in completed if r.get("position_recommendation") == "long")
        cash_count = sum(1 for r in completed if r.get("position_recommendation") == "cash")

        win_count = sum(1 for r in completed if r.get("outcome") == "win")
        loss_count = sum(1 for r in completed if r.get("outcome") == "loss")
        neutral_count = sum(1 for r in completed if r.get("outcome") == "neutral")

        # 方向准确率
        dir_denom = sum(1 for r in completed if r.get("direction_correct") is not None)
        dir_num = sum(1 for r in completed if r.get("direction_correct") is True)
        direction_accuracy = round(dir_num / dir_denom * 100, 2) if dir_denom else None

        # 胜率（不含中性）
        wl_denom = win_count + loss_count
        win_rate = round(win_count / wl_denom * 100, 2) if wl_denom else None
        neutral_rate = round(neutral_count / len(completed) * 100, 2) if completed else None

        # 平均收益
        avg_stock = cls._avg([r.get("stock_return_pct") for r in completed])
        avg_sim = cls._avg([r.get("simulated_return_pct") for r in completed])

        # 止损/止盈触发率
        stop_applicable = [r for r in completed if r.get("position_recommendation") == "long"]
        tp_applicable = stop_applicable
        sl_rate = (
            round(sum(1 for r in stop_applicable if r.get("hit_stop_loss")) / len(stop_applicable) * 100, 2)
            if stop_applicable else None
        )
        tp_rate = (
            round(sum(1 for r in tp_applicable if r.get("hit_take_profit")) / len(tp_applicable) * 100, 2)
            if tp_applicable else None
        )

        # 按信号分类
        signal_breakdown = cls._signal_breakdown(completed)

        return {
            "symbol": symbol,
            "eval_window_days": eval_window_days,
            "engine_version": "v1",
            "total_evaluations": total,
            "completed_count": len(completed),
            "insufficient_count": insufficient,
            "long_count": long_count,
            "cash_count": cash_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "neutral_count": neutral_count,
            "direction_accuracy_pct": direction_accuracy,
            "win_rate_pct": win_rate,
            "neutral_rate_pct": neutral_rate,
            "avg_stock_return_pct": avg_stock,
            "avg_simulated_return_pct": avg_sim,
            "stop_loss_trigger_rate": sl_rate,
            "take_profit_trigger_rate": tp_rate,
            "signal_breakdown": signal_breakdown,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    @classmethod
    def _error_result(cls, analysis_date: date, signal: str) -> dict[str, Any]:
        return {
            "analysis_date": analysis_date,
            "signal": signal,
            "position_recommendation": map_signal_to_position(signal),
            "direction_expected": map_signal_to_direction(signal),
            "eval_status": "error",
        }

    @classmethod
    def _insufficient_result(cls, analysis_date: date, signal: str, eval_days: int) -> dict[str, Any]:
        return {
            "analysis_date": analysis_date,
            "signal": signal,
            "position_recommendation": map_signal_to_position(signal),
            "direction_expected": map_signal_to_direction(signal),
            "eval_status": "insufficient_data",
            "eval_window_days": eval_days,
        }

    @classmethod
    def _classify_outcome(
        cls,
        *,
        stock_return_pct: Optional[float],
        direction_expected: str,
        neutral_band_pct: float,
    ) -> tuple[Optional[str], Optional[bool]]:
        if stock_return_pct is None:
            return None, None

        band = abs(float(neutral_band_pct))
        r = float(stock_return_pct)

        if direction_expected == "up":
            if r >= band:
                return "win", True
            if r <= -band:
                return "loss", False
            return "neutral", None

        if direction_expected == "down":
            if r <= -band:
                return "win", True
            if r >= band:
                return "loss", False
            return "neutral", None

        # flat: 价格波动在 band 内才算正确
        if abs(r) <= band:
            return "win", True
        return "loss", False

    @classmethod
    def _evaluate_targets(
        cls,
        *,
        position: str,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        window_highs: list[Optional[float]],
        window_lows: list[Optional[float]],
        window_dates: list[date],
        end_close: Optional[float],
    ) -> tuple:
        if position != "long":
            return (None, None, "not_applicable", None, None, None, "cash")

        has_target = stop_loss is not None or take_profit is not None
        if not has_target:
            return (None, None, "neither", None, None, end_close, "window_end")

        hit_sl: Optional[bool] = None if stop_loss is None else False
        hit_tp: Optional[bool] = None if take_profit is None else False
        first_hit = "neither"
        first_hit_date: Optional[date] = None
        first_hit_days: Optional[int] = None
        exit_price: Optional[float] = end_close
        exit_reason = "window_end"

        for i, (high, low) in enumerate(zip(window_highs, window_lows), start=1):
            sl_hit = stop_loss is not None and low is not None and low <= stop_loss
            tp_hit = take_profit is not None and high is not None and high >= take_profit

            if sl_hit:
                hit_sl = True
            if tp_hit:
                hit_tp = True

            if not sl_hit and not tp_hit:
                continue

            first_hit_date = window_dates[i - 1] if i - 1 < len(window_dates) else None
            first_hit_days = i

            if sl_hit and tp_hit:
                first_hit = "ambiguous"
                exit_price = stop_loss
                exit_reason = "ambiguous_stop_loss"
                break

            if sl_hit:
                first_hit = "stop_loss"
                exit_price = stop_loss
                exit_reason = "stop_loss"
                break

            first_hit = "take_profit"
            exit_price = take_profit
            exit_reason = "take_profit"
            break

        return (hit_sl, hit_tp, first_hit, first_hit_date, first_hit_days, exit_price, exit_reason)

    @staticmethod
    def _avg(values: list[Optional[float]]) -> Optional[float]:
        items = [float(v) for v in values if v is not None]
        if not items:
            return None
        return round(sum(items) / len(items), 4)

    @classmethod
    def _signal_breakdown(cls, completed: list[dict]) -> dict[str, Any]:
        """按信号类型统计"""
        buckets: dict[str, dict[str, int]] = {}
        for r in completed:
            sig = r.get("signal", "(unknown)")
            b = buckets.setdefault(sig, {"total": 0, "win": 0, "loss": 0, "neutral": 0})
            b["total"] += 1
            outcome = r.get("outcome", "")
            if outcome in ("win", "loss", "neutral"):
                b[outcome] += 1

        enriched: dict[str, Any] = {}
        for sig, b in buckets.items():
            denom = b["win"] + b["loss"]
            wr = round(b["win"] / denom * 100, 2) if denom else None
            enriched[sig] = {**b, "win_rate_pct": wr}
        return enriched
