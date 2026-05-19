"""Post-selection trade plan helpers for recommendations.

The functions in this module only add execution guidance to stocks that were
already selected by a strategy. They must not filter, reorder, or rescore the
recommendation list.
"""
from __future__ import annotations

import math
from typing import Any


def enrich_recommendations_with_trade_plan(
    recommended: list[dict[str, Any]] | None,
    *,
    strategy: str = "",
    sector: str = "",
) -> list[dict[str, Any]]:
    stocks = recommended or []
    for stock in stocks:
        if isinstance(stock, dict):
            stock["trade_plan"] = build_trade_plan_for_stock(stock, strategy=strategy, sector=sector)
    return stocks


def build_trade_plan_for_stock(stock: dict[str, Any], *, strategy: str = "", sector: str = "") -> dict[str, Any]:
    indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
    price = _safe_float(stock.get("latest_price") or stock.get("price"))
    if price is None:
        price = _first_number(indicators, ("close", "ma5", "ma10", "ma20", "boll_mid"))

    ma5 = _safe_float(indicators.get("ma5"))
    ma10 = _safe_float(indicators.get("ma10"))
    ma20 = _safe_float(indicators.get("ma20"))
    ma60 = _safe_float(indicators.get("ma60") or indicators.get("ma30"))
    boll_upper = _safe_float(indicators.get("boll_upper"))
    boll_mid = _safe_float(indicators.get("boll_mid"))
    boll_lower = _safe_float(indicators.get("boll_lower"))

    support = boll_lower or ma20 or ma60 or ma10
    resistance = boll_upper or _min_above_or_equal(price, [ma5, ma10])

    score = int(_safe_float(stock.get("score")) or 0)
    plan = build_trade_plan_from_levels(
        price=price,
        support=support,
        mid=boll_mid,
        resistance=resistance,
        ma20=ma20,
        ma60=ma60,
        score=score,
        confidence=int(_safe_float(stock.get("confidence")) or 70),
        risk_level=str(stock.get("risk_level") or "中"),
        action=str(stock.get("action") or stock.get("rating") or "等待确认"),
        position=_position_hint(strategy, stock),
        data_basis=(
            "基于推荐生成时的日K、BOLL、均线和支撑压力生成；"
            "不使用盘中实时行情；不参与选股、排序或评分。"
        ),
    )
    plan.update({
        "buy_zone_low": _first_level_from_zone(plan.get("buy_zone"), index=0),
        "buy_zone_high": _first_level_from_zone(plan.get("buy_zone"), index=1),
        "invalid_conditions": _invalid_conditions(plan.get("stop_loss"), ma20, ma60, stock),
        "strategy": strategy or stock.get("strategy") or "",
        "sector": sector,
    })
    if ma5 is not None and ma10 is not None and ma20 is not None:
        plan["add_condition"] = _add_condition(ma5, ma10, ma20, strategy)
    return plan


