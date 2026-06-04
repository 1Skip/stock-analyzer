"""Read-only scheduler status UI helpers."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import streamlit as st


DEFAULT_STATUS_PATH = Path(".cache") / "scheduler_status.json"


def get_scheduler_status_path() -> Path:
    return Path(os.getenv("SCHEDULER_STATUS_PATH", str(DEFAULT_STATUS_PATH)))


def load_scheduler_status(path: Path | None = None) -> dict[str, Any]:
    path = path or get_scheduler_status_path()
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {"_read_error": str(path)}
    return payload if isinstance(payload, dict) else {}


def _fmt(value: Any, default: str = "--") -> str:
    if value in (None, ""):
        return default
    return html.escape(str(value))


def _target_rows(targets: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, value in targets.items():
        if not isinstance(value, dict):
            continue
        rows.append({
            "目标": key,
            "状态": value.get("status") or "--",
            "命中数": value.get("recommended_count", 0),
            "耗时": value.get("elapsed_seconds", "--"),
            "失败原因": value.get("error") or value.get("reason") or "",
        })
    return rows


def render_scheduler_status(status: dict[str, Any] | None = None) -> None:
    """Render latest scheduler/T+1 state without triggering recommendation logic."""
    status = status if isinstance(status, dict) else load_scheduler_status()
    if not status:
        return
    if status.get("_read_error"):
        st.caption(f"调度状态暂不可读：{_fmt(status.get('_read_error'))}")
        return

    t1_status = status.get("t1_preheat") if isinstance(status.get("t1_preheat"), dict) else {}
    daily_status = status.get("daily_report") if isinstance(status.get("daily_report"), dict) else {}

    if not t1_status and not daily_status:
        return

    with st.expander("调度/T+1 状态", expanded=False):
        if t1_status:
            st.caption(
                "T+1 最近状态："
                f"{_fmt(t1_status.get('status'))} | "
                f"开始 {_fmt(t1_status.get('started_at'))} | "
                f"结束 {_fmt(t1_status.get('finished_at'))} | "
                f"成功 {int(t1_status.get('success_count') or 0)} | "
                f"失败 {int(t1_status.get('failed_count') or 0)}"
            )
            rows = _target_rows(t1_status.get("targets") or {})
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        if daily_status:
            st.caption(
                "日报最近状态："
                f"{_fmt(daily_status.get('status'))} | "
                f"开始 {_fmt(daily_status.get('started_at'))} | "
                f"结束 {_fmt(daily_status.get('finished_at'))}"
            )
