"""Non-strategy runtime helpers shared by recommendation orchestration."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def metric_value(metrics: dict[str, Any] | None, aliases: list[str]) -> float | None:
    for alias in aliases:
        for key, value in (metrics or {}).items():
            if alias == str(key) or alias in str(key):
                numeric = safe_float(value)
                if numeric is not None:
                    return numeric
    return None


def log_short_term_skip(symbol: str, reason: str, **details: Any) -> None:
    logger.debug(
        "短线分析跳过 symbol=%s reason=%s details=%s",
        symbol,
        reason,
        {key: value for key, value in details.items() if value is not None},
    )


def emit_progress(progress_callback: Any, stage: str, percent: int, **metrics: Any) -> None:
    if not callable(progress_callback):
        return
    try:
        progress_callback(stage, percent, metrics)
    except Exception:
        logger.debug("推荐进度回调失败: stage=%s", stage, exc_info=True)


def safe_extended_info_failure(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "financial": {},
        "fund_flow": {},
        "news": [],
        "market_news": [],
        "research": {"reports": [], "eps_consensus": {}},
        "risk_events": {"lhb": {}, "restricted_release": [], "announcements": []},
        "status": "source_failed",
        "reason": reason,
    }


def has_usable_extended_layer(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return value.get("status") not in {"source_failed", "source_empty"}


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if value is not None and not isinstance(value, (str, bytes, list, dict, tuple)):
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
    return value
