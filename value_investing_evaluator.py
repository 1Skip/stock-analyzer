"""Munger-Buffett-Codex valuation snapshot from real project data."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
import re
from statistics import median
from typing import Any


VALUATION_VERSION = "mbc_value_v1"
STATUS_SCREEN_GRADE = "screen-grade"
UNSUPPORTED_FINANCIAL_INDUSTRIES = ("银行", "保险", "证券", "多元金融", "信托")


def build_value_investing_snapshot(
    profile: dict[str, Any] | None,
    extended_info: dict[str, Any] | None,
    *,
    current_price: Any,
    price_as_of: Any = None,
    price_source: str = "",
) -> dict[str, Any]:
    """Build a conservative per-share valuation without fetching data.

    The project does not currently expose capex, net debt, or ROIC. The model
    therefore uses cash-backed earnings as an owner-earnings proxy and never
    grades the result above screen-grade.
    """
    profile = profile if isinstance(profile, dict) else {}
    extended_info = extended_info if isinstance(extended_info, dict) else {}
    financial = extended_info.get("financial") if isinstance(extended_info.get("financial"), dict) else {}
    metrics = financial.get("metrics") if isinstance(financial.get("metrics"), dict) else {}
    history = financial.get("history") if isinstance(financial.get("history"), list) else []
    research = extended_info.get("research") if isinstance(extended_info.get("research"), dict) else {}
    consensus = research.get("eps_consensus") if isinstance(research.get("eps_consensus"), dict) else {}
    dividend = extended_info.get("dividend") if isinstance(extended_info.get("dividend"), dict) else {}

    price = _positive(current_price)
    as_of = _date_text(price_as_of) or date.today().isoformat()
    report_period = _date_text(financial.get("period"))
    industry = str(profile.get("industry") or "")
    missing: list[str] = []

    if price is None:
        return _not_evaluable("当前价格缺失，无法锚定估值。", as_of, price_source, ["当前价格"])
    if any(token in industry for token in UNSUPPORTED_FINANCIAL_INDUSTRIES):
        return _not_evaluable(
            "金融行业需要净资产质量、资本充足率等专用模型，当前通用模型不适用。",
            as_of,
            price_source,
            ["金融行业专用估值字段"],
        )

    total_shares = _positive(profile.get("total_shares"))
    net_profit = _number(_metric(metrics, ("归母净利润", "净利润")))
    operating_cash = _number(_metric(metrics, ("经营现金流量净额", "经营活动产生的现金流量净额")))
    reported_eps = _number(_metric(metrics, ("每股收益", "基本每股收益", "EPS")))
    annual_factor = _annualization_factor(report_period)
    annual_profit = net_profit * annual_factor if net_profit is not None else None
    annual_cash = operating_cash * annual_factor if operating_cash is not None else None
    annual_eps = reported_eps * annual_factor if reported_eps is not None else None
    profit_per_share = annual_profit / total_shares if annual_profit is not None and total_shares else None
    cash_per_share = annual_cash / total_shares if annual_cash is not None and total_shares else None
    earnings_candidates = [value for value in (annual_eps, profit_per_share) if value is not None and value > 0]
    normalized_eps = median(earnings_candidates) if earnings_candidates else None

    if normalized_eps is not None and cash_per_share is not None and cash_per_share > 0:
        owner_earnings = min(normalized_eps, cash_per_share)
        owner_basis = "盈利与经营现金流孰低值"
    elif normalized_eps is not None:
        owner_earnings = normalized_eps * 0.70
        owner_basis = "盈利七折代理（经营现金流缺失或为负）"
        missing.append("正向经营现金流验证")
    elif cash_per_share is not None and cash_per_share > 0:
        owner_earnings = cash_per_share * 0.70
        owner_basis = "经营现金流七折代理（盈利字段缺失）"
        missing.append("正向盈利验证")
    else:
        return _not_evaluable(
            "正向盈利和经营现金流均不足，无法形成所有者收益代理。",
            as_of,
            price_source,
            ["正向盈利", "正向经营现金流"],
        )

    history_growth = _same_period_growth(history, "归母净利润", report_period)
    consensus_growth = _consensus_eps_growth(consensus.get("values"), normalized_eps, report_period)
    growth_evidence = history_growth if history_growth is not None else consensus_growth
    base_growth = max(-0.05, min(0.08, growth_evidence if growth_evidence is not None else 0.0))
    growth_basis = (
        "同报告期归母净利润同比"
        if history_growth is not None
        else "公开一致预期EPS"
        if consensus_growth is not None
        else "缺少可靠增长证据，基础情景按零增长"
    )

    scenarios = {
        "downside": _scenario_value(owner_earnings * 0.80, min(base_growth - 0.05, 0.0), 0.12, 0.00),
        "base": _scenario_value(owner_earnings, base_growth, 0.10, 0.02),
        "upside": _scenario_value(owner_earnings * 1.05, min(base_growth + 0.03, 0.12), 0.09, 0.03),
    }
    labels = {"downside": "悲观", "base": "基础", "upside": "乐观"}
    scenario_rows = []
    for key in ("downside", "base", "upside"):
        item = scenarios[key]
        value = item.get("value_per_share")
        scenario_rows.append({
            "key": key,
            "label": labels[key],
            **item,
            "margin_of_safety_pct": _pct(value / price - 1) if value is not None else None,
        })

    base_value = scenarios["base"].get("value_per_share")
    base_margin = _pct(base_value / price - 1) if base_value is not None else None
    cash_conversion = annual_cash / annual_profit if annual_cash is not None and annual_profit and annual_profit > 0 else None
    dividend_per_share = _positive(
        dividend.get("cash_dividend_per_share") or dividend.get("annual_dividend_per_share")
    )
    dividend_yield = _pct(dividend_per_share / price) if dividend_per_share is not None else None
    history_profit_ratio = _positive_history_ratio(history, ("归母净利润", "净利润"))

    munger = _munger_score(
        annual_profit=annual_profit,
        annual_cash=annual_cash,
        cash_conversion=cash_conversion,
        history_profit_ratio=history_profit_ratio,
        growth=growth_evidence,
        listing_date=profile.get("listing_date"),
        as_of=as_of,
    )
    buffett = _buffett_score(
        owner_earnings=owner_earnings,
        current_price=price,
        base_margin=base_margin,
        dividend_yield=dividend_yield,
    )

    load_bearing = {
        "当前价格": price,
        "财务报告期": report_period,
        "总股本": total_shares,
        "归母净利润": annual_profit,
        "经营现金流": annual_cash,
        "财务来源": financial.get("source") or extended_info.get("source"),
    }
    for label, value in load_bearing.items():
        if value in (None, ""):
            missing.append(label)
    missing.extend(["资本开支", "净负债/净现金", "ROIC", "护城河持续性证据", "管理层资本配置记录"])
    missing = list(dict.fromkeys(missing))
    codex = _codex_score(load_bearing, scenarios, report_period, as_of, growth_evidence)
    total_score = round(munger["score"] + buffett["score"] + codex["score"], 1)

    if base_margin is not None and base_margin >= 20 and total_score >= 70:
        action = "观察仓候选"
    elif base_margin is not None and base_margin < 0:
        action = "估值偏贵，等待价格或盈利变化"
    elif total_score < 50:
        action = "证据不足，暂不纳入"
    else:
        action = "等待更多证据"

    return {
        "status": "ok",
        "version": VALUATION_VERSION,
        "grade": STATUS_SCREEN_GRADE,
        "grade_label": "筛选级，不是精确内在价值",
        "current_price": round(price, 3),
        "price_as_of": as_of,
        "price_source": price_source or "页面当前真实行情/日K",
        "report_period": report_period,
        "financial_source": financial.get("source") or extended_info.get("source") or "--",
        "score": total_score,
        "action": action,
        "pillars": [munger, buffett, codex],
        "scenarios": scenario_rows,
        "base_value_per_share": base_value,
        "base_margin_of_safety_pct": base_margin,
        "market_implied_owner_earnings_multiple": round(price / owner_earnings, 2) if owner_earnings > 0 else None,
        "owner_earnings_yield_pct": _pct(owner_earnings / price),
        "facts": {
            "annualized_net_profit": _rounded(annual_profit),
            "annualized_operating_cash_flow": _rounded(annual_cash),
            "normalized_eps": _rounded(normalized_eps),
            "owner_earnings_proxy_per_share": _rounded(owner_earnings),
            "cash_conversion": _rounded(cash_conversion),
            "history_positive_profit_ratio": _rounded(history_profit_ratio),
            "dividend_yield_pct": dividend_yield,
        },
        "assumptions": {
            "owner_earnings_basis": owner_basis,
            "annualization_factor": annual_factor,
            "growth_basis": growth_basis,
            "base_growth_pct": _pct(base_growth),
            "forecast_years": 10,
        },
        "what_is_priced_in": (
            f"当前价格约为所有者收益代理的 {price / owner_earnings:.2f} 倍，"
            f"对应收益率 {_pct(owner_earnings / price):.2f}%。"
        ),
        "invalidation_conditions": [
            "归母净利润或经营现金流转负",
            "现金转化率持续低于0.5",
            "当前价格明显高于基础情景价值",
            "新增重大风险事件或盈利预期下修",
        ],
        "missing_evidence": missing,
        "source_posture": "事实来自页面已加载的真实行情、基础资料、财务摘要、分红和一致预期；模型值与假设单独列示。",
    }


def _not_evaluable(message: str, as_of: str, source: str, missing: list[str]) -> dict[str, Any]:
    return {
        "status": "not_evaluable",
        "version": VALUATION_VERSION,
        "grade": "not-decision-ready",
        "message": message,
        "price_as_of": as_of,
        "price_source": source or "--",
        "missing_evidence": missing,
    }


def _scenario_value(owner_earnings: float, growth: float, discount: float, terminal_growth: float) -> dict[str, Any]:
    years = 10
    cash = max(0.0, float(owner_earnings))
    present_value = 0.0
    for year in range(1, years + 1):
        cash *= 1 + growth
        present_value += cash / ((1 + discount) ** year)
    terminal = cash * (1 + terminal_growth) / (discount - terminal_growth)
    present_value += terminal / ((1 + discount) ** years)
    return {
        "value_per_share": round(present_value, 2),
        "growth_pct": _pct(growth),
        "discount_rate_pct": _pct(discount),
        "terminal_growth_pct": _pct(terminal_growth),
    }


def _munger_score(**values: Any) -> dict[str, Any]:
    score = 0.0
    notes: list[str] = []
    if (values.get("annual_profit") or 0) > 0:
        score += 8
        notes.append("盈利为正")
    if (values.get("annual_cash") or 0) > 0:
        score += 8
        notes.append("经营现金流为正")
    conversion = values.get("cash_conversion")
    if conversion is not None:
        if conversion >= 1:
            score += 8
        elif conversion >= 0.6:
            score += 5
        notes.append(f"现金转化率 {conversion:.2f}")
    ratio = values.get("history_profit_ratio")
    if ratio is not None:
        score += 8 * max(0.0, min(1.0, ratio))
        notes.append(f"历史盈利为正占比 {ratio * 100:.0f}%")
    growth = values.get("growth")
    if growth is not None and growth > 0:
        score += 4
        notes.append(f"可验证增长 {growth * 100:.1f}%")
    if _listing_age_years(values.get("listing_date"), values.get("as_of")) >= 5:
        score += 4
        notes.append("上市满5年")
    return {"name": "芒格质量", "score": round(min(score, 40), 1), "max_score": 40, "notes": notes}


def _buffett_score(*, owner_earnings: float, current_price: float, base_margin: float | None, dividend_yield: float | None) -> dict[str, Any]:
    score = 10.0
    notes = ["所有者收益代理为正"]
    earnings_yield = owner_earnings / current_price
    if earnings_yield >= 0.08:
        score += 10
    elif earnings_yield >= 0.05:
        score += 6
    else:
        score += 2
    notes.append(f"所有者收益率 {earnings_yield * 100:.2f}%")
    if base_margin is not None:
        if base_margin >= 30:
            score += 10
        elif base_margin >= 15:
            score += 6
        elif base_margin >= 0:
            score += 2
        notes.append(f"基础安全边际 {base_margin:.2f}%")
    if dividend_yield is not None:
        score += 5 if dividend_yield >= 2 else 2 if dividend_yield > 0 else 0
        notes.append(f"股息率 {dividend_yield:.2f}%")
    return {"name": "巴菲特价值", "score": round(min(score, 35), 1), "max_score": 35, "notes": notes}


def _codex_score(load_bearing: dict[str, Any], scenarios: dict[str, Any], report_period: str | None, as_of: str, growth: float | None) -> dict[str, Any]:
    available = sum(value not in (None, "") for value in load_bearing.values())
    score = 10 * available / len(load_bearing)
    notes = [f"关键字段 {available}/{len(load_bearing)}"]
    if all(item.get("value_per_share") is not None for item in scenarios.values()):
        score += 5
        notes.append("三情景可计算")
    age_days = _days_between(report_period, as_of)
    if age_days is not None and age_days <= 400:
        score += 4
        notes.append(f"财务期距估值日 {age_days} 天")
    score += 3
    notes.append("已列出下行失效条件")
    if growth is not None:
        score += 3
        notes.append("增长有历史或一致预期证据")
    return {"name": "Codex证据纪律", "score": round(min(score, 25), 1), "max_score": 25, "notes": notes}


def _metric(metrics: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if metrics.get(name) not in (None, ""):
            return metrics.get(name)
    return None


def _annualization_factor(period: str | None) -> float:
    if not period:
        return 1.0
    digits = re.sub(r"\D", "", str(period))
    month = int(digits[4:6]) if len(digits) >= 6 and digits[4:6].isdigit() else 12
    return {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(month, 1.0)


def _same_period_growth(history: list[dict[str, Any]], metric: str, latest_period: str | None) -> float | None:
    latest_date = _parse_date(latest_period)
    if latest_date is None:
        return None
    latest_value = None
    previous_value = None
    for row in history:
        if not isinstance(row, dict):
            continue
        row_date = _parse_date(row.get("period"))
        value = _number(_metric(row, (metric, "净利润")))
        if row_date is None or value is None:
            continue
        if row_date.year == latest_date.year and row_date.month == latest_date.month:
            latest_value = value
        if row_date.year == latest_date.year - 1 and row_date.month == latest_date.month:
            previous_value = value
    if latest_value is None or previous_value is None or previous_value <= 0:
        return None
    return latest_value / previous_value - 1


def _consensus_eps_growth(values: Any, normalized_eps: float | None, report_period: str | None) -> float | None:
    if not isinstance(values, dict) or not normalized_eps or normalized_eps <= 0:
        return None
    report_date = _parse_date(report_period)
    base_year = report_date.year if report_date else date.today().year
    candidates = []
    for key, raw in values.items():
        match = re.search(r"20\d{2}", str(key))
        value = _positive(raw)
        if match and value is not None and int(match.group()) >= base_year:
            candidates.append((int(match.group()), value))
    if not candidates:
        return None
    year, eps = min(candidates)
    years = max(1, year - base_year)
    return (eps / normalized_eps) ** (1 / years) - 1 if eps > 0 else None


def _positive_history_ratio(history: list[dict[str, Any]], names: tuple[str, ...]) -> float | None:
    values = []
    for row in history:
        if isinstance(row, dict):
            value = _number(_metric(row, names))
            if value is not None:
                values.append(value)
    return sum(value > 0 for value in values) / len(values) if values else None


def _listing_age_years(listing_date: Any, as_of: Any) -> float:
    start = _parse_date(listing_date)
    end = _parse_date(as_of)
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).days / 365.25)


def _days_between(start: Any, end: Any) -> int | None:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        return None
    return max(0, (end_date - start_date).days)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    digits = re.sub(r"\D", "", text)
    try:
        if len(digits) >= 8:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        return datetime.fromisoformat(text).date()
    except (TypeError, ValueError):
        return None


def _date_text(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _pct(value: float) -> float:
    return round(float(value) * 100, 2)


def _rounded(value: Any) -> float | None:
    number = _number(value)
    return round(number, 4) if number is not None else None
