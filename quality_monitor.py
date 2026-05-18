"""Observability, explanation, and outcome helpers for recommendations.

These helpers deliberately sit beside the strategy code. They add metadata and
diagnostics without changing which stocks are selected or how they are ranked.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import (
    CACHE_TTL_RECOMMENDATION_RESULTS,
    CACHE_TTL_STOCK_EXTENDED_INFO,
    CACHE_TTL_STRATEGY_KLINE,
    RUNTIME_CACHE_DIR,
)


_REQUIRED_STOCK_FIELDS = ("symbol", "name", "score", "rating", "latest_price", "indicators", "signals")
_INDICATOR_FIELDS = ("macd", "macd_signal", "macd_hist", "rsi_6", "rsi_12", "rsi_24", "kdj_k", "kdj_d", "kdj_j")


def build_runtime_diagnostics() -> dict[str, Any]:
    """Return local runtime/cache health that can be shown in settings."""
    cache_dir = Path(RUNTIME_CACHE_DIR)
    cache_files = _cache_file_summary(cache_dir)
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "cache_dir": str(cache_dir),
        "cache_dir_exists": cache_dir.exists(),
        "cache_files": cache_files,
        "cache_total_bytes": sum(item["size_bytes"] for item in cache_files),
        "ttl": {
            "recommendation_results_seconds": CACHE_TTL_RECOMMENDATION_RESULTS,
            "strategy_kline_seconds": CACHE_TTL_STRATEGY_KLINE,
            "stock_extended_info_seconds": CACHE_TTL_STOCK_EXTENDED_INFO,
        },
        "env": {
            "stock_data_source": os.getenv("STOCK_DATA_SOURCE", "auto"),
            "recommend_ranker_enabled": os.getenv("RECOMMEND_RANKER_ENABLED", "true"),
            "recommend_ranker_sort": os.getenv("RECOMMEND_RANKER_SORT", "false"),
            "runtime_cache_dir": os.getenv("RUNTIME_CACHE_DIR", ""),
        },
    }


def summarize_recommendation_quality(recommended: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Summarize missing fields and explanation coverage for a recommendation run."""
    stocks = recommended or []
    field_missing: dict[str, int] = {}
    indicator_missing: dict[str, int] = {}
    risk_count = 0
    explainable_count = 0
    for stock in stocks:
        missing = _missing_required_fields(stock)
        for field in missing:
            field_missing[field] = field_missing.get(field, 0) + 1
        indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
        for field in _INDICATOR_FIELDS:
            if indicators.get(field) is None:
                indicator_missing[field] = indicator_missing.get(field, 0) + 1
        explanation = stock.get("explanation") if isinstance(stock.get("explanation"), dict) else {}
        if explanation.get("why_selected"):
            explainable_count += 1
        if explanation.get("risk_flags") or stock.get("rank_penalty"):
            risk_count += 1
    return {
        "stock_count": len(stocks),
        "explainable_count": explainable_count,
        "risk_flag_count": risk_count,
        "missing_required_fields": field_missing,
        "missing_indicator_fields": indicator_missing,
        "status": "ok" if not field_missing else "partial",
    }


def save_plan_history(history_cache: Any, plan: dict[str, Any]) -> str | None:
    """Persist a generated plan into a long-lived history cache."""
    if not isinstance(plan, dict):
        return None
    key = _history_key(plan)
    history_cache.set(key, plan)
    return key


