"""Decision dashboard cards for single-stock analysis results."""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from decision_committee import build_a_share_decision


def build_decision_snapshot(
    data,
    signals: dict[str, Any],
    quote: dict[str, Any] | None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = build_a_share_decision(
        data=data,
        signals=signals,
        quote=quote,
        extended_info=extended_info,
        profile=profile,
    )
    score = decision["score"]
    tone = _tone_from_score(score)
    return {
        **decision,
        "tone": tone,
        "risks": decision.get("risk_alerts", []),
    }


def _tone_from_score(score: int | float | None) -> str:
    score = int(score or 0)
    if score >= 75:
        return "bullish"
    if score >= 60:
        return "watch"
    if score <= 35:
        return "bearish"
    return "neutral"


def _tone_from_delta(delta: int | float | None) -> str:
    delta = float(delta or 0)
    if delta > 0:
        return "bullish"
    if delta < 0:
        return "bearish"
    return "neutral"


def _escape(value: Any, default: str = "--") -> str:
    if value is None or value == "":
        return default
    return html.escape(str(value))


def _fmt_level(value: Any) -> str:
    try:
        if value is None or value == "":
            return "--"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "--"


def _chip(label: str, tone: str = "neutral") -> str:
    return f'<span class="decision-chip {tone}">{html.escape(str(label))}</span>'


def _progress_bar(value: Any, *, tone: str = "neutral", signed: bool = False) -> str:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    width = min(100, abs(numeric) if signed else max(0, numeric))
    label = f"{numeric:+.0f}" if signed else f"{numeric:.0f}%"
    return (
        '<div class="decision-meter">'
        f'<div class="decision-meter-fill {tone}" style="width:{width:.0f}%;"></div>'
        f'<span>{label}</span>'
        "</div>"
    )


def _list_items(items: list[Any] | tuple[Any, ...] | None, *, icon: str, empty: str, tone: str = "neutral") -> str:
    values = [str(item) for item in (items or []) if str(item).strip()]
    if not values:
        values = [empty]
    rows = "".join(
        f"<li><span class='decision-list-icon {tone}'>{html.escape(icon)}</span>{html.escape(item)}</li>"
        for item in values[:5]
    )
    return f"<ul class='decision-list'>{rows}</ul>"


def _key_level_row(label: str, value: Any, hint: str = "") -> str:
    hint_html = f"<span>{html.escape(hint)}</span>" if hint else ""
    return (
        '<div class="decision-level-row">'
        f"<span>{html.escape(label)}</span>"
        f"<b>{_fmt_level(value)}</b>"
        f"{hint_html}"
        "</div>"
    )


def _panel(title: str, body: str, tone: str = "neutral", *, compact: bool = False) -> None:
    compact_class = " compact" if compact else ""
    st.markdown(
        f"""
        <div class="decision-panel {tone}{compact_class}">
          <div class="decision-panel-title">{html.escape(title)}</div>
          <div class="decision-panel-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(snapshot: dict[str, Any]) -> None:
    score = int(snapshot.get("score") or 0)
    tone = snapshot.get("tone", "neutral")
    confidence = int(snapshot.get("confidence") or 0)
    body = f"""
    <div class="decision-hero {tone}">
      <div class="decision-score-ring {tone}">
        <strong>{score}</strong>
        <span>/100</span>
      </div>
      <div class="decision-hero-main">
        <div class="decision-eyebrow">A股决策委员会 · TradingAgents Lite</div>
        <div class="decision-hero-title">{_escape(snapshot.get("action"))}</div>
        <div class="decision-hero-summary">{_escape(snapshot.get("summary"))}</div>
        <div class="decision-chip-row">
          {_chip(f"仓位 {snapshot.get('position', '--')}", tone)}
          {_chip(f"风险 {snapshot.get('risk_level', '--')}", "bearish" if snapshot.get("risk_level") == "高" else "watch" if snapshot.get("risk_level") == "中" else "bullish")}
          {_chip(f"置信度 {confidence}%", "watch" if confidence < 70 else "bullish")}
        </div>
      </div>
    </div>
    """
    st.markdown(body, unsafe_allow_html=True)


def _render_key_levels(snapshot: dict[str, Any]) -> None:
    key_levels = snapshot.get("key_levels") or {}
    body = (
        _key_level_row("当前价", key_levels.get("price"), "实时/最新")
        + _key_level_row("支撑位", key_levels.get("support"), "BOLL下轨")
        + _key_level_row("中枢位", key_levels.get("mid"), "BOLL中轨")
        + _key_level_row("压力位", key_levels.get("resistance"), "BOLL上轨")
        + _key_level_row("MA20", key_levels.get("ma20"), "趋势线")
    )
    _panel("关键价位", body, snapshot.get("tone", "neutral"))


def _render_agent_card(agent: dict[str, Any]) -> str:
    delta = agent.get("score_delta", 0)
    raw_score = agent.get("raw_score", 0)
    tone = _tone_from_delta(delta)
    evidence = _list_items(agent.get("evidence"), icon="证", empty="暂无明确证据", tone="bullish")
    warnings = _list_items(agent.get("warnings"), icon="险", empty="暂无额外警报", tone="bearish")
    return f"""
    <div class="agent-card {tone}">
      <div class="agent-card-head">
        <div>
          <div class="agent-name">{_escape(agent.get("name"), "Agent")}</div>
          <div class="agent-summary">{_escape(agent.get("summary"))}</div>
        </div>
        <span class="agent-score-pill {tone}">{delta:+}</span>
      </div>
      <div class="agent-meta-grid">
        <span>立场 <b>{_escape(agent.get("stance"))}</b></span>
        <span>权重 <b>{agent.get("weight", 0)}</b></span>
        <span>原始分 <b>{raw_score:+}</b></span>
      </div>
      {_progress_bar(agent.get("confidence"), tone="watch")}
      <div class="agent-detail-grid">
        <div>{evidence}</div>
        <div>{warnings}</div>
      </div>
    </div>
    """


def render_decision_dashboard(
    data,
    signals: dict[str, Any],
    quote: dict[str, Any] | None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> None:
    if not signals or "error" in signals:
        return

    snapshot = build_decision_snapshot(data, signals, quote, extended_info, profile)
    st.markdown("#### 决策仪表盘")
    _render_hero(snapshot)

    col_action, col_levels, col_catalyst = st.columns([1.2, 1.2, 1.4])
    with col_action:
        body = (
            f"<div class='decision-action'>{_escape(snapshot.get('entry_hint'))}</div>"
            f"{_progress_bar(snapshot.get('confidence'), tone='watch')}"
            f"<div class='decision-mini-note'>信号：{_escape(snapshot.get('recommendation'))}</div>"
        )
        _panel("买卖点与仓位", body, snapshot.get("tone", "neutral"))
    with col_levels:
        _render_key_levels(snapshot)
    with col_catalyst:
        catalyst_html = _list_items(
            snapshot.get("catalysts"),
            icon="催",
            empty="等待量价突破、板块联动或公告催化",
            tone="watch",
        )
        _panel("催化因素", catalyst_html, "watch")

    col_bull, col_bear, col_risk = st.columns(3)
    with col_bull:
        _panel(
            "看多依据",
            _list_items(snapshot.get("bullish_points"), icon="多", empty="暂无明确看多证据", tone="bullish"),
            "bullish",
            compact=True,
        )
    with col_bear:
        _panel(
            "看空因素",
            _list_items(snapshot.get("bearish_points"), icon="空", empty="暂无明显看空风险", tone="neutral"),
            "neutral",
            compact=True,
        )
    with col_risk:
        risks = snapshot.get("risks") or snapshot.get("risk_alerts")
        _panel(
            "风险警报",
            _list_items(risks, icon="险", empty="暂无明显风险警报，仍需控制仓位", tone="bearish"),
            "bearish" if risks else "neutral",
            compact=True,
        )

    with st.expander("A股决策委员会：五层 Agent 观点", expanded=False):
        agent_cards = "".join(_render_agent_card(agent) for agent in snapshot.get("agents", []))
        st.markdown(f"<div class='agent-card-grid'>{agent_cards}</div>", unsafe_allow_html=True)
