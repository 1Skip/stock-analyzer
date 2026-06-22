"""Short-term recommendation learning from real T+1 plan outcomes."""
from __future__ import annotations

from typing import Any

from data.cache import JsonFileCache


MIN_COMPLETED_SAMPLES = 12
SCORE_BUCKET_SIZE = 5
MAX_LEARNING_BONUS = 6.0

_OUTCOME_CACHE = JsonFileCache("short_term_learning_outcomes", 86400 * 365)


def build_short_term_learning_profile(
    rows: list[dict[str, Any]] | None,
    *,
    quote_service: Any,
    evaluate_plan_outcomes: Any,
) -> dict[str, Any]:
    """Build a read-only short-term learning profile from completed outcomes."""
    samples = _collect_completed_short_term_samples(rows, quote_service, evaluate_plan_outcomes)
    profile: dict[str, Any] = {
        "version": "short_term_learning_v1",
        "strategy": "短线",
        "sample_count": len(samples),
        "min_samples": MIN_COMPLETED_SAMPLES,
        "status": "insufficient_samples",
        "score_threshold": None,
        "bucket_stats": [],
        "baseline_avg_1d_return_pct": None,
        "baseline_win_rate_1d_pct": None,
        "note": "短线真实回测完成样本不足，暂不启用动态评分门槛。",
    }
    if not samples:
        return profile

    returns = [sample["return_1d"] for sample in samples]
    profile["baseline_avg_1d_return_pct"] = _avg(returns)
    profile["baseline_win_rate_1d_pct"] = _win_rate(returns)
    bucket_stats = _bucket_samples(samples)
    profile["bucket_stats"] = bucket_stats
    if len(samples) < MIN_COMPLETED_SAMPLES:
        return profile

    threshold = _choose_score_threshold(bucket_stats)
    if threshold is None:
        profile["note"] = "短线真实回测样本已积累，但未发现优于基准的稳定分数段，暂不启用动态评分门槛。"
        return profile
    profile["status"] = "active"
    profile["score_threshold"] = threshold
    profile["note"] = f"短线动态门槛来自真实 T+1 历史回测：score >= {threshold}。"
    return profile


