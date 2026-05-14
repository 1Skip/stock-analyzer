"""A-share decision committee status card for the app shell."""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st


def build_committee_status() -> dict:
    """Return lightweight status metadata for the TradingAgents-inspired rollout."""
    from config import AI_API_KEY, AI_DEBATE_ENABLED, FEISHU_WEBHOOK_URL, NOTIFY_CHANNELS

    workflow_exists = Path(".github/workflows/daily_analysis.yml").exists()
    feishu_enabled = bool(FEISHU_WEBHOOK_URL)
    debate_enabled = bool(AI_DEBATE_ENABLED and AI_API_KEY)
    notify_enabled = "feishu" in {channel.lower() for channel in NOTIFY_CHANNELS} or feishu_enabled
    return {
        "stages": [
            {"name": "阶段1", "label": "五层决策委员会", "done": True},
            {"name": "阶段2", "label": "个股页仪表盘", "done": True},
            {"name": "阶段3", "label": "日报决策仪表盘", "done": True},
            {"name": "阶段4", "label": "LLM多空辩论", "done": True, "active": debate_enabled},
            {"name": "阶段5", "label": "Actions飞书闭环", "done": True, "active": workflow_exists and notify_enabled},
        ],
        "feishu_enabled": feishu_enabled,
        "debate_enabled": debate_enabled,
        "workflow_exists": workflow_exists,
    }


def render_committee_status_card() -> None:
    """Render a compact sidebar card that makes completed phases visible."""
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
    feishu_text = "已配置" if status["feishu_enabled"] else "未配置"
    debate_text = "已开启" if status["debate_enabled"] else "默认关闭"
    actions_text = "已接入" if status["workflow_exists"] else "未发现"
    st.markdown(
        f"""
        <div class="committee-status-card">
          <div class="committee-status-eyebrow">TradingAgents Lite</div>
          <div class="committee-status-title">A股决策委员会</div>
          <div class="committee-status-subtitle">阶段 1-5 最终版已接入</div>
          <div class="committee-stage-list">{stage_html}</div>
          <div class="committee-status-grid">
            <span>飞书 <b>{feishu_text}</b></span>
            <span>LLM辩论 <b>{debate_text}</b></span>
            <span>Actions <b>{actions_text}</b></span>
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