def list_plan_history(
    history_cache: Any,
    *,
    strategy: str | None = None,
    sector: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read stored T+1 plans, newest first."""
    payload = _read_cache_payload(history_cache)
    rows = []
    for key, item in payload.items():
        value = item.get("value") if isinstance(item, dict) else None
        if not isinstance(value, dict):
            continue
        if strategy and value.get("strategy") != strategy:
            continue
        if sector and value.get("sector") != sector:
            continue
        rows.append({
            "history_key": key,
            "generated_at": value.get("generated_at") or item.get("updated_at"),
            "strategy": value.get("strategy"),
            "sector": value.get("sector"),
            "num_stocks": value.get("num_stocks"),
            "plan_for_trade_date": value.get("plan_for_trade_date"),
            "recommended_count": len(value.get("recommended") or []),
            "recommended_symbols": [stock.get("symbol") for stock in (value.get("recommended") or [])],
            "plan": value,
        })
    rows.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    return rows[: max(1, int(limit or 20))]


def summarize_history_outcomes(outcome_reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate read-only outcome reviews by strategy and sector."""
    buckets: dict[str, dict[str, Any]] = {}
    total_items = 0
    completed_items = 0
    all_1d_returns: list[float | None] = []
    for review in outcome_reviews:
        plan = review.get("plan") or {}
        result = review.get("outcome") or {}
        summary = result.get("summary") or {}
        strategy = plan.get("strategy") or "--"
        sector = plan.get("sector") or "--"
        key = f"{strategy}:{sector}"
        bucket = buckets.setdefault(
            key,
            {
                "strategy": strategy,
                "sector": sector,
                "plans": 0,
                "total": 0,
                "completed": 0,
                "returns_1d": [],
            },
        )
        bucket["plans"] += 1
        bucket["total"] += int(summary.get("total") or 0)
        bucket["completed"] += int(summary.get("completed") or 0)
        total_items += int(summary.get("total") or 0)
        completed_items += int(summary.get("completed") or 0)
        for item in result.get("items") or []:
            returns = item.get("returns") or {}
            value = returns.get("1d")
            if value is not None:
                bucket["returns_1d"].append(value)
                all_1d_returns.append(value)
    by_strategy = []
    for bucket in buckets.values():
        returns = bucket.pop("returns_1d")
        bucket["avg_1d_return_pct"] = _avg(returns)
        bucket["win_rate_1d_pct"] = _win_rate(returns)
        by_strategy.append(bucket)
    by_strategy.sort(key=lambda item: (str(item["strategy"]), str(item["sector"])))
    return {
        "plans": len(outcome_reviews),
        "total_items": total_items,
        "completed_items": completed_items,
        "avg_1d_return_pct": _avg(all_1d_returns),
        "win_rate_1d_pct": _win_rate(all_1d_returns),
        "by_strategy": by_strategy,
    }


def run_data_source_health_check(quote_service: Any | None = None, info_service: Any | None = None) -> dict[str, Any]:
    """Run explicit, user-triggered data checks with timing and no strategy side effects."""
    checked_at = datetime.now().isoformat(timespec="seconds")
    checks = []
    if quote_service is None:
        from data.services.quote_service import QuoteDataService

        quote_service = QuoteDataService()
    checks.append(_timed_check("历史K线", lambda: quote_service.get_stock_data("000001", period="1mo", market="CN")))
    checks.append(_timed_check("批量实时行情", lambda: quote_service.get_batch_realtime_quotes(["000001"], market="CN")))
    if info_service is None:
        try:
            from data.services.info_service import StockInfoService

            info_service = StockInfoService()
        except Exception:
            info_service = None
    if info_service is not None:
        checks.append(
            _timed_check(
                "扩展信息缓存",
                lambda: info_service.get_cached_stock_extended_info("000001", market="CN", include_deep_layers=False),
            )
        )
    ok_count = sum(1 for item in checks if item.get("status") == "ok")
    return {
        "checked_at": checked_at,
        "status": "ok" if ok_count == len(checks) else "partial" if ok_count else "failed",
        "ok_count": ok_count,
        "total": len(checks),
        "checks": checks,
    }


def build_stock_data_quality_summary(
    data: Any,
    quote: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    extended_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize single-stock data completeness for display only."""
    issues = []
    warnings = []
    data_len = len(data) if data is not None and not getattr(data, "empty", True) else 0
    if data_len < 60:
        warnings.append(f"历史K线仅 {data_len} 条，长周期指标参考价值下降")
    if not quote:
        issues.append("实时行情缺失，当前价可能使用K线兜底")
    if not isinstance(profile, dict) or profile.get("loading"):
        warnings.append("基础资料/估值暂未完整返回")
    else:
        for field, label in (("market_cap", "市值"), ("pe_ttm", "PE"), ("pb", "PB")):
            if profile.get(field) in (None, "", {}):
                warnings.append(f"{label}缺失")
    extended_info = extended_info if isinstance(extended_info, dict) else {}
    if not extended_info or extended_info.get("loading"):
        warnings.append("财务/资金/新闻扩展信息暂未完整返回")
    else:
        if not extended_info.get("financial"):
            warnings.append("财务摘要缺失")
        if not extended_info.get("fund_flow"):
            warnings.append("资金流缺失")
        risk_events = extended_info.get("risk_events") if isinstance(extended_info.get("risk_events"), dict) else {}
        announcements = risk_events.get("announcements") or []
        risky = _risky_announcements(announcements)
        if risky:
            issues.append(f"发现风险公告 {len(risky)} 条")
    return {
        "data_rows": data_len,
        "issues": _dedupe(issues),
        "warnings": _dedupe(warnings),
        "status": "risk" if issues else "partial" if warnings else "ok",
    }


def build_compare_scorecard(metrics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build a read-only cross-stock scorecard from comparison metrics."""
    metrics = metrics or []
    rows = []
    for item in metrics:
        score = 50
        notes = []
        ret20 = _safe_float(item.get("return_20d"))
        ret60 = _safe_float(item.get("return_60d"))
        drawdown = _safe_float(item.get("max_drawdown"))
        vol = _safe_float(item.get("volatility"))
        up_ratio = _safe_float(item.get("up_day_ratio"))
        slope = _safe_float(item.get("trend_slope_20d"))
        if ret20 is not None:
            score += 12 if ret20 > 5 else 6 if ret20 > 0 else -8
            notes.append(f"20日收益 {ret20:+.2f}%")
        if ret60 is not None:
            score += 10 if ret60 > 10 else 5 if ret60 > 0 else -6
        if drawdown is not None:
            score += 8 if drawdown > -10 else -8 if drawdown < -25 else 0
            notes.append(f"最大回撤 {drawdown:+.2f}%")
        if vol is not None:
            score += 5 if vol < 35 else -5 if vol > 65 else 0
        if up_ratio is not None:
            score += 5 if up_ratio > 55 else -3 if up_ratio < 45 else 0
        if slope is not None:
            score += 8 if slope > 0 else -5
        rows.append({
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "compare_score": round(max(0, min(100, score)), 1),
            "ma_status": item.get("ma_status"),
            "notes": _dedupe(notes)[:3],
        })
    rows.sort(key=lambda row: row["compare_score"], reverse=True)
    return rows


def build_backtest_risk_summary(results: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Summarize backtest loss cases and return distribution."""
    completed = [item for item in (results or []) if item.get("eval_status") == "completed"]
    losses = [item for item in completed if item.get("outcome") == "loss"]
    returns = [_safe_float(item.get("simulated_return_pct")) for item in completed]
    returns = [value for value in returns if value is not None]
    worst = sorted(
        completed,
        key=lambda item: _safe_float(item.get("simulated_return_pct")) if _safe_float(item.get("simulated_return_pct")) is not None else 999,
    )[:5]
    return {
        "completed": len(completed),
        "loss_count": len(losses),
        "avg_simulated_return_pct": _avg(returns),
        "best_simulated_return_pct": round(max(returns), 2) if returns else None,
        "worst_simulated_return_pct": round(min(returns), 2) if returns else None,
        "worst_cases": worst,
    }


def build_hot_data_status(data: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize hot page data coverage."""
    data = data or {}
    counts = {key: len(value or []) for key, value in data.items() if isinstance(value, list)}
    missing = [key for key, count in counts.items() if count == 0]
    return {
        "counts": counts,
        "missing": missing,
        "total_rows": sum(counts.values()),
        "status": "ok" if counts and not missing else "partial" if counts else "empty",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def attach_recommendation_explanations(
    recommended: list[dict[str, Any]] | None,
    *,
    strategy: str = "",
    sector: str = "",
) -> list[dict[str, Any]]:
    """Attach a compact explanation block to each stock."""
    items = []
    for stock in recommended or []:
        item = dict(stock)
        item["explanation"] = build_recommendation_explanation(item, strategy=strategy, sector=sector)
        items.append(item)
    return items


def build_recommendation_explanation(stock: dict[str, Any], *, strategy: str = "", sector: str = "") -> dict[str, Any]:
    """Explain why an already-selected stock is useful to review."""
    reasons = [str(item) for item in (stock.get("rank_reason") or []) if item]
    penalties = [str(item) for item in (stock.get("rank_penalty") or []) if item]
    details = stock.get("strategy_details") if isinstance(stock.get("strategy_details"), dict) else {}
    checks = stock.get("strategy_checks") if isinstance(stock.get("strategy_checks"), dict) else {}
    passed_checks = [str(key) for key, ok in checks.items() if ok]
    failed_checks = [str(key) for key, ok in checks.items() if not ok]

    for key in ("技术说明", "财务确认", "主力净流入趋势", "买入观察"):
        if details.get(key):
            reasons.append(str(details[key]))

    why_selected = _dedupe(reasons + [f"{strategy or stock.get('strategy') or '策略'}候选"] + passed_checks)[:5]
    risk_flags = _dedupe(penalties + failed_checks + _risk_flags_from_stock(stock))[:5]
    missing = _missing_required_fields(stock)
    missing.extend(_missing_optional_evidence(stock))

    return {
        "strategy": strategy or stock.get("strategy") or "",
        "sector": sector,
        "why_selected": why_selected,
        "risk_flags": risk_flags,
        "missing_data": _dedupe(missing)[:8],
        "entry_conditions": _entry_conditions(stock, details),
        "invalid_conditions": _invalid_conditions(stock, details, risk_flags),
        "confidence_note": _confidence_note(stock, risk_flags, missing),
    }


def evaluate_plan_outcomes(
    plan: dict[str, Any] | None,
    *,
    quote_service: Any,
    horizons: Iterable[int] = (1, 5, 20),
) -> dict[str, Any]:
    """Evaluate stored recommendation results against later K-line closes.

    The method is intentionally read-only. If future bars are not available yet,
    the item is marked as pending instead of inventing a result.
    """
    if not isinstance(plan, dict):
        return {"status": "no_plan", "items": [], "summary": {}}
    generated_date = str(plan.get("generated_trade_date") or plan.get("generated_at") or "")[:10]
    recommended = plan.get("recommended") or []
    items = []
    for stock in recommended:
        items.append(_evaluate_stock_outcome(stock, generated_date, quote_service=quote_service, horizons=tuple(horizons)))
    completed = [item for item in items if item.get("status") == "completed"]
    returns_1d = [item.get("returns", {}).get("1d") for item in completed if item.get("returns", {}).get("1d") is not None]
    summary = {
        "total": len(items),
        "completed": len(completed),
        "pending": len(items) - len(completed),
        "avg_1d_return_pct": _avg(returns_1d),
        "win_rate_1d_pct": _win_rate(returns_1d),
    }
    return {
        "status": "ok" if items else "empty",
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_trade_date": generated_date,
        "items": items,
        "summary": summary,
    }


def _evaluate_stock_outcome(
    stock: dict[str, Any],
    generated_date: str,
    *,
    quote_service: Any,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    symbol = str(stock.get("symbol") or "").strip()
    entry_price = _safe_float(stock.get("latest_price") or stock.get("price"))
    base = {
        "symbol": symbol,
        "name": stock.get("name") or symbol,
        "entry_price": entry_price,
        "generated_trade_date": generated_date,
    }
    if not symbol or not entry_price:
        return {**base, "status": "skipped", "reason": "缺少代码或计划价"}
    try:
        data = quote_service.get_stock_data(symbol, period="3mo", market="CN")
    except Exception as exc:
        return {**base, "status": "failed", "reason": str(exc)}
    if data is None or getattr(data, "empty", True):
        return {**base, "status": "pending", "reason": "暂无后续K线"}

    frame = data.copy()
    if "date" in frame.columns:
        frame["_date"] = frame["date"].astype(str).str[:10]
    else:
        frame["_date"] = frame.index.astype(str).str[:10]
    close_col = "close" if "close" in frame.columns else "Close" if "Close" in frame.columns else None
    if close_col is None:
        return {**base, "status": "failed", "reason": "K线缺少收盘价"}

    future = frame[frame["_date"] > generated_date] if generated_date else frame.tail(max(horizons))
    if len(future) < min(horizons):
        return {**base, "status": "pending", "reason": "等待未来交易日数据"}

    returns: dict[str, float | None] = {}
    for horizon in horizons:
        if len(future) < horizon:
            returns[f"{horizon}d"] = None
            continue
        close = _safe_float(future.iloc[horizon - 1][close_col])
        returns[f"{horizon}d"] = round((close / entry_price - 1) * 100, 2) if close is not None else None
    return {**base, "status": "completed", "returns": returns}


def _cache_file_summary(cache_dir: Path) -> list[dict[str, Any]]:
    if not cache_dir.exists():
        return []
    files = []
    for path in sorted(cache_dir.glob("*.json")):
        try:
            stat = path.stat()
            files.append({
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
        except OSError:
            continue
    return files


def _history_key(plan: dict[str, Any]) -> str:
    generated = str(plan.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    strategy = str(plan.get("strategy") or "strategy")
    sector = str(plan.get("sector") or "sector")
    num_stocks = str(plan.get("num_stocks") or 0)
    raw = f"{generated}:{strategy}:{sector}:{num_stocks}"
    return "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in raw)


def _read_cache_payload(cache: Any) -> dict[str, Any]:
    try:
        payload = cache._read()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        store = getattr(cache, "store", None)
        if isinstance(store, dict):
            return {
                str(key): {"updated_at": "", "value": value}
                for key, value in store.items()
            }
        return {}


def _timed_check(name: str, callback: Any) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    try:
        payload = callback()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ok = _payload_has_data(payload)
        return {
            "name": name,
            "status": "ok" if ok else "empty",
            "elapsed_ms": elapsed_ms,
            "message": "可用" if ok else "返回为空",
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "status": "failed",
            "elapsed_ms": elapsed_ms,
            "message": str(exc)[:120],
        }


def _payload_has_data(payload: Any) -> bool:
    if payload is None:
        return False
    if isinstance(payload, dict):
        return bool(payload)
    return not bool(getattr(payload, "empty", False))


def _missing_required_fields(stock: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_STOCK_FIELDS if stock.get(field) in (None, "", {})]


def _missing_optional_evidence(stock: dict[str, Any]) -> list[str]:
    missing = []
    if not isinstance(stock.get("extended_info"), dict):
        missing.append("extended_info")
    if not isinstance(stock.get("profile"), dict):
        missing.append("profile")
    if stock.get("alpha_score") is None:
        missing.append("alpha_score")
    return missing


def _risk_flags_from_stock(stock: dict[str, Any]) -> list[str]:
    flags = []
    change_pct = _safe_float(stock.get("change_pct"))
    if change_pct is not None and change_pct >= 5:
        flags.append("当日涨幅较高，注意追高")
    if change_pct is not None and change_pct <= -5:
        flags.append("当日走势偏弱")
    name = str(stock.get("name") or "").upper()
    if "ST" in name or "退" in name:
        flags.append("名称含 ST/退市风险标识")
    return flags


def _risky_announcements(announcements: list[Any]) -> list[Any]:
    risky_keywords = ("减持", "立案", "处罚", "风险", "诉讼", "亏损", "退市", "监管", "问询", "警示")
    risky = []
    for item in announcements or []:
        if isinstance(item, dict):
            text = " ".join(str(item.get(key) or "") for key in ("title", "type", "summary", "content"))
        else:
            text = str(item or "")
        if any(keyword in text for keyword in risky_keywords):
            risky.append(item)
    return risky


def _entry_conditions(stock: dict[str, Any], details: dict[str, Any]) -> list[str]:
    items = []
    if details.get("买入观察"):
        items.append(str(details["买入观察"]))
    indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
    ma20 = _safe_float(indicators.get("ma20"))
    boll_lower = _safe_float(indicators.get("boll_lower"))
    if ma20:
        items.append(f"回踩不破 MA20 {ma20:.2f}")
    if boll_lower:
        items.append(f"BOLL 下轨 {boll_lower:.2f} 上方企稳")
    if not items:
        items.append("等待分时企稳且不追高")
    return _dedupe(items)[:4]


def _invalid_conditions(stock: dict[str, Any], details: dict[str, Any], risk_flags: list[str]) -> list[str]:
    items = []
    if details.get("卖出纪律"):
        items.append(str(details["卖出纪律"]))
    if details.get("风险排除"):
        items.append(str(details["风险排除"]))
    items.extend(risk_flags)
    if not items:
        items.append("放量冲高后回落或跌破关键支撑")
    return _dedupe(items)[:4]


def _confidence_note(stock: dict[str, Any], risk_flags: list[str], missing: list[str]) -> str:
    alpha = _safe_float(stock.get("alpha_score"))
    if missing:
        return "证据不完整，需结合原始行情与公告复核。"
    if risk_flags:
        return "存在扣分或风险提示，适合观察而非追高。"
    if alpha is not None and alpha >= 75:
        return "策略分与解释证据较一致。"
    return "推荐成立，但仍需等待价格与成交量确认。"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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


def _avg(values: list[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def _win_rate(values: list[float | None]) -> float | None:
    nums = [float(value) for value in values if value is not None]
    if not nums:
        return None
    return round(sum(1 for value in nums if value > 0) / len(nums) * 100, 2)
