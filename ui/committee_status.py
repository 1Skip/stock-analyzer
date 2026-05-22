"""A-share decision committee status card for the app shell."""
from __future__ import annotations

import html

import streamlit as st


def build_committee_status() -> dict:
    """Return lightweight status metadata for the local decision workflow."""
    from config import AI_API_KEY, AI_DEBATE_ENABLED, DAILY_REPORT_ENABLED, T1_PLAN_AUTO_ENABLED

    debate_enabled = bool(AI_DEBATE_ENABLED and AI_API_KEY)
    return {
        "stages": [
            {"name": "阶段1", "label": "六Agent决策", "done": True},
            {"name": "阶段2", "label": "个股仪表盘", "done": True},
            {"name": "阶段3", "label": "本地日报", "done": True, "active": DAILY_REPORT_ENABLED},
            {"name": "阶段4", "label": "LLM多空辩论", "done": True, "active": debate_enabled},
            {"name": "阶段5", "label": "T+1缓存预热", "done": True, "active": T1_PLAN_AUTO_ENABLED},
        ],
        "daily_report_enabled": bool(DAILY_REPORT_ENABLED),
        "debate_enabled": debate_enabled,
        "t1_preheat_enabled": bool(T1_PLAN_AUTO_ENABLED),
    }


def render_committee_status_card() -> None:
    """Render a compact sidebar card for local decision workflow status."""
    status = build_committee_status()
    stage_html = "".join(
        _stage_row(
            item["name"],
            item["label"],
            done=item["done"],
            active=item.get("active"),
        )
        for item in status["stages"]
    )
    daily_text = "已开启" if status["daily_report_enabled"] else "未开启"
    debate_text = "已开启" if status["debate_enabled"] else "默认关闭"
    t1_text = "已开启" if status["t1_preheat_enabled"] else "未开启"
    st.markdown(
        f"""
        <div class="committee-status-card">
          <div class="committee-status-eyebrow">TradingAgents Lite</div>
          <div class="committee-status-title">A股决策委员会</div>
          <div class="committee-status-subtitle">本地分析闭环状态</div>
          <div class="committee-stage-list">{stage_html}</div>
          <div class="committee-status-grid">
            <span>本地日报 <b>{daily_text}</b></span>
            <span>LLM辩论 <b>{debate_text}</b></span>
            <span>T+1预热 <b>{t1_text}</b></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _stage_row(name: str, label: str, *, done: bool, active: bool | None = None) -> str:
    state_class = "done" if done else "pending"
    if active is True:
        state_class += " active"
    elif active is False:
        state_class += " inactive"
    state_text = "运行中" if active is True else "可选" if active is False else "完成" if done else "待做"
    return (
        f'<div class="committee-stage-row {state_class}">'
        f"<span>{html.escape(name)}</span>"
        f"<strong>{html.escape(label)}</strong>"
        f"<em>{html.escape(state_text)}</em>"
        "</div>"
    )
