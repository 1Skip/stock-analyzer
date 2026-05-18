"""Explainable second-stage ranking for recommendation candidates."""
from __future__ import annotations

from typing import Any


def enrich_recommendations_with_alpha(
    recommended: list[dict[str, Any]] | None,
    *,
    strategy: str = "",
    sector: str = "",
    sort: bool = False,
) -> list[dict[str, Any]]:
    """Attach alpha ranking fields without changing the original strategy rules."""
    items = [dict(item) for item in (recommended or [])]
    for item in items:
        item.update(score_recommendation_alpha(item, strategy=strategy, sector=sector))
    if sort:
        items.sort(key=lambda item: (_safe_float(item.get("alpha_score")) or 0, _safe_float(item.get("score")) or 0), reverse=True)
    return items


def score_recommendation_alpha(stock: dict[str, Any], *, strategy: str = "", sector: str = "") -> dict[str, Any]:
    components: dict[str, int] = {}
    reasons: list[str] = []
    penalties: list[str] = []

    strategy_score = _safe_float(stock.get("score"))
    components["strategy"] = _component_from_strategy_score(strategy_score, reasons, penalties)
    components["trend"] = _score_trend(stock, reasons, penalties)
    components["volume"] = _score_volume(stock, reasons, penalties)
    components["capital"] = _score_capital(stock, reasons, penalties)
    components["sector"] = _score_sector(stock, sector, reasons)
    components["fundamental"] = _score_fundamental(stock, reasons, penalties)
    components["resonance"] = _score_resonance(stock, strategy, reasons)
    components["risk"] = _score_risk(stock, penalties)
    components["overheat"] = _score_overheat(stock, penalties)

    alpha_score = max(0, min(100, 50 + sum(components.values())))
    return {
        "alpha_score": round(alpha_score, 1),
        "alpha_grade": _alpha_grade(alpha_score),
        "rank_reason": reasons[:5] or ["策略基础分有效"],
        "rank_penalty": penalties[:5],
        "rank_components": components,
        "ranker_version": "alpha_v1",
    }


def _component_from_strategy_score(score: float | None, reasons: list[str], penalties: list[str]) -> int:
    if score is None:
        penalties.append("策略原始分缺失")
        return 0
    if score >= 85:
        reasons.append("策略原始分强")
        return 12
    if score >= 75:
        reasons.append("策略原始分较高")
        return 8
    if score >= 65:
        reasons.append("策略原始分达标")
        return 4
    penalties.append("策略原始分偏弱")
    return -8


def _score_trend(stock: dict[str, Any], reasons: list[str], penalties: list[str]) -> int:
    indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
    signals = stock.get("signals") if isinstance(stock.get("signals"), dict) else {}
    score = 0
    signal_text = " ".join(str(value) for value in signals.values())
    price = _safe_float(stock.get("latest_price") or stock.get("price"))
    ma5 = _safe_float(indicators.get("ma5"))
    ma10 = _safe_float(indicators.get("ma10"))
    ma20 = _safe_float(indicators.get("ma20"))
    ma60 = _safe_float(indicators.get("ma60"))

    if "金叉" in signal_text or "多头" in signal_text or "强突破" in str(stock.get("rating")):
        score += 8
        reasons.append("趋势信号偏强")
    if ma5 is not None and ma10 is not None and ma20 is not None and ma5 > ma10 > ma20:
        score += 7
        reasons.append("均线多头排列")
    elif price is not None and ma20 is not None:
        if price >= ma20:
            score += 4
            reasons.append("价格站上MA20")
        else:
            score -= 6
            penalties.append("价格跌破MA20")
    if ma20 is not None and ma60 is not None:
        if ma20 >= ma60:
            score += 4
        else:
            score -= 5
            penalties.append("中期均线偏弱")
    return max(-12, min(15, score))


def _score_volume(stock: dict[str, Any], reasons: list[str], penalties: list[str]) -> int:
    details = stock.get("strategy_details") if isinstance(stock.get("strategy_details"), dict) else {}
    volume_ratio = _safe_float(details.get("量比"))
    if volume_ratio is None:
        text = " ".join(str(value) for value in details.values())
        volume_ratio = _extract_number_after(text, "量比")
    if volume_ratio is None:
        return 0
    if 1.2 <= volume_ratio <= 3.5:
        reasons.append(f"量能确认 {volume_ratio:.2f}")
        return 8
    if volume_ratio > 3.5:
        penalties.append(f"量能过热 {volume_ratio:.2f}")
        return -4
    penalties.append(f"量能不足 {volume_ratio:.2f}")
    return -5


def _score_capital(stock: dict[str, Any], reasons: list[str], penalties: list[str]) -> int:
    extended = stock.get("extended_info") if isinstance(stock.get("extended_info"), dict) else {}
    fund_flow = extended.get("fund_flow") if isinstance(extended.get("fund_flow"), dict) else {}
    main_flow = _safe_float(fund_flow.get("main_net_inflow"))
    five_day = _safe_float(fund_flow.get("five_day_main_net_inflow"))
    main_ratio = _safe_float(fund_flow.get("main_net_inflow_ratio"))
    score = 0
    if five_day is not None:
        if five_day >= 30_000_000:
            score += 8
            reasons.append("近5日主力资金较强")
        elif five_day < 0:
            score -= 8
            penalties.append("近5日主力资金流出")
    if main_flow is not None:
        if main_flow > 0:
            score += 4
            reasons.append("当日主力净流入")
        elif main_flow < 0:
            score -= 4
            penalties.append("当日主力净流出")
    if main_ratio is not None and main_ratio < 0:
        score -= 3
    return max(-12, min(12, score))


