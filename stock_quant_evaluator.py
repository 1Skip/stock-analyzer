"""Single-stock quantitative snapshot from real daily K-line data."""
from __future__ import annotations

from math import sqrt
from typing import Any, Iterable

import pandas as pd


DEFAULT_PATTERN_HORIZONS = (1, 3, 5)
MIN_PATTERN_HISTORY = 80


def build_stock_quant_snapshot(
    data: pd.DataFrame | None,
    *,
    horizons: Iterable[int] = DEFAULT_PATTERN_HORIZONS,
    min_pattern_samples: int = 5,
) -> dict[str, Any]:
    """Build a read-only quantitative snapshot for one stock.

    The function expects the same daily K-line + indicator frame already used by
    the single-stock analysis page. It never fetches data and never changes
    recommendation or signal logic.
    """
    if data is None or getattr(data, "empty", True):
        return {"status": "empty", "message": "暂无可生成量化评分的日K数据。"}

    frame = _prepare_frame(data)
    if len(frame) < 30:
        return {
            "status": "insufficient_data",
            "message": "日K数据不足，暂不生成个股量化评分。",
            "data_rows": len(frame),
        }

    latest = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else latest
    close = _number(latest.get("close"))
    if close is None or close <= 0:
        return {
            "status": "invalid",
            "message": "最新收盘价缺失，暂不生成个股量化评分。",
            "data_rows": len(frame),
        }

    context = _build_context(frame, latest, previous)
    dimensions = [
        _score_trend(context),
        _score_momentum(context),
        _score_volume(context),
        _score_position(context),
        _score_risk(context),
    ]
    score = round(sum(item["score"] for item in dimensions), 1)
    score = round(max(0.0, min(100.0, score)), 1)
    risk_flags = _risk_flags(context)
    similar_pattern = _evaluate_similar_patterns(
        frame,
        context["pattern_state"],
        tuple(int(item) for item in horizons if int(item) > 0),
        min_samples=max(1, int(min_pattern_samples or 1)),
    )
    support = context.get("support")
    resistance = context.get("resistance")
    return {
        "status": "ok",
        "version": "stock_quant_v1",
        "data_basis": "基于个股分析页当前日K与技术指标；不合并实时行情",
        "calibration": {
            "status": "rule_based_uncalibrated",
            "label": "规则评分，尚未做收益校准",
            "affects_recommendation": False,
        },
        "data_rows": len(frame),
        "score": score,
        "rating": _rating(score),
        "action_hint": _action_hint(score, risk_flags),
        "dimensions": dimensions,
        "risk_flags": risk_flags,
        "key_levels": {
            "support": support,
            "resistance": resistance,
            "support_distance_pct": _distance_pct(close, support),
            "resistance_distance_pct": _upside_pct(close, resistance),
            "recent_low_20": context.get("recent_low_20"),
            "recent_high_20": context.get("recent_high_20"),
            "boll_lower": context.get("boll_lower"),
            "boll_mid": context.get("boll_mid"),
            "boll_upper": context.get("boll_upper"),
        },
        "metrics": {
            "close": close,
            "return_5d_pct": context.get("return_5d_pct"),
            "return_20d_pct": context.get("return_20d_pct"),
            "volume_ratio_5": context.get("volume_ratio_5"),
            "volume_ratio_20": context.get("volume_ratio_20"),
            "volatility_20d_pct": context.get("volatility_20d_pct"),
            "drawdown_20d_pct": context.get("drawdown_20d_pct"),
            "boll_percent": context.get("boll_percent"),
            "rsi_6": context.get("rsi_6"),
            "macd_hist": context.get("macd_hist"),
        },
        "similar_pattern": similar_pattern,
    }


