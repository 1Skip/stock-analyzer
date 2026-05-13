"""Decision dashboard cards for single-stock analysis results."""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from watchlist import get_entry_hint


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def build_decision_snapshot(data, signals: dict[str, Any], quote: dict[str, Any] | None, extended_info: dict[str, Any] | None = None) -> dict[str, Any]:
    recommendation = str(signals.get("recommendation", "观望"))
    signal_text = " ".join(str(signals.get(key, "")) for key in ("macd", "rsi", "kdj", "boll", "recommendation"))

    score = 50
    if "偏多信号（强）" in recommendation:
        score = 82
    elif "偏多" in recommendation:
        score = 68
    elif "偏空信号（强）" in recommendation:
        score = 22
    elif "偏空" in recommendation:
        score = 35

    change_pct = (quote or {}).get("change")
    if isinstance(change_pct, (int, float)):
        score += max(-8, min(8, change_pct * 1.2))
    score = int(max(0, min(100, round(score))))

    latest = data.iloc[-1].to_dict() if data is not None and not data.empty else {}
    price = (quote or {}).get("price") or latest.get("close") or 0
    entry_hint = get_entry_hint(price, latest, recommendation) if price else "等待有效价格数据"

    if score >= 75:
        action = "积极关注"
        tone = "bullish"
    elif score >= 60:
        action = "轻仓试探"
        tone = "watch"
    elif score <= 35:
        action = "控制风险"
        tone = "bearish"
    else:
        action = "耐心观察"
        tone = "neutral"

    risks = []
    if _contains_any(signal_text, ("偏空", "死叉", "回调", "超买", "突破上轨")):
        risks.append("技术面存在回调/偏空信号，避免追高。")
    if _contains_any(signal_text, ("超卖", "跌破下轨")):
        risks.append("短线波动可能放大，等待企稳确认。")
    risk_events = (extended_info or {}).get("risk_events") or {}
    announcements = risk_events.get("announcements") or []
    lockups = risk_events.get("lockup_expiry") or []
    if announcements:
        first = announcements[0]
        risks.append(f"关注公告风险：{first.get('title') or first.get('name') or '最新公告'}")
    if lockups:
        risks.append("存在限售解禁相关信息，注意供给冲击。")
    if not risks:
        risks.append("暂无明显风险警报，仍需控制仓位。")

    catalysts = []
    fund_flow = (extended_info or {}).get("fund_flow") or {}
    if fund_flow.get("main_net_inflow"):
        catalysts.append("主力资金流向可作为短线催化观察。")
    research = (extended_info or {}).get("research") or {}
    if research.get("reports"):
        catalysts.append("近期研报覆盖，可结合评级/目标价变化跟踪。")
    attribution = (extended_info or {}).get("attribution") or {}
    concepts = attribution.get("concepts") or []
    if concepts:
        catalysts.append(f"题材关注：{'、'.join(str(item) for item in concepts[:3])}")
    news = (extended_info or {}).get("news") or []
    if news:
        catalysts.append("近期新闻可能影响情绪面。")
    if not catalysts:
        catalysts.append("等待量价突破、板块联动或公告催化。")

    return {
        "score": score,
        "action": action,
        "tone": tone,
        "recommendation": recommendation,
        "entry_hint": entry_hint,
        "risks": risks[:3],
        "catalysts": catalysts[:3],
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
            f"<b>{html.escape(snapshot['action'])}</b><br><span>{html.escape(snapshot['entry_hint'])}</span>",
            snapshot["tone"],
        )
    with col_risk:
        risk_html = "<br>".join(f"⚠ {html.escape(item)}" for item in snapshot["risks"])
        _card("风险警报", risk_html, "bearish" if snapshot["risks"] else "neutral")
    with col_catalyst:
        catalyst_html = "<br>".join(f"✨ {html.escape(item)}" for item in snapshot["catalysts"])
        _card("催化因素", catalyst_html, "watch")
