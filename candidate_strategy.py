"""Price-only candidate strategies for reproducible A-share research."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import isfinite
from typing import Any

import pandas as pd


TREND_PULLBACK_RULE_ID = "trend_low_vol_pullback_v2"
DEFAULT_CANDIDATE_RULE_ID = TREND_PULLBACK_RULE_ID
CANDIDATE_RULESET_VERSION = "candidate_rules_v3_20260727"
CAPITAL_FLOW_RULE_IDS = {
    "capital_flow_pullback_regime_balanced",
    "capital_flow_pullback_regime_confirmed",
    "capital_flow_pullback_regime_strong",
}
PULLBACK_RECOVERY_RULE_IDS = {
    "pullback_recovery",
    "pullback_recovery_regime",
    *CAPITAL_FLOW_RULE_IDS,
}
REGIME_FILTERED_RULE_IDS = {
    "pullback_recovery_regime",
    *CAPITAL_FLOW_RULE_IDS,
}


@dataclass(frozen=True)
class CandidateRule:
    rule_id: str
    label: str
    min_return_60d: float
    max_return_60d: float
    min_return_3d: float
    max_return_3d: float
    min_rsi_6: float
    max_rsi_6: float
    min_close_to_ma20: float
    max_close_to_ma20: float
    max_volatility_20d: float
    min_amount_20d: float = 100_000_000.0
    max_single_day_gain: float = 0.095
    min_volume_ratio_20d: float | None = None
    min_amount_ratio_20d: float | None = None
    min_turnover: float | None = None
    max_turnover: float | None = None
    min_turnover_ratio_20d: float | None = None


CANDIDATE_RULES: dict[str, CandidateRule] = {
    "low_vol_trend": CandidateRule(
        rule_id="low_vol_trend",
        label="低波动趋势",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.04,
        max_return_3d=0.04,
        min_rsi_6=40,
        max_rsi_6=70,
        min_close_to_ma20=0.98,
        max_close_to_ma20=1.08,
        max_volatility_20d=0.040,
    ),
    TREND_PULLBACK_RULE_ID: CandidateRule(
        rule_id=TREND_PULLBACK_RULE_ID,
        label="趋势低波回撤",
        min_return_60d=0.03,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=0.00,
        min_rsi_6=25,
        max_rsi_6=50,
        min_close_to_ma20=0.97,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.040,
    ),
    "regime_reversal": CandidateRule(
        rule_id="regime_reversal",
        label="趋势内短期反转",
        min_return_60d=0.00,
        max_return_60d=0.35,
        min_return_3d=-0.12,
        max_return_3d=-0.02,
        min_rsi_6=10,
        max_rsi_6=35,
        min_close_to_ma20=0.90,
        max_close_to_ma20=1.02,
        max_volatility_20d=0.055,
    ),
    "near_high_low_vol": CandidateRule(
        rule_id="near_high_low_vol",
        label="低波动接近阶段新高",
        min_return_60d=0.03,
        max_return_60d=0.35,
        min_return_3d=-0.03,
        max_return_3d=0.05,
        min_rsi_6=45,
        max_rsi_6=72,
        min_close_to_ma20=0.99,
        max_close_to_ma20=1.10,
        max_volatility_20d=0.040,
    ),
    "rsi2_uptrend_reversal": CandidateRule(
        rule_id="rsi2_uptrend_reversal",
        label="上升趋势RSI2超卖反转",
        min_return_60d=0.02,
        max_return_60d=0.35,
        min_return_3d=-0.12,
        max_return_3d=-0.01,
        min_rsi_6=10,
        max_rsi_6=50,
        min_close_to_ma20=0.90,
        max_close_to_ma20=1.02,
        max_volatility_20d=0.055,
    ),
    "three_down_uptrend": CandidateRule(
        rule_id="three_down_uptrend",
        label="上升趋势三连跌反转",
        min_return_60d=0.02,
        max_return_60d=0.35,
        min_return_3d=-0.12,
        max_return_3d=-0.01,
        min_rsi_6=15,
        max_rsi_6=45,
        min_close_to_ma20=0.93,
        max_close_to_ma20=1.02,
        max_volatility_20d=0.050,
    ),
    "pullback_recovery": CandidateRule(
        rule_id="pullback_recovery",
        label="趋势回撤止跌",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=-0.01,
        min_rsi_6=25,
        max_rsi_6=52,
        min_close_to_ma20=0.95,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.045,
    ),
    "pullback_recovery_regime": CandidateRule(
        rule_id="pullback_recovery_regime",
        label="市场广度过滤的趋势回撤止跌",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=-0.01,
        min_rsi_6=25,
        max_rsi_6=52,
        min_close_to_ma20=0.95,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.045,
    ),
    "capital_flow_pullback_regime_balanced": CandidateRule(
        rule_id="capital_flow_pullback_regime_balanced",
        label="量价换手温和增强的趋势回撤止跌",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=-0.01,
        min_rsi_6=25,
        max_rsi_6=52,
        min_close_to_ma20=0.95,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.045,
        min_volume_ratio_20d=1.00,
        min_amount_ratio_20d=1.00,
        min_turnover=0.005,
        max_turnover=0.12,
        min_turnover_ratio_20d=1.00,
    ),
    "capital_flow_pullback_regime_confirmed": CandidateRule(
        rule_id="capital_flow_pullback_regime_confirmed",
        label="量价换手确认增强的趋势回撤止跌",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=-0.01,
        min_rsi_6=25,
        max_rsi_6=52,
        min_close_to_ma20=0.95,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.045,
        min_volume_ratio_20d=1.20,
        min_amount_ratio_20d=1.20,
        min_turnover=0.01,
        max_turnover=0.12,
        min_turnover_ratio_20d=1.10,
    ),
    "capital_flow_pullback_regime_strong": CandidateRule(
        rule_id="capital_flow_pullback_regime_strong",
        label="量价换手强确认的趋势回撤止跌",
        min_return_60d=0.02,
        max_return_60d=0.30,
        min_return_3d=-0.08,
        max_return_3d=-0.01,
        min_rsi_6=25,
        max_rsi_6=52,
        min_close_to_ma20=0.95,
        max_close_to_ma20=1.03,
        max_volatility_20d=0.045,
        min_volume_ratio_20d=1.50,
        min_amount_ratio_20d=1.50,
        min_turnover=0.015,
        max_turnover=0.15,
        min_turnover_ratio_20d=1.20,
    ),
}


def candidate_rule_fingerprint(rule_id: str) -> str:
    rule = CANDIDATE_RULES[rule_id]
    payload = json.dumps(
        asdict(rule),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_candidate_frame(data: pd.DataFrame | None) -> pd.DataFrame:
    """Calculate features using only information available at each close."""
    if data is None or getattr(data, "empty", True):
        return pd.DataFrame()
    frame = data.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame = frame.sort_index()
    for column in required | {"amount", "outstanding_share", "turnover", "turnover_rate"}:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    close = frame["close"]
    volume = frame["volume"]
    returns = close.pct_change()
    amount = (
        frame["amount"]
        if "amount" in frame.columns
        else pd.Series(float("nan"), index=frame.index, dtype="float64")
    )
    turnover = (
        frame["turnover"]
        if "turnover" in frame.columns
        else frame.get("turnover_rate")
    )
    if turnover is None and "outstanding_share" in frame.columns:
        turnover = volume / frame["outstanding_share"].replace(0, pd.NA)
    if turnover is not None:
        frame["turnover"] = pd.to_numeric(turnover, errors="coerce")
    frame["ma5"] = close.rolling(5, min_periods=5).mean()
    frame["ma10"] = close.rolling(10, min_periods=10).mean()
    frame["ma20"] = close.rolling(20, min_periods=20).mean()
    frame["ma60"] = close.rolling(60, min_periods=60).mean()
    frame["ma120"] = close.rolling(120, min_periods=120).mean()
    frame["return_1d"] = returns
    frame["return_3d"] = close.pct_change(3)
    frame["return_20d"] = close.pct_change(20)
    frame["return_60d"] = close.pct_change(60)
    frame["volatility_20d"] = returns.rolling(20, min_periods=15).std()
    frame["amount_20d"] = (
        amount.rolling(20, min_periods=15).median()
    )
    frame["volume_ratio_20d"] = volume / (
        volume.shift(1).rolling(20, min_periods=15).median().replace(0, pd.NA)
    )
    frame["amount_ratio_20d"] = amount / (
        amount.shift(1).rolling(20, min_periods=15).median().replace(0, pd.NA)
    )
    frame["turnover_ratio_20d"] = (
        frame["turnover"]
        / frame["turnover"].shift(1).rolling(20, min_periods=15).median().replace(0, pd.NA)
        if "turnover" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="Float64")
    )
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(6, min_periods=6).mean()
    losses = -delta.clip(upper=0).rolling(6, min_periods=6).mean()
    relative_strength = gains / losses.replace(0, pd.NA)
    frame["rsi_6"] = 100 - 100 / (1 + relative_strength)
    frame.loc[(losses == 0) & (gains > 0), "rsi_6"] = 100.0
    frame.loc[(losses == 0) & (gains == 0), "rsi_6"] = 50.0
    gains_2 = delta.clip(lower=0).rolling(2, min_periods=2).mean()
    losses_2 = -delta.clip(upper=0).rolling(2, min_periods=2).mean()
    relative_strength_2 = gains_2 / losses_2.replace(0, pd.NA)
    frame["rsi_2"] = 100 - 100 / (1 + relative_strength_2)
    frame.loc[(losses_2 == 0) & (gains_2 > 0), "rsi_2"] = 100.0
    frame.loc[(losses_2 == 0) & (gains_2 == 0), "rsi_2"] = 50.0
    rolling_std = close.rolling(20, min_periods=20).std(ddof=0)
    frame["boll_mid"] = frame["ma20"]
    frame["boll_upper"] = frame["ma20"] + rolling_std * 2
    frame["boll_lower"] = frame["ma20"] - rolling_std * 2
    frame["high_60d"] = frame["high"].rolling(60, min_periods=60).max()
    frame["distance_to_high_60d"] = close / frame["high_60d"] - 1
    frame["close_to_ma20"] = close / frame["ma20"]
    frame["ma20_to_ma60"] = frame["ma20"] / frame["ma60"] - 1
    frame["ma60_slope_5d"] = frame["ma60"] / frame["ma60"].shift(5) - 1
    frame["down_days_3"] = (returns < 0).astype(int).rolling(3, min_periods=3).sum()
    frame["intraday_return"] = close / frame["open"] - 1
    price_range = (frame["high"] - frame["low"]).replace(0, pd.NA)
    frame["close_location"] = (close - frame["low"]) / price_range
    return frame


def evaluate_candidate_at(
    frame: pd.DataFrame,
    position: int = -1,
    *,
    rule_id: str = DEFAULT_CANDIDATE_RULE_ID,
) -> dict[str, Any]:
    """Evaluate one historical close without reading future rows."""
    rule = CANDIDATE_RULES[rule_id]
    if frame is None or getattr(frame, "empty", True) or len(frame) < 80:
        return {"passed": False, "rule_id": rule_id, "reason": "K线不足80个交易日"}
    try:
        row = frame.iloc[position]
    except IndexError:
        return {"passed": False, "rule_id": rule_id, "reason": "指定交易日不存在"}
    metrics = {
        key: _number(row.get(key))
        for key in (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount_20d",
            "volume_ratio_20d",
            "amount_ratio_20d",
            "turnover",
            "turnover_ratio_20d",
            "ma5",
            "ma10",
            "ma20",
            "ma60",
            "ma120",
            "return_1d",
            "return_3d",
            "return_20d",
            "return_60d",
            "volatility_20d",
            "rsi_6",
            "rsi_2",
            "boll_mid",
            "boll_upper",
            "boll_lower",
            "distance_to_high_60d",
            "close_to_ma20",
            "ma20_to_ma60",
            "ma60_slope_5d",
            "down_days_3",
            "intraday_return",
            "close_location",
        )
    }
    if any(metrics.get(key) is None for key in ("close", "ma20", "ma60", "return_60d", "volatility_20d")):
        return {"passed": False, "rule_id": rule_id, "reason": "关键指标缺失", "metrics": metrics}

    checks = {
        "价格站上MA60": metrics["close"] > metrics["ma60"],
        "MA20高于MA60": metrics["ma20"] > metrics["ma60"],
        "60日涨幅适中": rule.min_return_60d <= metrics["return_60d"] <= rule.max_return_60d,
        "3日回撤范围": (
            metrics["return_3d"] is not None
            and rule.min_return_3d <= metrics["return_3d"] <= rule.max_return_3d
        ),
        "RSI6范围": (
            metrics["rsi_6"] is not None
            and rule.min_rsi_6 <= metrics["rsi_6"] <= rule.max_rsi_6
        ),
        "价格靠近MA20": (
            metrics["close_to_ma20"] is not None
            and rule.min_close_to_ma20 <= metrics["close_to_ma20"] <= rule.max_close_to_ma20
        ),
        "20日波动受控": metrics["volatility_20d"] <= rule.max_volatility_20d,
        "20日成交额达标": (
            metrics["amount_20d"] is not None and metrics["amount_20d"] >= rule.min_amount_20d
        ),
        "信号日未接近涨停": (
            metrics["return_1d"] is not None and metrics["return_1d"] < rule.max_single_day_gain
        ),
    }
    if rule_id == "near_high_low_vol":
        checks["距60日高点不超过5%"] = (
            metrics["distance_to_high_60d"] is not None
            and metrics["distance_to_high_60d"] >= -0.05
        )
    elif rule_id == "rsi2_uptrend_reversal":
        checks["MA60近5日上行"] = (
            metrics["ma60_slope_5d"] is not None and metrics["ma60_slope_5d"] > 0
        )
        checks["RSI2不高于10"] = metrics["rsi_2"] is not None and metrics["rsi_2"] <= 10
    elif rule_id == "three_down_uptrend":
        checks["连续3日下跌"] = metrics["down_days_3"] == 3
    elif rule_id in PULLBACK_RECOVERY_RULE_IDS:
        checks["信号日收阳"] = metrics["intraday_return"] is not None and metrics["intraday_return"] > 0
        checks["收盘位于日内区间上部"] = (
            metrics["close_location"] is not None and metrics["close_location"] >= 0.65
        )
    if rule.min_volume_ratio_20d is not None:
        checks["成交量相对20日中位数增强"] = (
            metrics["volume_ratio_20d"] is not None
            and metrics["volume_ratio_20d"] >= rule.min_volume_ratio_20d
        )
    if rule.min_amount_ratio_20d is not None:
        checks["成交额相对20日中位数增强"] = (
            metrics["amount_ratio_20d"] is not None
            and metrics["amount_ratio_20d"] >= rule.min_amount_ratio_20d
        )
    if rule.min_turnover is not None:
        checks["换手率达到最低活跃度"] = (
            metrics["turnover"] is not None and metrics["turnover"] >= rule.min_turnover
        )
    if rule.max_turnover is not None:
        checks["换手率未过热"] = (
            metrics["turnover"] is not None and metrics["turnover"] <= rule.max_turnover
        )
    if rule.min_turnover_ratio_20d is not None:
        checks["换手率相对20日中位数增强"] = (
            metrics["turnover_ratio_20d"] is not None
            and metrics["turnover_ratio_20d"] >= rule.min_turnover_ratio_20d
        )
    passed = all(checks.values())
    return {
        "passed": passed,
        "rule_id": rule_id,
        "label": rule.label,
        "score": round(candidate_score(metrics, rule_id=rule_id), 3),
        "checks": checks,
        "metrics": metrics,
        "reason": "全部候选条件通过" if passed else f"候选条件命中 {sum(checks.values())}/{len(checks)}",
        "as_of_date": str(frame.index[position])[:10],
    }


def candidate_score(metrics: dict[str, Any], *, rule_id: str = DEFAULT_CANDIDATE_RULE_ID) -> float:
    """Rank passing stocks without cross-sectional future information."""
    rule = CANDIDATE_RULES[rule_id]
    volatility = _number(metrics.get("volatility_20d")) or rule.max_volatility_20d
    return_60d = _number(metrics.get("return_60d")) or 0.0
    return_3d = _number(metrics.get("return_3d")) or 0.0
    rsi_6 = _number(metrics.get("rsi_6")) or 50.0
    close_to_ma20 = _number(metrics.get("close_to_ma20")) or 1.0
    amount_20d = _number(metrics.get("amount_20d")) or rule.min_amount_20d

    low_vol_score = _bounded(1 - volatility / max(rule.max_volatility_20d, 0.001))
    momentum_center = (rule.min_return_60d + rule.max_return_60d) / 2
    momentum_span = max((rule.max_return_60d - rule.min_return_60d) / 2, 0.01)
    momentum_score = _bounded(1 - abs(return_60d - momentum_center) / momentum_span)
    pullback_target = -0.025 if rule_id in {TREND_PULLBACK_RULE_ID, "regime_reversal"} else 0.0
    pullback_span = max(abs(rule.min_return_3d - rule.max_return_3d), 0.02)
    pullback_score = _bounded(1 - abs(return_3d - pullback_target) / pullback_span)
    rsi_target = 40.0 if rule_id in {TREND_PULLBACK_RULE_ID, "regime_reversal"} else 55.0
    rsi_score = _bounded(1 - abs(rsi_6 - rsi_target) / 25.0)
    ma_score = _bounded(1 - abs(close_to_ma20 - 1.0) / 0.08)
    liquidity_score = _bounded(amount_20d / 500_000_000.0)
    base_score = (
        low_vol_score * 25
        + momentum_score * 15
        + pullback_score * 25
        + rsi_score * 15
        + ma_score * 15
        + liquidity_score * 5
    )
    if rule_id not in CAPITAL_FLOW_RULE_IDS:
        return base_score
    flow_values = [
        _bounded((_number(metrics.get("volume_ratio_20d")) or 0) / 2),
        _bounded((_number(metrics.get("amount_ratio_20d")) or 0) / 2),
        _bounded((_number(metrics.get("turnover_ratio_20d")) or 0) / 2),
    ]
    flow_score = sum(flow_values) / len(flow_values) * 100
    return base_score * 0.80 + flow_score * 0.20


def candidate_trade_levels(
    metrics: dict[str, Any],
    *,
    rule_id: str = DEFAULT_CANDIDATE_RULE_ID,
) -> dict[str, float | None]:
    """Build the same daily-level execution fields used by paper validation."""
    close = _number(metrics.get("close"))
    ma20 = _number(metrics.get("ma20"))
    boll_lower = _number(metrics.get("boll_lower"))
    boll_upper = _number(metrics.get("boll_upper"))
    if close is None:
        return {
            "buy_zone_low": None,
            "buy_zone_high": None,
            "stop_loss": None,
            "take_profit_1": None,
        }
    if rule_id in {"rsi2_uptrend_reversal", "three_down_uptrend"}:
        support = max(value for value in (_number(metrics.get("ma60")), close * 0.97) if value is not None)
        buy_low = min(support, close * 0.985)
        buy_high = close * 1.015
        stop_loss = close * 0.97
        ma5 = _number(metrics.get("ma5"))
        take_profit = min(
            max(value for value in (ma5, close * 1.01) if value is not None),
            close * 1.03,
        )
    elif rule_id in PULLBACK_RECOVERY_RULE_IDS:
        support = max(value for value in (_number(metrics.get("ma60")), close * 0.97) if value is not None)
        buy_low = min(support, close * 0.985)
        buy_high = close * 1.015
        stop_loss = close * 0.97
        take_profit = min(
            max(value for value in (ma20, close * 1.01) if value is not None),
            close * 1.035,
        )
    else:
        support = max(value for value in (boll_lower, close * 0.90) if value is not None)
        buy_high = min(value for value in (ma20, close) if value is not None)
        buy_low = min(support, buy_high)
        stop_loss = support - close * 0.02
        take_profit = max(value for value in (boll_upper, close * 1.04) if value is not None)
    return {
        "buy_zone_low": round(buy_low, 3),
        "buy_zone_high": round(buy_high, 3),
        "stop_loss": round(stop_loss, 3),
        "take_profit_1": round(take_profit, 3),
    }


def candidate_signal_mask(frame: pd.DataFrame, *, rule_id: str) -> pd.Series:
    """Vectorized mirror of ``evaluate_candidate_at`` for the research runner."""
    rule = CANDIDATE_RULES[rule_id]
    mask = (
        (frame["close"] > frame["ma60"])
        & (frame["ma20"] > frame["ma60"])
        & frame["return_60d"].between(rule.min_return_60d, rule.max_return_60d)
        & frame["return_3d"].between(rule.min_return_3d, rule.max_return_3d)
        & frame["rsi_6"].between(rule.min_rsi_6, rule.max_rsi_6)
        & frame["close_to_ma20"].between(rule.min_close_to_ma20, rule.max_close_to_ma20)
        & (frame["volatility_20d"] <= rule.max_volatility_20d)
        & (frame["amount_20d"] >= rule.min_amount_20d)
        & (frame["return_1d"] < rule.max_single_day_gain)
    ).fillna(False)
    if rule_id == "near_high_low_vol":
        mask &= (frame["distance_to_high_60d"] >= -0.05).fillna(False)
    elif rule_id == "rsi2_uptrend_reversal":
        mask &= (frame["ma60_slope_5d"] > 0).fillna(False)
        mask &= (frame["rsi_2"] <= 10).fillna(False)
    elif rule_id == "three_down_uptrend":
        mask &= (frame["down_days_3"] == 3).fillna(False)
    elif rule_id in PULLBACK_RECOVERY_RULE_IDS:
        mask &= (frame["intraday_return"] > 0).fillna(False)
        mask &= (frame["close_location"] >= 0.65).fillna(False)
    if rule.min_volume_ratio_20d is not None:
        mask &= (frame["volume_ratio_20d"] >= rule.min_volume_ratio_20d).fillna(False)
    if rule.min_amount_ratio_20d is not None:
        mask &= (frame["amount_ratio_20d"] >= rule.min_amount_ratio_20d).fillna(False)
    if rule.min_turnover is not None:
        mask &= (frame["turnover"] >= rule.min_turnover).fillna(False)
    if rule.max_turnover is not None:
        mask &= (frame["turnover"] <= rule.max_turnover).fillna(False)
    if rule.min_turnover_ratio_20d is not None:
        mask &= (frame["turnover_ratio_20d"] >= rule.min_turnover_ratio_20d).fillna(False)
    return mask


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