def apply_short_term_learning(
    recommended: list[dict[str, Any]] | None,
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Attach learning fields and use real backtest data as ranking aid, not hard filter."""
    items = [
        dict(item)
        for item in (recommended or [])
        if not _is_star_market_symbol((item or {}).get("symbol"))
    ]
    if not items:
        return []
    profile = profile if isinstance(profile, dict) else {}
    active = profile.get("status") == "active" and profile.get("score_threshold") is not None
    threshold = _safe_float(profile.get("score_threshold"))
    baseline = _safe_float(profile.get("baseline_avg_1d_return_pct")) or 0.0
    bucket_stats = profile.get("bucket_stats") if isinstance(profile.get("bucket_stats"), list) else []
    learned = []
    for item in items:
        score = _safe_float(item.get("score"))
        bucket = _find_bucket_stat(score, bucket_stats)
        bonus = _learning_bonus(bucket, baseline) if active else 0.0
        learned_alpha = _safe_float(item.get("alpha_score"))
        if learned_alpha is not None:
            learned_alpha = round(max(0.0, min(100.0, learned_alpha + bonus)), 1)
        item["learning_profile_version"] = profile.get("version") or "short_term_learning_v1"
        item["learning_status"] = profile.get("status") or "insufficient_samples"
        item["learning_bonus"] = bonus
        item["learned_alpha_score"] = learned_alpha
        item["learning_reason"] = _learning_reason(profile, bucket, bonus)
        item["learning_score_threshold"] = threshold if active else None
        below_threshold = active and score is not None and threshold is not None and score < threshold
        item["learning_below_threshold"] = bool(below_threshold)
        item["learning_threshold_note"] = (
            f"真实回测参考线 score >= {threshold}，当前 {score:.1f}；仅影响排序，不剔除。"
            if below_threshold else ""
        )
        item["learning_filtered"] = False
        learned.append(item)
    if active:
        learned.sort(
            key=lambda item: (
                _safe_float(item.get("learned_alpha_score")) if item.get("learned_alpha_score") is not None else -1,
                _safe_float(item.get("alpha_score")) if item.get("alpha_score") is not None else -1,
                _safe_float(item.get("score")) if item.get("score") is not None else -1,
            ),
            reverse=True,
        )
    return learned


def _collect_completed_short_term_samples(rows: list[dict[str, Any]] | None, quote_service: Any, evaluate_plan_outcomes: Any) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows or []:
        plan = row.get("plan") if isinstance(row, dict) else None
        if not isinstance(plan, dict) or plan.get("strategy") != "短线":
            continue
        plan_key = f"{plan.get('generated_at')}:{plan.get('sector') or '全部'}"
        cached = _OUTCOME_CACHE.get(plan_key)
        if cached is not None and isinstance(cached, list):
            for sample in cached:
                samples.append(dict(sample))
            continue
        outcome = evaluate_plan_outcomes(plan, quote_service=quote_service, horizons=(1,))
        plan_samples: list[dict[str, Any]] = []
        for item in outcome.get("items") or []:
            if item.get("status") != "completed":
                continue
            return_1d = _safe_float((item.get("returns") or {}).get("1d"))
            if return_1d is None:
                continue
            stock = _find_plan_stock(plan, item.get("symbol"))
            score = _safe_float(stock.get("score")) if isinstance(stock, dict) else None
            if score is None:
                continue
            sample = {
                "symbol": item.get("symbol"),
                "score": score,
                "return_1d": return_1d,
                "sector": plan.get("sector") or "全部",
            }
            plan_samples.append(sample)
            samples.append(sample)
        if plan_samples:
            _OUTCOME_CACHE.set(plan_key, plan_samples)
    return samples
def _bucket_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[float]] = {}
    for sample in samples:
        score = _safe_float(sample.get("score"))
        ret = _safe_float(sample.get("return_1d"))
        if score is None or ret is None:
            continue
        floor = int(score // SCORE_BUCKET_SIZE) * SCORE_BUCKET_SIZE
        buckets.setdefault(floor, []).append(ret)
    rows = []
    for floor, returns in sorted(buckets.items()):
        rows.append({
            "score_min": floor,
            "score_max": floor + SCORE_BUCKET_SIZE - 0.1,
            "sample_count": len(returns),
            "avg_1d_return_pct": _avg(returns),
            "win_rate_1d_pct": _win_rate(returns),
        })
    return rows


def _choose_score_threshold(bucket_stats: list[dict[str, Any]]) -> float | None:
    eligible = [
        bucket for bucket in bucket_stats
        if int(bucket.get("sample_count") or 0) >= 3
        and (_safe_float(bucket.get("avg_1d_return_pct")) or 0) > 0
        and (_safe_float(bucket.get("win_rate_1d_pct")) or 0) >= 50
    ]
    if not eligible:
        return None
    return float(min(bucket["score_min"] for bucket in eligible))


def _learning_bonus(bucket: dict[str, Any] | None, baseline: float) -> float:
    if not bucket:
        return 0.0
    avg_return = _safe_float(bucket.get("avg_1d_return_pct"))
    win_rate = _safe_float(bucket.get("win_rate_1d_pct"))
    if avg_return is None or win_rate is None:
        return 0.0
    raw = (avg_return - baseline) * 1.5 + (win_rate - 50.0) / 12.0
    return round(max(-MAX_LEARNING_BONUS, min(MAX_LEARNING_BONUS, raw)), 1)


def _learning_reason(profile: dict[str, Any], bucket: dict[str, Any] | None, bonus: float) -> str:
    if profile.get("status") != "active":
        return str(profile.get("note") or "短线真实回测样本不足，暂不启用动态学习。")
    if not bucket:
        return "当前分数段暂无足够真实回测样本，学习加权为 0。"
    direction = "加分" if bonus > 0 else "扣分" if bonus < 0 else "中性"
    return (
        f"真实回测分数段 {bucket.get('score_min')}-{bucket.get('score_max')}："
        f"{bucket.get('sample_count')} 个样本，1日均收益 {bucket.get('avg_1d_return_pct')}%，"
        f"胜率 {bucket.get('win_rate_1d_pct')}%，学习{direction} {bonus:+.1f}。"
    )


def _find_bucket_stat(score: float | None, bucket_stats: list[dict[str, Any]]) -> dict[str, Any] | None:
    if score is None:
        return None
    for bucket in bucket_stats:
        low = _safe_float(bucket.get("score_min"))
        high = _safe_float(bucket.get("score_max"))
        if low is not None and high is not None and low <= score <= high:
            return bucket
    return None


def _find_plan_stock(plan: dict[str, Any], symbol: Any) -> dict[str, Any] | None:
    symbol_text = str(symbol or "")
    for stock in plan.get("recommended") or []:
        if str((stock or {}).get("symbol") or "") == symbol_text:
            return stock
    return None


def _is_star_market_symbol(symbol: Any) -> bool:
    return str(symbol or "").strip().startswith(("688", "689"))


def _avg(values: list[float]) -> float | None:
    valid = [_safe_float(value) for value in values if _safe_float(value) is not None]
    return round(sum(valid) / len(valid), 2) if valid else None


def _win_rate(values: list[float]) -> float | None:
    valid = [_safe_float(value) for value in values if _safe_float(value) is not None]
    return round(sum(1 for value in valid if value > 0) / len(valid) * 100, 2) if valid else None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None