def _prepare_frame(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    if "date" in frame.columns:
        frame["_date"] = frame["date"].astype(str).str[:10]
    else:
        frame["_date"] = frame.index.astype(str).str[:10]
    return frame.reset_index(drop=True)


def _build_context(frame: pd.DataFrame, latest: pd.Series, previous: pd.Series) -> dict[str, Any]:
    close = _number(latest.get("close"))
    previous_close = _number(previous.get("close"))
    recent = frame.tail(20)
    recent_high_20 = _series_max(recent.get("high"))
    recent_low_20 = _series_min(recent.get("low"))
    ma5 = _number(latest.get("ma5"))
    ma10 = _number(latest.get("ma10"))
    ma20 = _number(latest.get("ma20"))
    ma30 = _number(latest.get("ma30"))
    ma60 = _number(latest.get("ma60"))
    boll_lower = _number(latest.get("boll_lower"))
    boll_mid = _number(latest.get("boll_mid"))
    boll_upper = _number(latest.get("boll_upper"))
    volume_ratio_5 = _volume_ratio(frame, 5)
    volume_ratio_20 = _volume_ratio(frame, 20)
    context = {
        "close": close,
        "previous_close": previous_close,
        "price_up": close is not None and previous_close is not None and close > previous_close,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma30": ma30,
        "ma60": ma60,
        "macd": _number(latest.get("macd")),
        "macd_signal": _number(latest.get("macd_signal")),
        "macd_hist": _number(latest.get("macd_hist")),
        "prev_macd_hist": _number(previous.get("macd_hist")),
        "rsi_6": _number(latest.get("rsi_6") if latest.get("rsi_6") is not None else latest.get("rsi")),
        "kdj_k": _number(latest.get("kdj_k")),
        "kdj_d": _number(latest.get("kdj_d")),
        "boll_lower": boll_lower,
        "boll_mid": boll_mid,
        "boll_upper": boll_upper,
        "boll_percent": _number(latest.get("boll_percent")),
        "recent_high_20": recent_high_20,
        "recent_low_20": recent_low_20,
        "return_5d_pct": _lookback_return(frame, 5),
        "return_20d_pct": _lookback_return(frame, 20),
        "volume_ratio_5": volume_ratio_5,
        "volume_ratio_20": volume_ratio_20,
        "volatility_20d_pct": _volatility_pct(frame, 20),
        "drawdown_20d_pct": _drawdown_pct(close, recent_high_20),
    }
    context["support"] = _nearest_below(close, [ma5, ma10, ma20, ma30, boll_lower, recent_low_20])
    context["resistance"] = _nearest_above(close, [boll_upper, recent_high_20])
    context["pattern_state"] = _pattern_state(
        latest,
        volume_ratio_5=volume_ratio_5,
    )
    return context


def _score_trend(context: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    notes: list[str] = []
    close = context.get("close")
    ma5 = context.get("ma5")
    ma10 = context.get("ma10")
    ma20 = context.get("ma20")
    ma60 = context.get("ma60")
    ret20 = context.get("return_20d_pct")
    if _gt(close, ma5):
        score += 4
        notes.append("收盘价站上MA5")
    if _gt(ma5, ma10):
        score += 5
        notes.append("MA5高于MA10")
    if _gt(ma10, ma20):
        score += 5
        notes.append("MA10高于MA20")
    if _gt(close, ma20):
        score += 6
        notes.append("价格站上MA20")
    if _gt(ma20, ma60):
        score += 5
        notes.append("MA20高于MA60")
    if ret20 is not None and ret20 > 0:
        score += 5
        notes.append(f"20日收益{ret20:+.2f}%")
    return _dimension("趋势结构", score, 30, notes)


def _score_momentum(context: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    notes: list[str] = []
    macd = context.get("macd")
    signal = context.get("macd_signal")
    hist = context.get("macd_hist")
    prev_hist = context.get("prev_macd_hist")
    rsi = context.get("rsi_6")
    k = context.get("kdj_k")
    d = context.get("kdj_d")
    ret5 = context.get("return_5d_pct")
    if _gt(macd, signal):
        score += 5
        notes.append("MACD位于信号线上方")
    if hist is not None and hist > 0:
        score += 4
        notes.append("MACD柱为正")
    if hist is not None and prev_hist is not None and hist > prev_hist:
        score += 4
        notes.append("MACD动能改善")
    if rsi is not None:
        if 45 <= rsi <= 70:
            score += 4
            notes.append(f"RSI处于健康区间 {rsi:.1f}")
        elif 35 <= rsi < 45 or 70 < rsi <= 78:
            score += 2
            notes.append(f"RSI临界 {rsi:.1f}")
    if _gt(k, d):
        score += 3
        notes.append("KDJ短线偏多")
    if ret5 is not None and ret5 > 0:
        score += 2
        notes.append(f"5日收益{ret5:+.2f}%")
    return _dimension("动量强弱", score, 20, notes)


def _score_volume(context: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    notes: list[str] = []
    ratio5 = context.get("volume_ratio_5")
    ratio20 = context.get("volume_ratio_20")
    if ratio5 is not None:
        if 1.1 <= ratio5 <= 2.5:
            score += 8
            notes.append(f"较5日均量放大 {ratio5:.2f}倍")
        elif ratio5 > 2.5:
            score += 4
            notes.append(f"明显放量 {ratio5:.2f}倍，需防冲高回落")
        elif 0.8 <= ratio5 < 1.1:
            score += 4
            notes.append(f"量能接近5日均量 {ratio5:.2f}倍")
    if ratio20 is not None and ratio20 >= 1:
        score += 3
        notes.append(f"量能高于20日均量 {ratio20:.2f}倍")
    if context.get("price_up") and ratio5 is not None and ratio5 > 1:
        score += 4
        notes.append("价涨量增")
    return _dimension("量能配合", score, 15, notes)


def _score_position(context: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    notes: list[str] = []
    boll_percent = context.get("boll_percent")
    close = context.get("close")
    boll_mid = context.get("boll_mid")
    support_distance = _distance_pct(close, context.get("support"))
    resistance_distance = _upside_pct(close, context.get("resistance"))
    if boll_percent is not None:
        if 0.2 <= boll_percent <= 0.8:
            score += 7
            notes.append(f"BOLL位置适中 {boll_percent:.2f}")
        elif 0.8 < boll_percent <= 1.0:
            score += 4
            notes.append(f"接近BOLL上轨 {boll_percent:.2f}")
        elif 0 <= boll_percent < 0.2:
            score += 3
            notes.append(f"靠近BOLL下沿 {boll_percent:.2f}")
    if support_distance is not None and 0 <= support_distance <= 8:
        score += 5
        notes.append(f"距支撑约{support_distance:.2f}%")
    if resistance_distance is not None:
        if resistance_distance >= 5:
            score += 4
            notes.append(f"上方空间约{resistance_distance:.2f}%")
        elif resistance_distance >= 2:
            score += 2
            notes.append(f"距离压力约{resistance_distance:.2f}%")
    if _gt(close, boll_mid):
        score += 4
        notes.append("价格位于BOLL中轨上方")
    return _dimension("位置结构", score, 20, notes)


def _score_risk(context: dict[str, Any]) -> dict[str, Any]:
    score = 15.0
    notes: list[str] = ["默认风险分满分起算"]
    rsi = context.get("rsi_6")
    boll_percent = context.get("boll_percent")
    volatility = context.get("volatility_20d_pct")
    drawdown = context.get("drawdown_20d_pct")
    close = context.get("close")
    ma20 = context.get("ma20")
    ratio5 = context.get("volume_ratio_5")
    if rsi is not None and rsi > 80:
        score -= 4
        notes.append(f"RSI过热 {rsi:.1f}")
    if boll_percent is not None and boll_percent > 1.05:
        score -= 4
        notes.append("价格突破BOLL上轨较多")
    if volatility is not None and volatility > 4.5:
        score -= 3
        notes.append(f"20日波动偏高 {volatility:.2f}%")
    if drawdown is not None and drawdown < -15:
        score -= 2
        notes.append(f"距20日高点回撤 {drawdown:.2f}%")
    if close is not None and ma20 is not None and close < ma20:
        score -= 3
        notes.append("价格低于MA20")
    if ratio5 is not None and ratio5 > 3:
        score -= 2
        notes.append("异常放量")
    return _dimension("风险控制", score, 15, notes)


def _evaluate_similar_patterns(
    frame: pd.DataFrame,
    current_state: dict[str, str],
    horizons: tuple[int, ...],
    *,
    min_samples: int,
) -> dict[str, Any]:
    if len(frame) < MIN_PATTERN_HISTORY or not horizons:
        return {
            "status": "insufficient_history",
            "sample_count": 0,
            "min_samples": min_samples,
            "match_rule": "趋势+RSI+BOLL+量能",
            "horizons": [],
        }
    max_horizon = max(horizons)
    strict_raw_matches = _pattern_matches(frame, current_state, max_horizon, include_volume=True)
    strict_matches = _select_non_overlapping_matches(strict_raw_matches, max_horizon)
    raw_matches = strict_raw_matches
    matches = strict_matches
    match_rule = "趋势+RSI+BOLL+量能"
    if len(matches) < min_samples:
        raw_matches = _pattern_matches(frame, current_state, max_horizon, include_volume=False)
        matches = _select_non_overlapping_matches(raw_matches, max_horizon)
        match_rule = "趋势+RSI+BOLL"
    horizon_rows = []
    for horizon in horizons:
        returns = []
        for index in matches:
            current_close = _number(frame.iloc[index].get("close"))
            future_close = _number(frame.iloc[index + horizon].get("close")) if index + horizon < len(frame) else None
            if current_close and future_close:
                returns.append(round((future_close / current_close - 1) * 100, 2))
        win_rate = _win_rate(returns)
        ci_low, ci_high = _wilson_interval(returns)
        horizon_rows.append({
            "horizon": f"{horizon}d",
            "sample_count": len(returns),
            "win_rate_pct": win_rate,
            "win_rate_ci_low_pct": ci_low,
            "win_rate_ci_high_pct": ci_high,
            "avg_return_pct": _avg(returns),
            "best_return_pct": round(max(returns), 2) if returns else None,
            "worst_return_pct": round(min(returns), 2) if returns else None,
        })
    sample_count = len(matches)
    reliability = _sample_reliability(sample_count, min_samples)
    return {
        "status": "ok" if sample_count >= min_samples else "insufficient_samples",
        "sample_count": sample_count,
        "raw_sample_count": len(raw_matches),
        "min_samples": min_samples,
        "match_rule": match_rule,
        "sample_method": "non_overlapping_forward_windows",
        "reliability": reliability,
        "current_state": current_state,
        "horizons": horizon_rows,
    }


def _pattern_matches(
    frame: pd.DataFrame,
    current_state: dict[str, str],
    max_horizon: int,
    *,
    include_volume: bool,
) -> list[int]:
    matches = []
    end = len(frame) - max_horizon - 1
    if end <= 60:
        return matches
    for index in range(60, end):
        row = frame.iloc[index]
        volume_ratio = _volume_ratio_at(frame, index, 5)
        state = _pattern_state(row, volume_ratio_5=volume_ratio)
        keys = ("trend", "rsi", "boll", "volume") if include_volume else ("trend", "rsi", "boll")
        if all(state.get(key) == current_state.get(key) for key in keys):
            matches.append(index)
    return matches


def _select_non_overlapping_matches(matches: list[int], max_horizon: int) -> list[int]:
    selected = []
    next_allowed = -1
    gap = max(1, int(max_horizon))
    for index in sorted(set(matches)):
        if index < next_allowed:
            continue
        selected.append(index)
        next_allowed = index + gap
    return selected


def _sample_reliability(sample_count: int, min_samples: int) -> dict[str, Any]:
    if sample_count < min_samples:
        return {"level": "insufficient", "label": "样本不足", "is_reliable": False}
    if sample_count < 12:
        return {"level": "low", "label": "低", "is_reliable": False}
    if sample_count < 30:
        return {"level": "medium", "label": "中", "is_reliable": False}
    return {"level": "high", "label": "高", "is_reliable": True}


def _pattern_state(row: pd.Series, *, volume_ratio_5: float | None) -> dict[str, str]:
    close = _number(row.get("close"))
    ma5 = _number(row.get("ma5"))
    ma10 = _number(row.get("ma10"))
    ma20 = _number(row.get("ma20"))
    rsi = _number(row.get("rsi_6") if row.get("rsi_6") is not None else row.get("rsi"))
    boll_percent = _number(row.get("boll_percent"))
    if _gt(ma5, ma10) and _gt(ma10, ma20) and _gt(close, ma20):
        trend = "bullish"
    elif _gt(ma20, ma10) and _gt(ma10, ma5) and close is not None and ma20 is not None and close < ma20:
        trend = "bearish"
    else:
        trend = "mixed"
    if rsi is None:
        rsi_bucket = "missing"
    elif rsi < 35:
        rsi_bucket = "oversold"
    elif rsi < 50:
        rsi_bucket = "weak"
    elif rsi <= 65:
        rsi_bucket = "healthy"
    elif rsi <= 75:
        rsi_bucket = "strong"
    else:
        rsi_bucket = "overheat"
    if boll_percent is None:
        boll_bucket = "missing"
    elif boll_percent < 0.2:
        boll_bucket = "lower"
    elif boll_percent <= 0.8:
        boll_bucket = "middle"
    elif boll_percent <= 1.05:
        boll_bucket = "upper"
    else:
        boll_bucket = "above_upper"
    if volume_ratio_5 is None:
        volume_bucket = "missing"
    elif volume_ratio_5 >= 1.8:
        volume_bucket = "high"
    elif volume_ratio_5 >= 1.1:
        volume_bucket = "rising"
    elif volume_ratio_5 <= 0.7:
        volume_bucket = "low"
    else:
        volume_bucket = "normal"
    return {
        "trend": trend,
        "rsi": rsi_bucket,
        "boll": boll_bucket,
        "volume": volume_bucket,
    }


def _risk_flags(context: dict[str, Any]) -> list[str]:
    flags = []
    rsi = context.get("rsi_6")
    boll_percent = context.get("boll_percent")
    ratio5 = context.get("volume_ratio_5")
    volatility = context.get("volatility_20d_pct")
    close = context.get("close")
    ma20 = context.get("ma20")
    resistance_distance = _upside_pct(close, context.get("resistance"))
    if rsi is not None and rsi > 80:
        flags.append("RSI过热")
    if boll_percent is not None and boll_percent > 1.05:
        flags.append("价格明显高于BOLL上轨")
    if ratio5 is not None and ratio5 > 3:
        flags.append("异常放量")
    if volatility is not None and volatility > 4.5:
        flags.append("波动偏高")
    if close is not None and ma20 is not None and close < ma20:
        flags.append("跌破MA20")
    if resistance_distance is not None and 0 <= resistance_distance < 2:
        flags.append("距离上方压力较近")
    return flags


def _dimension(name: str, score: float, max_score: int, notes: list[str]) -> dict[str, Any]:
    score = round(max(0.0, min(float(max_score), score)), 1)
    ratio = score / max_score if max_score else 0
    if ratio >= 0.75:
        level = "强"
    elif ratio >= 0.55:
        level = "中上"
    elif ratio >= 0.35:
        level = "中性"
    else:
        level = "弱"
    return {
        "name": name,
        "score": score,
        "max_score": max_score,
        "level": level,
        "notes": notes[:5],
    }


def _rating(score: float) -> str:
    if score >= 80:
        return "强势"
    if score >= 65:
        return "偏强"
    if score >= 50:
        return "中性"
    if score >= 35:
        return "偏弱"
    return "弱势"


def _action_hint(score: float, risk_flags: list[str]) -> str:
    if score >= 70 and len(risk_flags) <= 1:
        return "可重点观察"
    if score >= 55:
        return "观察等待确认"
    if score >= 40:
        return "谨慎观察"
    return "暂不适合追入"


def _volume_ratio(frame: pd.DataFrame, window: int) -> float | None:
    return _volume_ratio_at(frame, len(frame) - 1, window)


def _volume_ratio_at(frame: pd.DataFrame, index: int, window: int) -> float | None:
    if "volume" not in frame.columns or index <= 0:
        return None
    current = _number(frame.iloc[index].get("volume"))
    start = max(0, index - window)
    base = pd.to_numeric(frame.iloc[start:index]["volume"], errors="coerce").dropna()
    if current is None or base.empty:
        return None
    avg_volume = float(base.mean())
    if avg_volume <= 0:
        return None
    return round(current / avg_volume, 2)


def _lookback_return(frame: pd.DataFrame, days: int) -> float | None:
    if len(frame) <= days:
        return None
    current = _number(frame.iloc[-1].get("close"))
    base = _number(frame.iloc[-days - 1].get("close"))
    if current is None or base is None or base <= 0:
        return None
    return round((current / base - 1) * 100, 2)


def _volatility_pct(frame: pd.DataFrame, days: int) -> float | None:
    if "close" not in frame.columns or len(frame) < days + 1:
        return None
    returns = pd.to_numeric(frame["close"], errors="coerce").pct_change().tail(days).dropna()
    if returns.empty:
        return None
    return round(float(returns.std()) * 100, 2)


def _drawdown_pct(close: float | None, recent_high: float | None) -> float | None:
    if close is None or recent_high is None or recent_high <= 0:
        return None
    return round((close / recent_high - 1) * 100, 2)


def _distance_pct(price: float | None, level: float | None) -> float | None:
    if price is None or level is None or level <= 0:
        return None
    return round((price / level - 1) * 100, 2)


def _upside_pct(price: float | None, level: float | None) -> float | None:
    if price is None or level is None or price <= 0:
        return None
    return round((level / price - 1) * 100, 2)


def _nearest_below(price: float | None, levels: list[float | None]) -> float | None:
    if price is None:
        return None
    valid = [level for level in levels if level is not None and level <= price and level > 0]
    return round(max(valid), 2) if valid else None


def _nearest_above(price: float | None, levels: list[float | None]) -> float | None:
    if price is None:
        return None
    valid = [level for level in levels if level is not None and level >= price and level > 0]
    return round(min(valid), 2) if valid else None


def _series_max(series: Any) -> float | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    return round(float(values.max()), 2) if not values.empty else None


def _series_min(series: Any) -> float | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    return round(float(values.min()), 2) if not values.empty else None


def _avg(values: list[float]) -> float | None:
    valid = [_number(value) for value in values]
    valid = [value for value in valid if value is not None]
    return round(sum(valid) / len(valid), 2) if valid else None


def _win_rate(values: list[float]) -> float | None:
    valid = [_number(value) for value in values]
    valid = [value for value in valid if value is not None]
    return round(sum(1 for value in valid if value > 0) / len(valid) * 100, 2) if valid else None


def _wilson_interval(values: list[float], z: float = 1.96) -> tuple[float | None, float | None]:
    valid = [_number(value) for value in values]
    valid = [value for value in valid if value is not None]
    if not valid:
        return None, None
    total = len(valid)
    proportion = sum(1 for value in valid if value > 0) / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * sqrt((proportion * (1 - proportion) / total) + (z * z / (4 * total * total)))
        / denominator
    )
    return round(max(0.0, center - margin) * 100, 2), round(min(1.0, center + margin) * 100, 2)


def _gt(left: Any, right: Any) -> bool:
    left_num = _number(left)
    right_num = _number(right)
    return left_num is not None and right_num is not None and left_num > right_num


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None
