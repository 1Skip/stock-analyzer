"""Text-only catalyst classification helpers for recommendation context."""
from __future__ import annotations

from typing import Any

import pandas as pd


POSITIVE_CATALYST_KEYWORDS = ["政策", "订单", "业绩", "回购", "增持", "合同", "机构覆盖"]
RISK_CATALYST_KEYWORDS = ["减持", "处罚", "诉讼", "亏损", "退市风险"]


def recent_items(items: list[dict[str, Any]] | None, days: int = 2) -> list[dict[str, Any]]:
    if not items:
        return []
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    recent = []
    for item in items:
        raw_date = item.get("date") or item.get("announcement_date") or item.get("time")
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if pd.notna(parsed) and getattr(parsed, "tzinfo", None) is not None:
            parsed = parsed.tz_localize(None)
        if pd.notna(parsed) and parsed.normalize() >= cutoff:
            recent.append(item)
    return recent


def classify_catalyst_item(item: dict[str, Any]) -> tuple[str, list[str]]:
    text = " ".join(str(item.get(key) or "") for key in ("title", "summary", "type", "rating"))
    risk_hits = [keyword for keyword in RISK_CATALYST_KEYWORDS if keyword in text]
    positive_hits = [keyword for keyword in POSITIVE_CATALYST_KEYWORDS if keyword in text]
    if risk_hits:
        return "风险", risk_hits
    if positive_hits:
        return "偏利好", positive_hits
    return "中性", []


def format_catalyst_item(item: dict[str, Any]) -> str:
    title = str(item.get("title") or item.get("summary") or "").strip()
    if not title:
        return ""
    date = str(item.get("date") or item.get("announcement_date") or item.get("time") or "").strip()
    source = str(item.get("source") or item.get("org") or item.get("type") or "").strip()
    sentiment, keywords = classify_catalyst_item(item)
    prefix = f"{date} " if date else ""
    suffix_parts = [part for part in [source, sentiment, "/".join(keywords)] if part]
    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
    return f"{prefix}{title}{suffix}"
