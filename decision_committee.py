"""A-share decision committee inspired by TradingAgents.

Stage 1 final version is deterministic and data-driven. It keeps the system
fast for the web UI and GitHub Actions while using a TradingAgents-style
multi-role structure adapted to A-share data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from watchlist import get_entry_hint


AGENT_WEIGHTS = {
    "技术分析 Agent": 30,
    "资金情绪 Agent": 20,
    "基本面 Agent": 20,
    "题材板块 Agent": 15,
    "风险事件 Agent": 15,
}


@dataclass
class AgentView:
    name: str
    weight: int
    raw_score: int
    score_delta: int
    confidence: int
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
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a TradingAgents-Lite decision snapshot for an A-share stock."""
    signals = signals or {}
    quote = quote or {}
    extended_info = extended_info or {}
    profile = profile or {}
    latest = _latest_row(data)
    indicators = indicators or _extract_indicators(latest)
    price = _number(quote.get("price")) or _number(latest.get("close"))
    change_pct = _number(quote.get("change")) or _number(quote.get("change_pct"))
    recommendation = str(signals.get("recommendation") or signals.get("signal_summary") or "观望")

    agents = [
        _technical_agent(signals, indicators, latest, recommendation, price),
        _capital_agent(extended_info, quote, profile, change_pct),
        _fundamental_agent(extended_info, profile),
        _sector_agent(extended_info, profile),
        _risk_event_agent(extended_info, signals, recommendation, symbol, stock_name),
    ]

    score = 50 + sum(agent.score_delta for agent in agents)
    if change_pct is not None:
        score += int(max(-5, min(5, change_pct)))
    score = max(0, min(100, score))

    confidence = _overall_confidence(agents)
    risk_level = _risk_level(score, agents)
    action = _action_from_score(score, risk_level, confidence)
    position = _position_from_score(score, risk_level, confidence)
    entry_hint = get_entry_hint(price, indicators, recommendation) if price else "等待有效价格数据"
    key_levels = _key_levels(price, indicators, latest)

    bullish_points = _collect_points(agents, positive=True)
    bearish_points = _collect_points(agents, positive=False)
    catalysts = _collect_catalysts(extended_info, agents)
    risk_alerts = _collect_risk_alerts(agents)

    return {
        "symbol": symbol,
        "name": stock_name or symbol,
        "score": score,
        "confidence": confidence,
        "action": action,
        "position": position,
        "risk_level": risk_level,
        "entry_hint": entry_hint,
        "key_levels": key_levels,
        "recommendation": recommendation,
        "summary": _summary(action, score, risk_level, confidence),
        "bullish_points": bullish_points[:5],
        "bearish_points": bearish_points[:5],
        "risk_alerts": risk_alerts[:5],
        "catalysts": catalysts[:5],
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


def _technical_agent(
    signals: dict[str, Any],
    indicators: dict[str, Any],
    latest: dict[str, Any],
    recommendation: str,
    price: float | None,
) -> AgentView:
    name = "技术分析 Agent"
    raw = 0
    evidence = []
    warnings = []
    signal_text = " ".join(str(signals.get(key, "")) for key in ("macd", "rsi", "kdj", "boll", "recommendation"))

    if "偏多信号（强）" in recommendation:
        raw += 58
    elif "偏多" in recommendation:
        raw += 36
    elif "偏空信号（强）" in recommendation:
        raw -= 58
    elif "偏空" in recommendation:
        raw -= 36
    evidence.extend([part for part in (signals.get("macd"), signals.get("rsi"), signals.get("kdj"), signals.get("boll")) if part])

    if _contains(signal_text, ("金叉", "中轨上方", "反弹")):
        raw += 10
    if _contains(signal_text, ("死叉", "超买", "突破上轨", "回调")):
        warnings.append("技术面存在高位或回调信号")
        raw -= 12

    ma20 = _number(indicators.get("ma20") or latest.get("ma20"))
    ma60 = _number(indicators.get("ma60") or latest.get("ma60"))
    if price and ma20:
        if price > ma20:
            raw += 8
            evidence.append("价格位于 MA20 上方")
        else:
            raw -= 8
            warnings.append("价格位于 MA20 下方")
    if ma20 and ma60:
        if ma20 > ma60:
            raw += 8
            evidence.append("MA20 位于 MA60 上方")
        else:
            raw -= 8
            warnings.append("MA20 位于 MA60 下方")

    boll_upper = _number(indicators.get("boll_upper"))
    boll_lower = _number(indicators.get("boll_lower"))
    if price and boll_upper and boll_lower and boll_upper > boll_lower:
        position = (price - boll_lower) / (boll_upper - boll_lower)
        if position >= 0.9:
            warnings.append("价格接近布林上轨，追高风险上升")
            raw -= 8
        elif position <= 0.2:
            evidence.append("价格接近布林下轨，具备支撑观察价值")
            raw += 5

    return _agent(name, raw, evidence, warnings, "技术指标与趋势结构综合判断")


def _capital_agent(
    extended_info: dict[str, Any],
    quote: dict[str, Any],
    profile: dict[str, Any],
    change_pct: float | None,
) -> AgentView:
    name = "资金情绪 Agent"
    fund_flow = extended_info.get("fund_flow") or {}
    risk_events = extended_info.get("risk_events") or {}
    lhb = risk_events.get("lhb") or {}
    evidence = []
    warnings = []
    raw = 0

    main_flow = _number(fund_flow.get("main_net_inflow"))
    main_ratio = _number(fund_flow.get("main_net_inflow_ratio"))
    five_day_flow = _number(fund_flow.get("five_day_main_net_inflow"))
    super_flow = _number(fund_flow.get("super_large_net_inflow"))
    large_flow = _number(fund_flow.get("large_net_inflow"))

    if main_flow is not None:
        evidence.append(f"主力净流入 {_fmt_money(main_flow)}")
        raw += 24 if main_flow > 0 else -24
    if main_ratio is not None:
        evidence.append(f"主力净占比 {main_ratio:+.2f}%")
        raw += 8 if main_ratio > 0 else -8
    if five_day_flow is not None:
        evidence.append(f"近5日主力净流入 {_fmt_money(five_day_flow)}")
        raw += 18 if five_day_flow > 0 else -18
    if super_flow is not None and super_flow > 0:
        evidence.append(f"超大单净流入 {_fmt_money(super_flow)}")
        raw += 8
    if large_flow is not None and large_flow < 0:
        warnings.append(f"大单净流出 {_fmt_money(large_flow)}")
        raw -= 8

    turnover = _number(profile.get("turnover_rate") or quote.get("turnover_rate") or quote.get("turnover"))
    if turnover is not None:
        evidence.append(f"换手率 {turnover:.2f}%")
        if turnover > 12:
            warnings.append("换手率过高，短线博弈情绪偏强")
            raw -= 8
        elif turnover >= 2:
            raw += 5
    if lhb:
        evidence.append(f"龙虎榜近一月上榜 {lhb.get('times', '--')} 次")
        raw += 5 if (_number(lhb.get("net_amount")) or 0) > 0 else -5
    if change_pct is not None and abs(change_pct) >= 5:
        warnings.append(f"当日波动 {change_pct:+.2f}% 偏大")
        raw -= 8
    if not evidence:
        evidence.append("暂无资金流/换手/龙虎榜数据")

    return _agent(name, raw, evidence, warnings, "资金流、换手率与龙虎榜情绪综合判断")


def _fundamental_agent(extended_info: dict[str, Any], profile: dict[str, Any]) -> AgentView:
    name = "基本面 Agent"
    financial = extended_info.get("financial") or {}
    metrics = financial.get("metrics") or {}
    research = extended_info.get("research") or {}
    evidence = []
    warnings = []
    raw = 0

    revenue = _pick_metric(metrics, ("营业总收入", "营业收入"))
    profit = _pick_metric(metrics, ("归母净利润", "净利润"))
    cashflow = _pick_metric(metrics, ("经营现金流量净额", "经营现金流"))
    eps = _pick_metric(metrics, ("每股收益", "EPS"))
    pe = _number(profile.get("pe_ttm"))
    pb = _number(profile.get("pb"))
    market_cap = _number(profile.get("market_cap"))

    if revenue is not None:
        evidence.append(f"营收 {_fmt_money(revenue)}")
    if profit is not None:
        evidence.append(f"归母净利润 {_fmt_money(profit)}")
        raw += 22 if profit > 0 else -32
        if profit < 0:
            warnings.append("归母净利润为负，基本面承压")
    if cashflow is not None:
        evidence.append(f"经营现金流 {_fmt_money(cashflow)}")
        raw += 10 if cashflow > 0 else -10
    if eps is not None:
        evidence.append(f"EPS {eps:.3f}")
        raw += 6 if eps > 0 else -8
    if pe is not None:
        evidence.append(f"PE(TTM) {pe:.2f}")
        if pe <= 0:
            warnings.append("PE 为负或异常")
            raw -= 10
        elif pe > 80:
            warnings.append("PE 偏高，估值消化压力较大")
            raw -= 8
        elif pe < 35:
            raw += 5
    if pb is not None:
        evidence.append(f"PB {pb:.2f}")
        if pb > 8:
            warnings.append("PB 偏高，需关注估值风险")
            raw -= 6
        elif 0 < pb < 3:
            raw += 4
    if market_cap is not None:
        evidence.append(f"总市值 {_fmt_money(market_cap)}")
    reports = research.get("reports") or []
    if reports:
        evidence.append(f"近期研报 {len(reports)} 篇")
        raw += 6
    consensus = (research.get("eps_consensus") or {}).get("values") or {}
    if consensus:
        evidence.append("存在一致预期 EPS")
        raw += 5
    if not evidence:
        evidence.append("暂无完整基本面/估值数据")

    return _agent(name, raw, evidence, warnings, "盈利质量、现金流、估值与研报覆盖综合判断")


def _sector_agent(extended_info: dict[str, Any], profile: dict[str, Any]) -> AgentView:
    name = "题材板块 Agent"
    attribution = extended_info.get("sector_attribution") or extended_info.get("attribution") or {}
    industry = attribution.get("industry") or {}
    concepts = attribution.get("concepts") or []
    evidence = []
    warnings = []
    raw = 0

    profile_industry = profile.get("industry")
    if profile_industry:
        evidence.append(f"所属行业 {profile_industry}")
    industry_change = _number(industry.get("change_pct"))
    if industry:
        evidence.append(f"行业 {industry.get('name', '--')} {_fmt_pct(industry_change)}")
        if industry_change is not None:
            raw += 24 if industry_change >= 2 else 12 if industry_change > 0 else -15
    positive_concepts = 0
    negative_concepts = 0
    for concept in concepts[:5]:
        change = _number(concept.get("change_pct"))
        evidence.append(f"概念 {concept.get('name', '--')} {_fmt_pct(change)}")
        if change is not None and change > 0:
            positive_concepts += 1
        elif change is not None and change < 0:
            negative_concepts += 1
    raw += min(24, positive_concepts * 6)
    raw -= min(18, negative_concepts * 6)
    if concepts and positive_concepts == 0:
        warnings.append("相关概念未形成正向共振")
    if not evidence:
        evidence.append("暂无行业/概念归因数据")

    return _agent(name, raw, evidence, warnings, "行业强度、概念联动与题材催化综合判断")


def _risk_event_agent(
    extended_info: dict[str, Any],
    signals: dict[str, Any],
    recommendation: str,
    symbol: str,
    stock_name: str,
) -> AgentView:
    name = "风险事件 Agent"
    risk_events = extended_info.get("risk_events") or {}
    lhb = risk_events.get("lhb") or {}
    releases = risk_events.get("restricted_release") or risk_events.get("lockup_expiry") or []
    announcements = risk_events.get("announcements") or []
    evidence = []
    warnings = []
    raw = 10
    display_text = f"{symbol}{stock_name}".upper()

    if _contains(display_text, ("ST", "*ST", "退")):
        warnings.append("标的存在 ST/退市相关标识")
        raw -= 45
    if lhb:
        evidence.append(f"龙虎榜上榜 {lhb.get('times', '--')} 次")
        net_amount = _number(lhb.get("net_amount"))
        raw += 5 if net_amount and net_amount > 0 else -8
    if releases:
        warnings.append(f"存在 {len(releases)} 条限售解禁/供给冲击信息")
        raw -= min(35, len(releases) * 10)

    risky_announcements = [
        item for item in announcements
        if _contains(
            f"{item.get('title', '')}{item.get('type', '')}",
            ("风险", "减持", "质押", "处罚", "诉讼", "亏损", "退市", "停牌", "问询", "监管", "异常波动"),
        )
    ]
    if risky_announcements:
        warnings.append(f"存在 {len(risky_announcements)} 条风险公告")
        raw -= min(40, len(risky_announcements) * 12)
    if "偏空" in recommendation:
        warnings.append("技术信号偏空，需降低试错力度")
        raw -= 12
    if not evidence and not warnings:
        evidence.append("暂无明显公告/龙虎榜/解禁风险")

    return _agent(name, raw, evidence, warnings, "公告、解禁、龙虎榜与特殊状态风险综合判断")


def _agent(name: str, raw_score: int, evidence: list[str], warnings: list[str], summary_prefix: str) -> AgentView:
    raw_score = max(-100, min(100, int(raw_score)))
    weight = AGENT_WEIGHTS[name]
    score_delta = round(raw_score / 100 * weight)
    confidence = _confidence(evidence, warnings)
    stance = _stance(raw_score)
    summary = f"{summary_prefix}：{stance}"
    return AgentView(
        name=name,
        weight=weight,
        raw_score=raw_score,
        score_delta=score_delta,
        confidence=confidence,
        stance=stance,
        summary=summary,
        evidence=evidence[:6],
        warnings=warnings[:5],
    )


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


def _confidence(evidence: list[str], warnings: list[str]) -> int:
    signal_count = len([item for item in evidence if item and "暂无" not in item]) + len(warnings)
    if signal_count >= 5:
        return 90
    if signal_count >= 3:
        return 75
    if signal_count >= 1:
        return 55
    return 35


def _overall_confidence(agents: list[AgentView]) -> int:
    if not agents:
        return 0
    weighted = sum(agent.confidence * agent.weight for agent in agents)
    total_weight = sum(agent.weight for agent in agents)
    return round(weighted / total_weight)


def _stance(raw_score: int) -> str:
    if raw_score >= 25:
        return "看多"
    if raw_score <= -25:
        return "看空"
    return "中性"


def _risk_level(score: int, agents: list[AgentView]) -> str:
    risk_agent = next((agent for agent in agents if agent.name == "风险事件 Agent"), None)
    risk_penalty = abs(sum(min(0, agent.score_delta) for agent in agents))
    warning_count = sum(len(agent.warnings) for agent in agents)
    if score < 40 or risk_penalty >= 24 or warning_count >= 4 or (risk_agent and risk_agent.raw_score <= -45):
        return "高"
    if score < 65 or risk_penalty >= 10 or warning_count:
        return "中"
    return "低"


def _action_from_score(score: int, risk_level: str, confidence: int) -> str:
    if risk_level == "高" or score < 40:
        return "回避/降仓"
    if confidence < 55:
        return "等待数据确认"
    if score >= 78:
        return "积极关注"
    if score >= 62:
        return "轻仓试探"
    return "等待确认"


def _position_from_score(score: int, risk_level: str, confidence: int) -> str:
    if risk_level == "高" or score < 40:
        return "0-1成"
    if confidence < 55:
        return "观察仓"
    if score >= 78:
        return "2-3成"
    if score >= 62:
        return "1-2成"
    return "观察仓"


def _summary(action: str, score: int, risk_level: str, confidence: int) -> str:
    return f"{action}，综合评分 {score}/100，风险等级 {risk_level}，置信度 {confidence}%。"


def _key_levels(price: float | None, indicators: dict[str, Any], latest: dict[str, Any]) -> dict[str, Any]:
    support = _number(indicators.get("boll_lower")) or _number(latest.get("boll_lower"))
    mid = _number(indicators.get("boll_mid")) or _number(latest.get("boll_mid"))
    resistance = _number(indicators.get("boll_upper")) or _number(latest.get("boll_upper"))
    ma20 = _number(indicators.get("ma20")) or _number(latest.get("ma20"))
    return {
        "support": support,
        "mid": mid,
        "resistance": resistance,
        "ma20": ma20,
        "price": price,
    }


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
    if (_number(fund_flow.get("main_net_inflow")) or 0) > 0:
        catalysts.append("主力资金净流入")
    research = extended_info.get("research") or {}
    if research.get("reports"):
        catalysts.append("近期研报覆盖")
    if extended_info.get("market_news"):
        catalysts.append("市场快讯/宏观资讯催化")
    attribution = extended_info.get("sector_attribution") or extended_info.get("attribution") or {}
    concepts = attribution.get("concepts") or []
    if concepts:
        catalysts.append("题材/概念联动")
    if any(agent.name == "题材板块 Agent" and agent.score_delta > 0 for agent in agents):
        catalysts.append("行业板块表现偏强")
    if any(agent.name == "基本面 Agent" and agent.score_delta > 0 for agent in agents):
        catalysts.append("基本面/估值具备支撑")
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
