"""A-share decision committee inspired by TradingAgents.

The first version is deterministic and data-driven: it reuses the project's
existing indicators and A-share extended data, so it is fast enough for the
web UI and GitHub Actions daily reports.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from watchlist import get_entry_hint


@dataclass
class AgentView:
    name: str
    score_delta: int
    stance: str
    summary: str
    evidence: list[str]
    warnings: list[str]


def build_a_share_decision(
    data: pd.DataFrame | None = None,
    signals: dict[str, Any] | None = None,
    quote: dict[str, Any] | None = None,
    extended_info: dict[str, Any] | None = None,
    *,
    symbol: str = "",
    stock_name: str = "",
    indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a TradingAgents-Lite decision snapshot for an A-share stock."""
    signals = signals or {}
    quote = quote or {}
    extended_info = extended_info or {}
    latest = _latest_row(data)
    indicators = indicators or _extract_indicators(latest)
    price = _number(quote.get("price")) or _number(latest.get("close"))
    change_pct = _number(quote.get("change")) or _number(quote.get("change_pct"))
    recommendation = str(signals.get("recommendation") or signals.get("signal_summary") or "观望")

    agents = [
        _technical_agent(signals, indicators, latest, recommendation),
        _capital_agent(extended_info, quote, change_pct),
        _fundamental_agent(extended_info),
        _sector_agent(extended_info),
        _risk_event_agent(extended_info, signals, recommendation),
    ]

    score = 50 + sum(agent.score_delta for agent in agents)
    if change_pct is not None:
        score += int(max(-6, min(6, change_pct)))
    score = max(0, min(100, score))

    risk_level = _risk_level(score, agents)
    action = _action_from_score(score, risk_level)
    position = _position_from_score(score, risk_level)
    entry_hint = get_entry_hint(price, indicators, recommendation) if price else "等待有效价格数据"

    bullish_points = _collect_points(agents, positive=True)
    bearish_points = _collect_points(agents, positive=False)
    catalysts = _collect_catalysts(extended_info, agents)
    risk_alerts = _collect_risk_alerts(agents)

    return {
        "symbol": symbol,
        "name": stock_name or symbol,
        "score": score,
        "action": action,
        "position": position,
        "risk_level": risk_level,
        "entry_hint": entry_hint,
        "recommendation": recommendation,
        "summary": _summary(action, score, risk_level),
        "bullish_points": bullish_points[:4],
        "bearish_points": bearish_points[:4],
        "risk_alerts": risk_alerts[:4],
        "catalysts": catalysts[:4],
        "agents": [asdict(agent) for agent in agents],
    }