def build_trade_plan_from_levels(
    *,
    price: float | None = None,
    support: float | None = None,
    mid: float | None = None,
    resistance: float | None = None,
    ma20: float | None = None,
    ma60: float | None = None,
    score: int | float | None = None,
    confidence: int | float | None = None,
    risk_level: str = "中",
    action: str = "等待确认",
    position: str = "--",
    buffer: float | None = None,
    risk_control: dict[str, Any] | None = None,
    data_basis: str = "真实行情/K线/指标推导，未使用模拟或随机行情",
) -> dict[str, Any]:
    """Build a shared post-selection execution plan from real daily levels."""
    score_value = int(score or 0)
    risk_control = risk_control or {}
    price = _safe_float(price)
    support = _safe_float(support)
    mid = _safe_float(mid)
    resistance = _safe_float(resistance)
    ma20 = _safe_float(ma20)
    ma60 = _safe_float(ma60)

    if risk_control:
        confirm_level = _safe_float(risk_control.get("confirm_level"))
        if risk_control.get("hard_block"):
            buy_zone = "禁止新增，等待重大风险解除"
        elif risk_control.get("level") == "高" or score_value < 40:
            buy_zone = "暂不新增，等待风险解除"
        elif score_value >= 78:
            buy_zone = _format_range(support, _min_present(mid, ma20, price))
        elif score_value >= 62:
            buy_zone = _format_range(support, mid or ma20)
        else:
            buy_zone = "等回踩支撑或放量突破确认"

        if confirm_level is not None and price is not None and price >= confirm_level and score_value >= 60:
            add_condition = f"已站上确认位 {confirm_level:.2f}，仍需观察量能和风险事件"
        elif confirm_level is not None:
            add_condition = f"放量站回 {confirm_level:.2f} 上方再考虑加仓"
        else:
            add_condition = "等待关键均线和量价确认"

        take_profit_1 = risk_control.get("take_profit_1")
        trim_condition = (
            f"接近 {_format_level(take_profit_1)} 压力位先观察减仓"
            if _safe_float(take_profit_1) is not None
            else "等待形成明确压力位"
        )
        return {
            "current_action": risk_control.get("final_action") or action,
            "buy_zone": buy_zone,
            "add_condition": add_condition,
            "stop_loss": risk_control.get("stop_loss"),
            "take_profit_1": take_profit_1,
            "take_profit_2": risk_control.get("take_profit_2"),
            "trim_condition": trim_condition,
            "position": risk_control.get("max_position") or position or "--",
            "risk_note": "硬拦截已触发" if risk_control.get("hard_block") else "最终仓位受执行风控约束",
            "data_basis": risk_control.get("data_basis") or data_basis,
        }

    fallback_buffer = ((price or support or resistance or 0) * 0.02)
    buffer = _safe_float(buffer)
    if buffer is None:
        buffer = fallback_buffer
    confirm_level = max([value for value in (mid, ma20, ma60) if value is not None], default=None)
    stop_anchor = support if support is not None else ma60
    stop_loss = stop_anchor - buffer if stop_anchor is not None else None
    take_profit_1 = resistance
    take_profit_2 = None
    if resistance is not None and support is not None:
        take_profit_2 = resistance + max(0, resistance - support) * 0.5

    confidence_value = int(confidence or 0)
    if risk_level == "高" or score_value < 40:
        current_action = "降仓回避"
        buy_zone = "暂不新增，等待风险解除"
    elif confidence_value < 55:
        current_action = "等待确认"
        buy_zone = "等待数据确认后再定"
    elif score_value >= 78:
        current_action = "积极关注 / 分批建仓"
        buy_zone = _format_range(support, _min_present(mid, ma20, price))
    elif score_value >= 62:
        current_action = "轻仓试探"
        buy_zone = _format_range(support, mid or ma20)
    else:
        current_action = action
        buy_zone = "等回踩支撑或放量突破确认"

    if price is not None and confirm_level is not None and price >= confirm_level and score_value >= 60:
        add_condition = f"已站上确认位 {confirm_level:.2f}，仍需观察量能和风险事件"
    elif confirm_level is not None:
        add_condition = f"放量站回 {confirm_level:.2f} 上方再考虑加仓"
    else:
        add_condition = "等待关键均线和量价确认"

    trim_condition = (
        f"接近 {take_profit_1:.2f} 压力位先观察减仓"
        if take_profit_1 is not None
        else "等待形成明确压力位"
    )
    return {
        "current_action": current_action,
        "buy_zone": buy_zone,
        "add_condition": add_condition,
        "stop_loss": _round_price(stop_loss),
        "take_profit_1": _round_price(take_profit_1),
        "take_profit_2": _round_price(take_profit_2),
        "trim_condition": trim_condition,
        "position": position or "--",
        "risk_note": "高风险优先控制回撤" if risk_level == "高" else "按计划分批，不追高满仓",
        "data_basis": data_basis,
    }


def _buy_zone(
    price: float | None,
    support: float | None,
    boll_mid: float | None,
    ma20: float | None,
    strategy: str,
) -> tuple[float | None, float | None]:
    if price is None:
        return None, None
    anchors = [value for value in (support, boll_mid, ma20) if value is not None and value > 0]
    if anchors:
        anchor = max(min(anchors), price * 0.9)
        low = min(anchor, price * 0.98)
    else:
        low = price * 0.97
    upper_factor = 1.015 if "激进" in str(strategy) else 1.01
    high = max(low, price * upper_factor)
    if high > price * 1.04:
        high = price * 1.04
    return low, high


def _stop_loss(price: float | None, support: float | None, ma20: float | None, ma60: float | None) -> float | None:
    anchors = [value for value in (support, ma20, ma60) if value is not None and value > 0]
    if anchors:
        anchor = min(anchors)
    elif price is not None:
        anchor = price
    else:
        return None
    return anchor * 0.97


