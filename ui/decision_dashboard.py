"""Decision dashboard cards for single-stock analysis results."""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from decision_committee import build_a_share_decision


def build_decision_snapshot(data, signals: dict[str, Any], quote: dict[str, Any] | None, extended_info: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = build_a_share_decision(data=data, signals=signals, quote=quote, extended_info=extended_info)
    score = decision["score"]
    tone = "bullish" if score >= 75 else "watch" if score >= 60 else "bearish" if score <= 35 else "neutral"
    return {
        **decision,
        "tone": tone,
        "risks": decision.get("risk_alerts", []),
    }


def _card(title: str, body: str, tone: str = "neutral") -> None:
    colors = {
        "bullish": ("#ff3b30", "rgba(255,59,48,0.10)"),
        "bearish": ("#34c759", "rgba(52,199,89,0.10)"),
        "watch": ("#ff9500", "rgba(255,149,0,0.10)"),
        "neutral": ("#1e88e5", "rgba(30,136,229,0.10)"),
    }
    accent, background = colors.get(tone, colors["neutral"])
    st.markdown(
        f"""
        <div class="decision-card" style="border-left-color:{accent};background:{background};">
          <div class="decision-card-title">{html.escape(title)}</div>
          <div class="decision-card-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_decision_dashboard(data, signals: dict[str, Any], quote: dict[str, Any] | None, extended_info: dict[str, Any] | None = None) -> None:
    if not signals or "error" in signals:
        return

    snapshot = build_decision_snapshot(data, signals, quote, extended_info)
    st.markdown("#### 决策仪表盘")
    col_score, col_action, col_risk, col_catalyst = st.columns([1, 1.2, 1.6, 1.6])
    with col_score:
        score = snapshot["score"]
        _card("综合评分", f"<div class='decision-score'>{score}</div><div>/ 100</div>", snapshot["tone"])
    with col_action:
        _card(
            "操作参考",
            f"<b>{html.escape(snapshot['action'])}</b><br>"
            f"<span>仓位：{html.escape(snapshot['position'])}</span><br>"
            f"<span>{html.escape(snapshot['entry_hint'])}</span>",
            snapshot["tone"],
        )
    with col_risk:
        risk_html = "<br>".join(f"⚠ {html.escape(item)}" for item in snapshot["risks"])
        _card("风险警报", risk_html, "bearish" if snapshot["risks"] else "neutral")
    with col_catalyst:
        catalyst_html = "<br>".join(f"✨ {html.escape(item)}" for item in snapshot["catalysts"])
        _card("催化因素", catalyst_html, "watch")

    with st.expander("A股决策委员会：五层 Agent 观点", expanded=False):
        cols = st.columns(5)
        for idx, agent in enumerate(snapshot.get("agents", [])):
            with cols[idx % 5]:
                evidence = "<br>".join(html.escape(str(item)) for item in agent.get("evidence", [])[:3])
                warnings = "<br>".join(f"⚠ {html.escape(str(item))}" for item in agent.get("warnings", [])[:2])
                body = (
                    f"<b>{html.escape(agent.get('stance', '--'))}</b> "
                    f"({agent.get('score_delta', 0):+})<br>"
                    f"{html.escape(agent.get('summary', ''))}<br>{evidence}"
                )
                if warnings:
                    body += f"<br>{warnings}"
                _card(agent.get("name", "Agent"), body, "bullish" if agent.get("score_delta", 0) > 0 else "bearish" if agent.get("score_delta", 0) < 0 else "neutral")
