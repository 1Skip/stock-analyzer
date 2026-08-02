"""Read-only system status page."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from data.runtime import run_with_timeout
from quality_monitor import run_data_source_health_check
from scripts.inspect_cache_status import DEFAULT_CACHE_DIRS, inspect_cache_dirs
from ui.scheduler_status import load_scheduler_status, render_scheduler_status

CACHE_STALE_MINUTES = 24 * 60
DATA_SOURCE_HEALTH_SESSION_KEY = "system_data_source_health"
DATA_SOURCE_HEALTH_TIMEOUT_SECONDS = 30


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
        for section_name in (
            "daily_report",
            "scheduled_analysis",
            "t1_preheat",
            "paper_trading",
            "broker_reconciliation",
            "portfolio_backtest",
        ):
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


def run_system_data_source_health_check() -> dict[str, Any]:
    """Run explicit real-source checks without generating recommendations."""
    try:
        return run_with_timeout(run_data_source_health_check, DATA_SOURCE_HEALTH_TIMEOUT_SECONDS)
    except Exception as exc:
        return {
            "status": "failed",
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "ok_count": 0,
            "total": 0,
            "checks": [],
            "error": str(exc)[:160],
        }


def build_data_source_health_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for item in (result or {}).get("checks") or []:
        rows.append({
            "检测项": item.get("name") or "--",
            "状态": {"ok": "可用", "empty": "返回为空", "failed": "失败"}.get(item.get("status"), "未知"),
            "耗时(ms)": item.get("elapsed_ms"),
            "说明": item.get("message") or "--",
        })
    return rows


def render_data_source_health_status() -> None:
    st.markdown("#### 数据源状态")
    if st.button("检测数据源", key="system_run_data_source_health"):
        st.session_state[DATA_SOURCE_HEALTH_SESSION_KEY] = run_system_data_source_health_check()

    result = st.session_state.get(DATA_SOURCE_HEALTH_SESSION_KEY)
    if not isinstance(result, dict):
        st.caption("尚未检测。点击按钮后会抽样检查真实公开数据源，不生成推荐计划。")
        return

    status = result.get("status")
    summary = f"{result.get('ok_count', 0)}/{result.get('total', 0)} 项可用"
    if status == "ok":
        st.success(f"数据源检测通过：{summary}")
    elif status == "partial":
        st.warning(f"数据源部分可用：{summary}")
    else:
        st.error(f"数据源检测失败：{result.get('error') or summary}")
    if result.get("checked_at"):
        st.caption(f"检测时间：{result['checked_at']}")
    rows = build_data_source_health_rows(result)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_system_status_page() -> None:
    """Render scheduler, cache and explicit data-source diagnostics."""
    st.markdown("# 系统状态")
    st.caption("诊断页：展示调度、T+1 和本地缓存；数据源检测仅在点击按钮后运行，不生成推荐。")

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

    render_data_source_health_status()
    st.markdown("#### 缓存状态")
    if not rows:
        st.caption("暂无缓存文件。")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