def _score_sector(stock: dict[str, Any], sector: str, reasons: list[str]) -> int:
    extended = stock.get("extended_info") if isinstance(stock.get("extended_info"), dict) else {}
    attribution = extended.get("sector_attribution") or extended.get("attribution") or {}
    industry = attribution.get("industry") if isinstance(attribution, dict) else {}
    concepts = attribution.get("concepts") if isinstance(attribution, dict) else []
    score = 0
    industry_change = _safe_float((industry or {}).get("change_pct"))
    if industry_change is not None and industry_change > 0:
        score += 4 if industry_change < 2 else 7
        reasons.append("行业表现偏强")
    positive_concepts = 0
    if isinstance(concepts, list):
        for concept in concepts[:5]:
            if _safe_float((concept or {}).get("change_pct")) and _safe_float((concept or {}).get("change_pct")) > 0:
                positive_concepts += 1
    if positive_concepts:
        score += min(5, positive_concepts * 2)
        reasons.append("概念联动")
    if sector and sector != "全部":
        score += 2
    return max(0, min(10, score))


def _score_fundamental(stock: dict[str, Any], reasons: list[str], penalties: list[str]) -> int:
    extended = stock.get("extended_info") if isinstance(stock.get("extended_info"), dict) else {}
    financial = extended.get("financial") if isinstance(extended.get("financial"), dict) else {}
    metrics = financial.get("metrics") if isinstance(financial.get("metrics"), dict) else {}
    profile = stock.get("profile") if isinstance(stock.get("profile"), dict) else {}
    score = 0
    profit = _pick_metric(metrics, ("归母净利润", "净利润", "PARENT_NETPROFIT"))
    profit_growth = _pick_metric(metrics, ("净利润同比", "归母净利润同比", "PARENT_NETPROFIT_YOY"))
    pe = _safe_float(profile.get("pe_ttm") or profile.get("pe"))
    pb = _safe_float(profile.get("pb"))
    if profit_growth is not None and profit_growth > 20:
        score += 7
        reasons.append("利润增速较好")
    elif profit is not None and profit >= 0:
        score += 4
        reasons.append("盈利未亏损")
    elif profit is not None and profit < 0:
        score -= 8
        penalties.append("净利润亏损")
    if pe is not None:
        if 0 < pe <= 40:
            score += 3
        elif pe <= 0 or pe > 80:
            score -= 5
            penalties.append("估值压力较大")
    if pb is not None and pb > 8:
        score -= 3
        penalties.append("PB偏高")
    return max(-10, min(12, score))


def _score_resonance(stock: dict[str, Any], strategy: str, reasons: list[str]) -> int:
    checks = stock.get("strategy_checks") if isinstance(stock.get("strategy_checks"), dict) else {}
    core_checks = stock.get("core_checks") if isinstance(stock.get("core_checks"), dict) else {}
    source = core_checks or checks
    matched = sum(1 for ok in source.values() if ok)
    if matched >= 4:
        reasons.append("多因子共振")
        return 8
    if matched >= 3:
        reasons.append("策略条件命中较多")
        return 5
    if "激进突破" in str(stock.get("strategy") or strategy) and matched >= 3:
        return 6
    return 0


def _score_risk(stock: dict[str, Any], penalties: list[str]) -> int:
    extended = stock.get("extended_info") if isinstance(stock.get("extended_info"), dict) else {}
    risk_events = extended.get("risk_events") if isinstance(extended.get("risk_events"), dict) else {}
    announcements = risk_events.get("announcements") or []
    releases = risk_events.get("restricted_release") or risk_events.get("lockup_expiry") or []
    penalty = 0
    risky = [
        item for item in announcements
        if any(word in str((item or {}).get("title", "")) for word in ["减持", "立案", "处罚", "风险", "诉讼", "亏损", "退市", "问询", "监管"])
    ]
    if risky:
        penalty -= min(15, len(risky) * 8)
        penalties.append(f"风险公告 {len(risky)} 条")
    if releases:
        penalty -= min(8, len(releases) * 4)
        penalties.append("存在限售解禁")
    name = str(stock.get("name") or "").upper()
    if "ST" in name or "退" in name:
        penalty -= 20
        penalties.append("ST/退市标识")
    return max(-20, penalty)


def _score_overheat(stock: dict[str, Any], penalties: list[str]) -> int:
    change_pct = _safe_float(stock.get("change_pct"))
    if change_pct is None:
        return 0
    if change_pct >= 7:
        penalties.append("当日涨幅过热")
        return -8
    if change_pct >= 5:
        penalties.append("短线追高风险")
        return -5
    if change_pct <= -5:
        penalties.append("当日走势偏弱")
        return -6
    return 0


def _alpha_grade(score: float) -> str:
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _pick_metric(metrics: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        for key, value in (metrics or {}).items():
            if alias == str(key) or alias in str(key):
                number = _safe_float(value)
                if number is not None:
                    return number
    return None


def _extract_number_after(text: str, marker: str) -> float | None:
    if marker not in text:
        return None
    tail = text.split(marker, 1)[1]
    number = ""
    for char in tail:
        if char.isdigit() or char == ".":
            number += char
        elif number:
            break
    return _safe_float(number)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None
