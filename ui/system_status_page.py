"""Read-only system status page."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from scripts.inspect_cache_status import DEFAULT_CACHE_DIRS, inspect_cache_dirs
from ui.scheduler_status import load_scheduler_status, render_scheduler_status

CACHE_STALE_MINUTES = 24 * 60


def _format_size(size_bytes: Any) -> str:
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return "--"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{int(size)} B"


def _age_minutes(modified_at: Any) -> float | None:
    if not modified_at:
        return None
    try:
        modified = datetime.fromisoformat(str(modified_at))
    except ValueError:
        return None
    return round((datetime.now() - modified).total_seconds() / 60, 1)


def build_cache_status_rows(paths: list[Path] | None = None) -> list[dict[str, Any]]:
    rows = []
    for item in inspect_cache_dirs(paths or DEFAULT_CACHE_DIRS):
        row = dict(item)
        row["size"] = _format_size(row.get("size_bytes"))
        age = _age_minutes(row.get("modified_at"))
        row["age_minutes"] = age
        if row.get("status") != "ok":
            row["freshness"] = row.get("status")
        elif age is None:
            row["freshness"] = "unknown"
        elif age > CACHE_STALE_MINUTES:
            row["freshness"] = "stale"
        else:
            row["freshness"] = "fresh"
        rows.append(row)
    return rows


def summarize_scheduler_failures(status: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for section_name, section in status.items():
        if not isinstance(section, dict):
            continue
        reason = section.get("error") or section.get("reason")
        if reason:
            failures.append(f"{section_name}: {reason}")
        targets = section.get("targets") if isinstance(section.get("targets"), dict) else {}
        for key, target in targets.items():
            if not isinstance(target, dict):
                continue
            target_reason = target.get("error") or target.get("reason")
            if target_reason:
                failures.append(f"{section_name}/{key}: {target_reason}")
    return failures


def render_system_status_page() -> None:
    """Render local scheduler and cache status without mutating project state."""
    st.markdown("# 系统状态")
    st.caption("只读诊断页：展示调度、T+1 和本地缓存状态，不触发推荐生成或行情刷新。")

    status = load_scheduler_status()
    render_scheduler_status(status)
    if not status:
        st.caption("暂无调度状态文件。")
    else:
        failures = summarize_scheduler_failures(status)
        if failures:
            st.warning("最近调度失败原因：" + "；".join(failures[:5]))

    st.markdown("#### 缓存状态")
    rows = build_cache_status_rows()
    if not rows:
        st.caption("暂无缓存文件。")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