def build_watchlist_decision(item: dict[str, Any], extended_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a committee decision from watchlist summary data."""
    return build_a_share_decision(
        data=None,
        signals={"recommendation": item.get("signal_summary") or item.get("rating") or "观望"},
        quote={"price": item.get("price"), "change": item.get("change_pct")},
        extended_info=extended_info or {},
        symbol=str(item.get("symbol") or ""),
        stock_name=str(item.get("name") or item.get("symbol") or ""),
        indicators=item.get("indicators") or {},
    )


def _technical_agent(signals: dict[str, Any], indicators: dict[str, Any], latest: dict[str, Any], recommendation: str) -> AgentView:
    text = " ".join(str(signals.get(key, "")) for key in ("macd", "rsi", "kdj", "boll", "recommendation"))
    evidence = [part for part in (signals.get("macd"), signals.get("rsi"), signals.get("kdj"), signals.get("boll")) if part]
    warnings = []
    delta = 0
    if "偏多信号（强）" in recommendation:
        delta += 22
    elif "偏多" in recommendation:
        delta += 14
    if "偏空信号（强）" in recommendation:
        delta -= 22
    elif "偏空" in recommendation:
        delta -= 14
    if _contains(text, ("超买", "死叉", "突破上轨")):
        warnings.append("技术面存在高位或回调信号")
        delta -= 5
    if _contains(text, ("金叉", "中轨上方", "反弹")):
        delta += 4
    stance = _stance(delta)
    return AgentView("技术分析 Agent", delta, stance, f"技术面{recommendation}", evidence[:4], warnings)


def _capital_agent(extended_info: dict[str, Any], quote: dict[str, Any], change_pct: float | None) -> AgentView:
    fund_flow = extended_info.get("fund_flow") or {}
    main_flow = _number(fund_flow.get("main_net_inflow"))
    five_day_flow = _number(fund_flow.get("five_day_main_net_inflow"))
    evidence = []
    warnings = []
    delta = 0
    if main_flow is not None:
        evidence.append(f"主力净流入 {_fmt_money(main_flow)}")
        delta += 8 if main_flow > 0 else -8
    if five_day_flow is not None:
        evidence.append(f"近5日主力净流入 {_fmt_money(five_day_flow)}")
        delta += 5 if five_day_flow > 0 else -5
    if change_pct is not None and abs(change_pct) >= 5:
        warnings.append(f"当日波动 {change_pct:+.2f}% 偏大")
        delta -= 3
    if not evidence:
        evidence.append("暂无资金流数据")
    return AgentView("资金情绪 Agent", delta, _stance(delta), "资金面偏强" if delta > 0 else "资金面待确认", evidence, warnings)


def _fundamental_agent(extended_info: dict[str, Any]) -> AgentView:
    financial = extended_info.get("financial") or {}
    metrics = financial.get("metrics") or {}
    research = extended_info.get("research") or {}
    evidence = []
    warnings = []
    delta = 0
    revenue = _pick_metric(metrics, ("营业总收入", "营业收入"))
    profit = _pick_metric(metrics, ("归母净利润", "净利润"))
    if revenue is not None:
        evidence.append(f"营收 {_fmt_money(revenue)}")
    if profit is not None:
        evidence.append(f"归母净利润 {_fmt_money(profit)}")
        delta += 8 if profit > 0 else -12
        if profit < 0:
            warnings.append("归母净利润为负，基本面承压")
    reports = research.get("reports") or []
    if reports:
        evidence.append(f"近期研报 {len(reports)} 篇")
        delta += 4
    eps = (research.get("eps_consensus") or {}).get("values") or {}
    if eps:
        evidence.append("存在一致预期 EPS")
        delta += 3
    if not evidence:
        evidence.append("暂无完整基本面数据")
    return AgentView("基本面 Agent", delta, _stance(delta), "基本面有支撑" if delta > 0 else "基本面信息不足", evidence[:4], warnings)


def _sector_agent(extended_info: dict[str, Any]) -> AgentView:
    attribution = extended_info.get("sector_attribution") or extended_info.get("attribution") or {}
    industry = attribution.get("industry") or {}
    concepts = attribution.get("concepts") or []
    evidence = []
    warnings = []
    delta = 0
    industry_change = _number(industry.get("change_pct"))
    if industry:
        evidence.append(f"行业 {industry.get('name', '--')} { _fmt_pct(industry_change) }")
        if industry_change is not None:
            delta += 6 if industry_change > 0 else -6
    positive_concepts = 0
    for concept in concepts[:3]:
        change = _number(concept.get("change_pct"))
        evidence.append(f"概念 {concept.get('name', '--')} { _fmt_pct(change) }")
        if change is not None and change > 0:
            positive_concepts += 1
    if positive_concepts:
        delta += min(9, positive_concepts * 3)
    if not evidence:
        evidence.append("暂无行业/概念归因")
    return AgentView("题材板块 Agent", delta, _stance(delta), "板块联动偏强" if delta > 0 else "板块联动待确认", evidence[:4], warnings)


def _risk_event_agent(extended_info: dict[str, Any], signals: dict[str, Any], recommendation: str) -> AgentView:
    risk_events = extended_info.get("risk_events") or {}
    lhb = risk_events.get("lhb") or {}
    releases = risk_events.get("restricted_release") or risk_events.get("lockup_expiry") or []
    announcements = risk_events.get("announcements") or []
    evidence = []
    warnings = []
    delta = 0
    if lhb:
        evidence.append(f"龙虎榜上榜 {lhb.get('times', '--')} 次")
        delta -= 3
    if releases:
        warnings.append(f"存在 {len(releases)} 条限售解禁/供给冲击信息")
        delta -= min(12, len(releases) * 4)
    risky_announcements = [
        item for item in announcements
        if _contains(f"{item.get('title', '')}{item.get('type', '')}", ("风险", "减持", "质押", "处罚", "诉讼", "亏损", "退市", "停牌"))
    ]
    if risky_announcements:
        warnings.append(f"存在 {len(risky_announcements)} 条风险公告")
        delta -= min(15, len(risky_announcements) * 5)
    if "偏空" in recommendation:
        warnings.append("技术信号偏空，需降低试错力度")
        delta -= 4
    if not evidence and not warnings:
        evidence.append("暂无明显公告/龙虎榜/解禁风险")
    return AgentView("风险事件 Agent", delta, _stance(delta), "风险可控" if delta >= 0 else "风险事件需优先排查", evidence, warnings)


def _latest_row(data: pd.DataFrame | None) -> dict[str, Any]:
    if data is None or data.empty:
        return {}
    return data.iloc[-1].to_dict()


def _extract_indicators(latest: dict[str, Any]) -> dict[str, Any]:
    keys = ("boll_upper", "boll_mid", "boll_lower", "macd", "macd_signal", "rsi", "kdj_k", "kdj_d", "kdj_j", "ma5", "ma10", "ma20", "ma60")
    return {key: latest.get(key) for key in keys if key in latest}


def _pick_metric(metrics: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = _number(metrics.get(name))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _contains(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in str(text) for keyword in keywords)


def _stance(delta: int) -> str:
    if delta >= 8:
        return "看多"
    if delta <= -8:
        return "看空"
    return "中性"


def _risk_level(score: int, agents: list[AgentView]) -> str:
    risk_penalty = abs(sum(min(0, agent.score_delta) for agent in agents))
    warning_count = sum(len(agent.warnings) for agent in agents)
    if score < 40 or risk_penalty >= 25 or warning_count >= 3:
        return "高"
    if score < 65 or risk_penalty >= 10 or warning_count:
        return "中"
    return "低"


def _action_from_score(score: int, risk_level: str) -> str:
    if risk_level == "高" or score < 40:
        return "回避/降仓"
    if score >= 78:
        return "积极关注"
    if score >= 62:
        return "轻仓试探"
    return "等待确认"


def _position_from_score(score: int, risk_level: str) -> str:
    if risk_level == "高" or score < 40:
        return "0-1成"
    if score >= 78:
        return "2-3成"
    if score >= 62:
        return "1-2成"
    return "观察仓"


def _summary(action: str, score: int, risk_level: str) -> str:
    return f"{action}，综合评分 {score}/100，风险等级 {risk_level}。"


def _collect_points(agents: list[AgentView], *, positive: bool) -> list[str]:
    result = []
    for agent in agents:
        if positive and agent.score_delta > 0:
            result.extend(agent.evidence[:2])
        if not positive and agent.score_delta < 0:
            result.extend(agent.warnings or agent.evidence[:2])
    return result or (["暂无明确看多证据"] if positive else ["暂无明显看空风险"])


def _collect_risk_alerts(agents: list[AgentView]) -> list[str]:
    alerts = []
    for agent in agents:
        alerts.extend(agent.warnings)
    return alerts or ["暂无明显风险警报，仍需控制仓位"]


def _collect_catalysts(extended_info: dict[str, Any], agents: list[AgentView]) -> list[str]:
    catalysts = []
    fund_flow = extended_info.get("fund_flow") or {}
    if _number(fund_flow.get("main_net_inflow")) and _number(fund_flow.get("main_net_inflow")) > 0:
        catalysts.append("主力资金净流入")
    research = extended_info.get("research") or {}
    if research.get("reports"):
        catalysts.append("近期研报覆盖")
    attribution = extended_info.get("sector_attribution") or extended_info.get("attribution") or {}
    concepts = attribution.get("concepts") or []
    if concepts:
        catalysts.append("题材/概念联动")
    if any(agent.name == "题材板块 Agent" and agent.score_delta > 0 for agent in agents):
        catalysts.append("行业板块表现偏强")
    return catalysts or ["等待量价突破、板块联动或公告催化"]


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "--"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万"
    return f"{value:.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:+.2f}%"