def _take_profit_1(price: float | None, resistance: float | None, boll_upper: float | None) -> float | None:
    candidates = [value for value in (resistance, boll_upper) if value is not None and value > 0]
    if candidates:
        target = max(candidates)
        if price is not None:
            target = max(target, price * 1.06)
        return target
    return price * 1.08 if price is not None else None


def _take_profit_2(price: float | None, take_profit_1: float | None, support: float | None) -> float | None:
    if take_profit_1 is None:
        return price * 1.15 if price is not None else None
    if price is not None and support is not None:
        return take_profit_1 + max(price - support, price * 0.05)
    return take_profit_1 * 1.06


def _add_condition(ma5: float | None, ma10: float | None, ma20: float | None, strategy: str) -> str:
    if ma5 is not None and ma10 is not None and ma20 is not None:
        return f"收盘价放量站稳 MA5/MA10，且不跌破 MA20 {ma20:.2f} 后再加仓"
    if "突破" in str(strategy):
        return "突破后回踩不破前高或短期均线，再考虑加仓"
    return "放量站稳短期均线后再加仓，未确认前只做观察"


def _invalid_conditions(stop_loss: float | None, ma20: float | None, ma60: float | None, stock: dict[str, Any]) -> list[str]:
    conditions = []
    if stop_loss is not None:
        conditions.append(f"收盘跌破止损线 {stop_loss:.2f} 且次日无法收回")
    if ma20 is not None:
        conditions.append(f"收盘跌破 MA20 {ma20:.2f} 且量能放大")
    if ma60 is not None:
        conditions.append(f"跌破 MA60 {ma60:.2f} 则进入防御观察")
    risky = _risk_notice(stock)
    if risky:
        conditions.append(f"出现重大风险公告：{risky}")
    else:
        conditions.append("出现重大风险公告或策略核心条件失效")
    return conditions[:4]


def _position_hint(strategy: str, stock: dict[str, Any]) -> str:
    score = _safe_float(stock.get("score"))
    if "激进" in str(strategy):
        return "观察仓-1成"
    if score is not None and score >= 85:
        return "1-2成"
    return "观察仓"


def _risk_notice(stock: dict[str, Any]) -> str | None:
    risk_events = stock.get("risk_events") if isinstance(stock.get("risk_events"), dict) else None
    if risk_events is None and isinstance(stock.get("extended_info"), dict):
        risk_events = stock["extended_info"].get("risk_events")
    announcements = (risk_events or {}).get("announcements") if isinstance(risk_events, dict) else []
    keywords = ("减持", "立案", "处罚", "风险", "诉讼", "亏损", "退市", "监管", "问询", "警示")
    for item in announcements or []:
        text = " ".join(str(item.get(key) or "") for key in ("title", "type", "summary", "content")) if isinstance(item, dict) else str(item or "")
        if any(keyword in text for keyword in keywords):
            return text[:60]
    return None


def _first_number(mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _safe_float(mapping.get(key))
        if value is not None and value > 0:
            return value
    return None


def _max_below_or_equal(price: float | None, values: list[float | None]) -> float | None:
    candidates = [value for value in values if value is not None and value > 0 and (price is None or value <= price)]
    return max(candidates) if candidates else None


def _min_above_or_equal(price: float | None, values: list[float | None]) -> float | None:
    candidates = [value for value in values if value is not None and value > 0 and (price is None or value >= price)]
    return min(candidates) if candidates else None


def _format_zone(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "--"
    return f"{low:.2f}-{high:.2f}"


def _format_range(low: Any, high: Any) -> str:
    low_num = _safe_float(low)
    high_num = _safe_float(high)
    if low_num is None and high_num is None:
        return "--"
    if low_num is None:
        return f"≤ {_format_level(high_num)}"
    if high_num is None:
        return f"≥ {_format_level(low_num)}"
    if low_num > high_num:
        low_num, high_num = high_num, low_num
    return f"{low_num:.2f} ~ {high_num:.2f}"


def _format_level(value: Any) -> str:
    numeric = _safe_float(value)
    return "--" if numeric is None else f"{numeric:.2f}"


def _min_present(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _first_level_from_zone(value: Any, *, index: int) -> float | None:
    text = str(value or "")
    numbers = []
    for chunk in text.replace("~", " ").replace("-", " ").replace("≤", " ").replace("≥", " ").split():
        number = _safe_float(chunk)
        if number is not None:
            numbers.append(number)
    if not numbers:
        return None
    if index >= len(numbers):
        return numbers[-1]
    return numbers[index]


def _round_price(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None
