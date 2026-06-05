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
        row["diagnosis"] = diagnose_cache_row(row)
        rows.append(row)
    return rows


def diagnose_cache_row(row: dict[str, Any]) -> str:
    """Return a read-only human diagnosis for one cache row."""
    status = row.get("status")
    freshness = row.get("freshness")
    path = str(row.get("path") or "")
    if status == "missing":
        return "目录不存在：当前未生成该类缓存。"
    if status == "error":
        reason = row.get("reason") or "读取失败"
        return f"读取异常：{reason}"
    if freshness == "stale":
        return "缓存较旧：排查异常结果时优先确认是否命中旧缓存。"
    if path.endswith("scheduler_status.json"):
        return "调度状态缓存：用于判断最近日报/T+1 预热是否运行。"
    if "recommendation_t1" in path or "t1" in path.lower():
        return "T+1 计划缓存：读取不应重新扫描股票池。"
    if freshness == "fresh":
        return "缓存新鲜：通常可作为近期状态参考。"
    return "状态未知：需要结合文件内容或日志继续确认。"


def build_status_diagnostics(status: dict[str, Any], cache_rows: list[dict[str, Any]]) -> list[str]:
    """Build read-only diagnosis lines without triggering jobs or cache refreshes."""
    diagnostics: list[str] = []
    if not status:
        diagnostics.append("暂无调度状态文件：无法仅凭页面判断日报或 T+1 预热是否已运行。")
    else:
        for section_name in ("daily_report", "scheduled_analysis", "t1_preheat"):
            section = status.get(section_name)
            if not isinstance(section, dict):
                diagnostics.append(f"{section_name}: 暂无状态记录。")
                continue
            section_status = section.get("status") or "unknown"
            if section_status in {"failed", "partial_failed"}:
                reason = section.get("error") or section.get("reason") or "请查看目标明细或日志"
                diagnostics.append(f"{section_name}: 最近状态异常（{section_status}），原因：{reason}")
            elif section_status == "running":
                diagnostics.append(f"{section_name}: 当前记录为运行中，请结合更新时间确认是否卡住。")
            else:
                diagnostics.append(f"{section_name}: 最近状态 {section_status}。")

    stale_rows = [row for row in cache_rows if row.get("freshness") == "stale"]
    missing_rows = [row for row in cache_rows if row.get("status") == "missing"]
    if stale_rows:
        diagnostics.append(f"发现 {len(stale_rows)} 个较旧缓存：异常结果排查时应优先核对缓存日期。")
    if missing_rows:
        diagnostics.append(f"发现 {len(missing_rows)} 个缓存目录缺失：可能是尚未运行过对应任务。")
    return diagnostics


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
    rows = build_cache_status_rows()
    diagnostics = build_status_diagnostics(status, rows)
    if diagnostics:
        st.info("诊断结论：" + "；".join(diagnostics[:6]))
    if not status:
        st.caption("暂无调度状态文件。")
    else:
        failures = summarize_scheduler_failures(status)
        if failures:
            st.warning("最近调度失败原因：" + "；".join(failures[:5]))

    st.markdown("#### 缓存状态")
    if not rows:
        st.caption("暂无缓存文件。")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


