"""Decision dashboard cards for single-stock analysis results."""
from __future__ import annotations

import html
import math
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


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _clamp_score(value: float | int | None) -> int:
    if value is None:
        return 50
    return int(max(0, min(100, round(float(value)))))


def _fmt_range(low: Any, high: Any) -> str:
    low_num = _num(low)
    high_num = _num(high)
    if low_num is None and high_num is None:
        return "--"
    if low_num is None:
        return f"≤ {_fmt_level(high_num)}"
    if high_num is None:
        return f"≥ {_fmt_level(low_num)}"
    if low_num > high_num:
        low_num, high_num = high_num, low_num
    return f"{low_num:.2f} ~ {high_num:.2f}"


def _latest_value(data: Any, key: str) -> float | None:
    try:
        if data is None or data.empty or key not in data.columns:
            return None
        return _num(data.iloc[-1].get(key))
    except Exception:
        return None


def _atr_buffer(data: Any, price: float | None) -> float | None:
    """Use real OHLC data to derive a small stop buffer. No synthetic quote data."""
    try:
        if data is None or data.empty or not {"high", "low", "close"} <= set(data.columns):
            return price * 0.02 if price else None
        recent = data.tail(14)
        ranges = (recent["high"] - recent["low"]).dropna()
        if ranges.empty:
            return price * 0.02 if price else None
        atr_like = float(ranges.mean())
        if atr_like <= 0:
            return price * 0.02 if price else None
        return min(atr_like * 0.5, price * 0.03) if price else atr_like * 0.5
    except Exception:
        return price * 0.02 if price else None


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


def build_trade_plan(snapshot: dict[str, Any], data: Any = None) -> dict[str, Any]:
    """Build a deterministic trade plan from real quote, K-line and indicator data."""
    key_levels = snapshot.get("key_levels") or {}
    price = _num(key_levels.get("price"))
    support = _num(key_levels.get("support"))
    mid = _num(key_levels.get("mid"))
    resistance = _num(key_levels.get("resistance"))
    ma20 = _num(key_levels.get("ma20"))
    ma60 = _latest_value(data, "ma60")
    score = int(snapshot.get("score") or 0)
    risk_level = snapshot.get("risk_level") or "中"
    confidence = int(snapshot.get("confidence") or 0)
    action = snapshot.get("action") or "等待确认"
    buffer = _atr_buffer(data, price) or ((price or support or resistance or 0) * 0.02)

    confirm_candidates = [value for value in (mid, ma20, ma60) if value is not None]
    confirm_level = max(confirm_candidates) if confirm_candidates else None
    stop_anchor = support if support is not None else ma60
    stop_loss = stop_anchor - buffer if stop_anchor is not None else None
    take_profit_1 = resistance
    take_profit_2 = None
    if resistance is not None and support is not None:
        take_profit_2 = resistance + max(0, resistance - support) * 0.5

    if risk_level == "高" or score < 40:
        current_action = "降仓回避"
        buy_zone = "暂不新增，等待风险解除"
    elif confidence < 55:
        current_action = "等待确认"
        buy_zone = "等待数据确认后再定"
    elif score >= 78:
        current_action = "积极关注 / 分批建仓"
        buy_zone = _fmt_range(support, min(value for value in (mid, ma20, price) if value is not None) if any(value is not None for value in (mid, ma20, price)) else None)
    elif score >= 62:
        current_action = "轻仓试探"
        buy_zone = _fmt_range(support, mid or ma20)
    else:
        current_action = action
        buy_zone = "等回踩支撑或放量突破确认"

    if price is not None and confirm_level is not None and price >= confirm_level and score >= 60:
        add_condition = f"已站上确认位 {confirm_level:.2f}，仍需观察量能和风险事件"
    elif confirm_level is not None:
        add_condition = f"放量站回 {confirm_level:.2f} 上方再考虑加仓"
    else:
        add_condition = "等待关键均线和量价确认"

    if take_profit_1 is not None:
        trim_condition = f"接近 {take_profit_1:.2f} 压力位先观察减仓"
    else:
        trim_condition = "等待形成明确压力位"

    return {
        "current_action": current_action,
        "buy_zone": buy_zone,
        "add_condition": add_condition,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "trim_condition": trim_condition,
        "position": snapshot.get("position") or "--",
        "risk_note": "高风险优先控制回撤" if risk_level == "高" else "按计划分批，不追高满仓",
        "data_basis": "真实行情/K线/指标推导，未使用模拟或随机行情",
    }


def _fmt_percent(value: Any, *, signed: bool = False) -> str:
    numeric = _num(value)
    if numeric is None:
        return "暂无"
    prefix = "+" if signed and numeric > 0 else ""
    return f"{prefix}{numeric:.2f}%"


def _fmt_money(value: Any) -> str:
    numeric = _num(value)
    if numeric is None:
        return "暂无"
    absolute = abs(numeric)
    sign = "-" if numeric < 0 else ""
    if absolute >= 100_000_000:
        return f"{sign}{absolute / 100_000_000:.2f}亿"
    if absolute >= 10_000:
        return f"{sign}{absolute / 10_000:.2f}万"
    return f"{numeric:.2f}"


def _period_return(data: Any, periods: int) -> float | None:
    try:
        if data is None or data.empty or "close" not in data.columns:
            return None
        close = data["close"].dropna()
        if len(close) <= periods:
            return None
        previous = float(close.iloc[-periods - 1])
        latest = float(close.iloc[-1])
        if previous <= 0:
            return None
        return (latest / previous - 1) * 100
    except Exception:
        return None


def _calculate_beta(data: Any, benchmark_data: Any, periods: int = 120) -> float | None:
    try:
        if data is None or benchmark_data is None:
            return None
        if data.empty or benchmark_data.empty or "close" not in data.columns or "close" not in benchmark_data.columns:
            return None
        stock_returns = data["close"].dropna().pct_change().dropna().tail(periods)
        benchmark_returns = benchmark_data["close"].dropna().pct_change().dropna().tail(periods)
        if len(stock_returns) < 30 or len(benchmark_returns) < 30:
            return None
        aligned = stock_returns.rename("stock").to_frame().join(
            benchmark_returns.rename("benchmark"),
            how="inner",
        ).dropna()
        if len(aligned) < 30:
            return None
        variance = float(aligned["benchmark"].var())
        if variance <= 0:
            return None
        covariance = float(aligned["stock"].cov(aligned["benchmark"]))
        return covariance / variance
    except Exception:
        return None


def _max_drawdown(data: Any) -> float | None:
    try:
        if data is None or data.empty or "close" not in data.columns:
            return None
        close = data["close"].dropna()
        if close.empty:
            return None
        return float((close / close.cummax() - 1).min() * 100)
    except Exception:
        return None


def _latest_indicator(data: Any, *keys: str) -> float | None:
    for key in keys:
        value = _latest_value(data, key)
        if value is not None:
            return value
    return None


def _volume_weighted_cost(data: Any, periods: int = 20) -> float | None:
    try:
        if data is None or data.empty or not {"close", "volume"} <= set(data.columns):
            return None
        recent = data[["close", "volume"]].dropna().tail(periods)
        if recent.empty:
            return None
        volume_sum = float(recent["volume"].sum())
        if volume_sum <= 0:
            return None
        return float((recent["close"] * recent["volume"]).sum() / volume_sum)
    except Exception:
        return None


def _eps_growth_from_consensus(extended_info: dict[str, Any]) -> float | None:
    values = ((extended_info.get("research") or {}).get("eps_consensus") or {}).get("values") or {}
    eps_points = [(str(label), _num(value)) for label, value in values.items()]
    eps_points = [(label, value) for label, value in eps_points if value is not None]
    if len(eps_points) < 2:
        return None
    eps_points.sort(key=lambda item: item[0])
    previous = eps_points[0][1]
    latest = eps_points[-1][1]
    if previous is None or latest is None or previous <= 0:
        return None
    return (latest / previous - 1) * 100


def _consensus_eps_for_year(extended_info: dict[str, Any], target_year: str = "2026") -> float | None:
    values = ((extended_info.get("research") or {}).get("eps_consensus") or {}).get("values") or {}
    for label, value in values.items():
        label_text = str(label)
        if target_year in label_text and ("EPS" in label_text.upper() or "每股收益" in label_text):
            eps = _num(value)
            if eps is not None and eps > 0:
                return eps
    return None


def _profit_cagr_from_financial_history(extended_info: dict[str, Any], periods: int = 3) -> float | None:
    history = ((extended_info.get("financial") or {}).get("history") or [])
    if not isinstance(history, list) or len(history) < 2:
        return None

    points = []
    for row in history:
        if not isinstance(row, dict):
            continue
        value = None
        for key, raw_value in row.items():
            key_text = str(key)
            if any(alias in key_text for alias in ("归母净利润", "归属于母公司所有者的净利润", "PARENT_NETPROFIT")):
                value = _num(raw_value)
                break
        if value is not None:
            points.append(value)

    if len(points) < 2:
        return None
    points = points[-periods:]
    first = points[0]
    last = points[-1]
    years = len(points) - 1
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _astock_peg_from_sources(
    extended_info: dict[str, Any],
    profile: dict[str, Any],
    price: float | None = None,
) -> tuple[float | None, str | None, str]:
    price = _num(price) or _num(profile.get("latest_price") or profile.get("price"))
    eps_2026 = _consensus_eps_for_year(extended_info, "2026")
    profit_cagr = _profit_cagr_from_financial_history(extended_info, periods=3)
    if price is None or price <= 0:
        return None, None, "缺当前价，无法按 astock-peg 口径计算"
    if eps_2026 is None:
        return None, None, "缺2026一致预期EPS，无法按 astock-peg 口径计算"
    if profit_cagr is None or profit_cagr <= 0:
        return None, None, "缺近3年归母净利润正增长CAGR，无法按 astock-peg 口径计算"
    forward_pe = price / eps_2026
    return forward_pe / (profit_cagr * 100), "astock-peg", "前瞻PE=当前价/2026一致预期EPS；PEG=前瞻PE/近3年归母净利润CAGR"


def _growth_from_financial_metrics(extended_info: dict[str, Any], profile: dict[str, Any]) -> tuple[float | None, str | None]:
    metrics = ((extended_info.get("financial") or {}).get("metrics") or {})
    candidates = [
        ("归属于母公司所有者的净利润同比", "财务摘要归母净利润同比"),
        ("归属母公司股东的净利润同比", "财务摘要归母净利润同比"),
        ("归母净利润增长率", "财务摘要归母净利润增长率"),
        ("归母净利润增长率(%)", "财务摘要归母净利润增长率"),
        ("归母净利润同比", "财务摘要归母净利润同比"),
        ("PARENT_NETPROFIT_YOY", "财务摘要归母净利润同比"),
        ("净利润增长率", "财务摘要净利润增长率"),
        ("净利润增长率(%)", "财务摘要净利润增长率"),
        ("净利润同比", "财务摘要净利润同比"),
        ("扣非净利润同比", "财务摘要扣非净利润同比"),
        ("扣非归母净利润同比", "财务摘要扣非归母净利润同比"),
        ("EPS同比", "财务摘要EPS同比"),
        ("每股收益同比", "财务摘要EPS同比"),
        ("基本每股收益同比", "财务摘要EPS同比"),
        ("每股收益增长率", "财务摘要EPS增长率"),
        ("营业总收入同比", "财务摘要营收同比"),
        ("营业收入同比", "财务摘要营收同比"),
    ]
    for key, label in candidates:
        for source in (metrics, profile):
            if not isinstance(source, dict):
                continue
            for source_key, raw_value in source.items():
                if key == str(source_key) or key in str(source_key):
                    value = _num(raw_value)
                    if value is not None:
                        return value, label
    history = ((extended_info.get("financial") or {}).get("history") or [])
    if isinstance(history, list) and len(history) >= 2:
        rows = [row for row in history if isinstance(row, dict)]
        for key, label in [
            ("归母净利润", "财务摘要近两期归母净利润增速"),
            ("净利润", "财务摘要近两期净利润增速"),
            ("每股收益", "财务摘要近两期EPS增速"),
            ("EPS", "财务摘要近两期EPS增速"),
        ]:
            points = []
            for row in rows:
                matched_value = None
                for row_key, row_value in row.items():
                    if key == str(row_key) or key in str(row_key):
                        matched_value = _num(row_value)
                        break
                if matched_value is not None:
                    points.append(matched_value)
            if len(points) >= 2 and points[-2] > 0:
                growth = (points[-1] / points[-2] - 1) * 100
                return growth, label
    return None, None


def _direct_peg_from_sources(extended_info: dict[str, Any], profile: dict[str, Any]) -> tuple[float | None, str | None]:
    candidates = [
        (profile, "基础资料"),
        (extended_info.get("profile") or {}, "扩展基础资料"),
        ((extended_info.get("financial") or {}).get("metrics") or {}, "财务摘要"),
        ((extended_info.get("research") or {}).get("eps_consensus") or {}, "一致预期"),
    ]
    for source, label in candidates:
        if not isinstance(source, dict):
            continue
        for key, raw_value in source.items():
            key_text = str(key).strip().lower()
            if key_text in {"peg", "peg_ratio"} or "peg" in key_text or "市盈率相对盈利增长比率" in str(key):
                value = _num(raw_value)
                if value is not None and value > 0:
                    return value, label
    return None, None


def _peg_from_sources(
    extended_info: dict[str, Any],
    profile: dict[str, Any],
    price: float | None = None,
) -> tuple[float | None, str | None, str]:
    astock_peg, astock_source, astock_note = _astock_peg_from_sources(extended_info, profile, price=price)
    if astock_peg is not None:
        return astock_peg, astock_source, astock_note

    pe = _num(profile.get("pe_ttm") or profile.get("pe"))
    eps_consensus = (extended_info.get("research") or {}).get("eps_consensus") or {}
    direct_peg, direct_source = _direct_peg_from_sources(extended_info, profile)
    if direct_peg is not None:
        return direct_peg, direct_source, f"{astock_note}；改用{direct_source}PEG字段"
    if pe is None:
        return None, None, "缺PE，暂不计算"

    eps_growth = _eps_growth_from_consensus(extended_info)
    if eps_growth is not None:
        if eps_growth > 0:
            return pe / eps_growth, "一致预期EPS增速", "PE ÷ 一致预期EPS增速"
        return None, "一致预期EPS增速", "一致预期EPS增速不为正，暂不计算"

    financial_growth, financial_source = _growth_from_financial_metrics(extended_info, profile)
    if financial_growth is not None:
        if financial_growth > 0:
            return pe / financial_growth, financial_source, f"PE ÷ {financial_source}"
        return None, financial_source, f"{financial_source}不为正，暂不计算"

    if eps_consensus.get("status") == "source_failed":
        return None, None, f"已有PE；EPS源失败：{eps_consensus.get('reason') or '接口异常'}"
    if eps_consensus.get("status") == "source_empty":
        return None, None, eps_consensus.get("reason") or "已有PE，EPS源未返回可计算字段"
    return None, None, "已有PE，缺EPS/财务增速，不编造"


def _status_label(status: str | None) -> str:
    labels = {
        "ok": "已获取",
        "derived": "已推导",
        "missing": "无字段",
        "source_empty": "源无数据",
        "source_failed": "接口失败",
        "insufficient": "样本不足",
    }
    return labels.get(status or "", "待确认")


def _metric_status(status: str, note: str) -> dict[str, str]:
    return {"status": status, "status_label": _status_label(status), "note": note}


def _extract_dividend_yield(
    extended_info: dict[str, Any],
    profile: dict[str, Any],
    price: float | None = None,
) -> tuple[float | None, dict[str, str]]:
    candidates = [
        (profile, "dividend_yield", "基础资料"),
        (profile, "股息率", "基础资料"),
        (profile, "dividend", "基础资料"),
        (extended_info.get("dividend") or {}, "dividend_yield", "分红数据"),
        (extended_info.get("dividend") or {}, "股息率", "分红数据"),
        (extended_info.get("profile") or {}, "dividend_yield", "扩展基础资料"),
        (extended_info.get("profile") or {}, "股息率", "扩展基础资料"),
    ]
    for source, key, label in candidates:
        if not isinstance(source, dict):
            continue
        value = _num(source.get(key))
        if value is not None:
            return value, _metric_status("ok", f"来自{label}")
    dividend = extended_info.get("dividend") or {}
    if isinstance(dividend, dict) and dividend.get("status") == "source_failed":
        reason = dividend.get("reason") or "分红接口请求失败"
        return None, _metric_status("source_failed", f"{dividend.get('source') or '分红数据源'}失败：{reason}")
    cash_per_share = _num(dividend.get("cash_dividend_per_share"))
    if cash_per_share is not None and price is not None and price > 0:
        return cash_per_share / price * 100, _metric_status(
            "derived",
            f"来自{dividend.get('source') or '历史分红'}按现价推导",
        )
    annual_per_share = _num(dividend.get("annual_dividend_per_share"))
    if annual_per_share is not None and price is not None and price > 0:
        return annual_per_share / price * 100, _metric_status(
            "derived",
            f"来自{dividend.get('source') or '历史分红摘要'}按年均股息推导",
        )
    if isinstance(dividend, dict) and dividend:
        reason = dividend.get("reason") or dividend.get("note") or "分红源返回字段不足"
        return None, _metric_status("source_empty", str(reason))
    return None, _metric_status("missing", "当前公开数据源未返回股息率/现金分红字段")


def _beta_status(data: Any, benchmark_data: Any, beta: float | None) -> dict[str, str]:
    if beta is not None:
        return _metric_status("ok", "相对沪深300，真实K线收益计算")
    if data is None or getattr(data, "empty", True) or "close" not in getattr(data, "columns", []):
        return _metric_status("missing", "本股K线未返回，无法计算Beta")
    if benchmark_data is None or getattr(benchmark_data, "empty", True) or "close" not in getattr(benchmark_data, "columns", []):
        return _metric_status("source_failed", "沪深300基准K线未返回，无法计算Beta")
    return _metric_status("insufficient", "本股或基准K线样本不足30根")


def _build_signal_state(snapshot: dict[str, Any], data: Any = None) -> dict[str, Any]:
    key_levels = snapshot.get("key_levels") or {}
    price = _num(key_levels.get("price"))
    support = _num(key_levels.get("support"))
    resistance = _num(key_levels.get("resistance"))
    ma20 = _num(key_levels.get("ma20"))
    ma60 = _latest_value(data, "ma60")
    rsi = _latest_indicator(data, "rsi", "RSI", "rsi_6", "RSI6")
    score = int(snapshot.get("score") or 0)
    confidence = int(snapshot.get("confidence") or 0)
    risk_level = snapshot.get("risk_level") or "中"

    confirm_candidates = [value for value in (ma20, ma60, (support * 1.03 if support else None)) if value is not None]
    confirm_level = max(confirm_candidates) if confirm_candidates else None

    if risk_level == "高" or score < 40:
        name = "风险回避"
        tone = "bearish"
        reason = "综合评分或风险事件不支持新增仓位"
    elif price is None or confidence < 55:
        name = "防御观望"
        tone = "neutral"
        reason = "价格或置信度不足，先等确认"
    elif resistance is not None and price >= resistance * 0.98:
        name = "压力减仓"
        tone = "watch"
        reason = "价格接近压力位，优先保护利润"
    elif rsi is not None and rsi >= 75:
        name = "压力减仓"
        tone = "watch"
        reason = "RSI 进入高位区，警惕放量滞涨"
    elif support is not None and price <= support * 1.04 and score >= 50:
        name = "底部观察"
        tone = "watch"
        reason = "接近支撑区，适合观察止跌信号"
    elif confirm_level is not None and price >= confirm_level and score >= 70:
        name = "趋势持有"
        tone = "bullish"
        reason = "价格站上关键均线/确认位，趋势延续"
    elif score >= 62:
        name = "试探建仓"
        tone = "watch"
        reason = "评分达标但仍需关键位和量能确认"
    else:
        name = "防御观望"
        tone = "neutral"
        reason = "信号尚未形成足够胜率"

    triggers = []
    if confirm_level is not None:
        triggers.append(f"放量站稳 {confirm_level:.2f} 上方 → 进入趋势持有/加仓观察")
    if support is not None:
        triggers.append(f"跌破 {support:.2f} 且无法收回 → 降仓或止损")
    if resistance is not None:
        triggers.append(f"接近 {resistance:.2f} 压力位 → 观察减仓")
    if rsi is not None:
        triggers.append(f"RSI 当前 {rsi:.1f}，高于75偏热，低于35偏冷")
    if not triggers:
        triggers.append("等待真实 K 线、均线、量能或资金流给出下一触发条件")

    return {
        "name": name,
        "tone": tone,
        "reason": reason,
        "triggers": triggers[:4],
        "data_basis": "状态机基于真实价格、K线、均线、RSI、支撑/压力和风险等级推导",
    }


def _build_core_metrics(
    snapshot: dict[str, Any],
    data: Any = None,
    benchmark_data: Any = None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    extended_info = extended_info or {}
    profile = profile or {}
    pe = _num(profile.get("pe_ttm") or profile.get("pe"))
    eps_consensus = (extended_info.get("research") or {}).get("eps_consensus") or {}
    price = _num((snapshot.get("key_levels") or {}).get("price"))
    peg, peg_source, peg_note = _peg_from_sources(extended_info, profile, price=price)
    if peg is not None:
        peg_status = "derived"
    elif pe is None:
        if eps_consensus.get("status") == "source_failed":
            peg_note = f"缺PE；EPS源失败：{eps_consensus.get('reason') or '接口异常'}"
            peg_status = "source_failed"
        elif eps_consensus.get("status") == "source_empty":
            peg_note = eps_consensus.get("reason") or "缺PE和EPS增速，不编造"
            peg_status = "source_empty"
        else:
            peg_note = "缺PE和EPS增速，不编造"
            peg_status = "missing"
    elif peg_source is None and eps_consensus.get("status") in {"source_failed", "source_empty"}:
        if eps_consensus.get("status") == "source_failed":
            peg_status = "source_failed"
        else:
            peg_status = "source_empty"
    else:
        peg_status = "source_empty"
    dividend_yield, dividend_status = _extract_dividend_yield(extended_info, profile, price)
    return_20d = _period_return(data, 20)
    return_60d = _period_return(data, 60)
    drawdown = _max_drawdown(data)
    beta = _calculate_beta(data, benchmark_data)
    beta_status = _beta_status(data, benchmark_data, beta)
    main_ratio = _num((extended_info.get("fund_flow") or {}).get("main_net_inflow_ratio"))
    capital_cost = _volume_weighted_cost(data, 20)

    metrics = [
        {
            "name": "PEG",
            "value": f"{peg:.2f}" if peg is not None else "暂无",
            "note": peg_note,
            "status": peg_status,
            "status_label": _status_label(peg_status),
        },
        {
            "name": "相对强弱",
            "value": _fmt_percent(return_20d, signed=True),
            "note": "本股20日真实K线收益，非全市场RPS" if return_20d is not None else "需至少21根K线",
            "status": "ok" if return_20d is not None else "insufficient",
            "status_label": _status_label("ok" if return_20d is not None else "insufficient"),
        },
        {
            "name": "Beta",
            "value": f"{beta:.2f}" if beta is not None else "暂无",
            "note": beta_status["note"],
            "status": beta_status["status"],
            "status_label": beta_status["status_label"],
        },
        {
            "name": "股息率",
            "value": _fmt_percent(dividend_yield),
            "note": dividend_status["note"],
            "status": dividend_status["status"],
            "status_label": dividend_status["status_label"],
        },
        {
            "name": "主力成本",
            "value": _fmt_level(capital_cost) if capital_cost is not None else "暂无",
            "note": "20日量价成本，模型推断" if capital_cost is not None else "需成交量数据",
            "status": "derived" if capital_cost is not None else "missing",
            "status_label": _status_label("derived" if capital_cost is not None else "missing"),
        },
        {
            "name": "资金态度",
            "value": _fmt_percent(main_ratio, signed=True),
            "note": "主力净占比，真实资金流；态度为模型推断" if main_ratio is not None else "资金流暂无",
            "status": "derived" if main_ratio is not None else "source_empty",
            "status_label": _status_label("derived" if main_ratio is not None else "source_empty"),
        },
        {
            "name": "60日收益",
            "value": _fmt_percent(return_60d, signed=True),
            "note": "真实K线周期收益" if return_60d is not None else "需至少61根K线",
            "status": "ok" if return_60d is not None else "insufficient",
            "status_label": _status_label("ok" if return_60d is not None else "insufficient"),
        },
        {
            "name": "最大回撤",
            "value": _fmt_percent(drawdown, signed=True),
            "note": "样本区间历史回撤" if drawdown is not None else "K线暂无",
            "status": "ok" if drawdown is not None else "missing",
            "status_label": _status_label("ok" if drawdown is not None else "missing"),
        },
    ]
    return metrics


def _build_capital_trace(
    extended_info: dict[str, Any] | None = None,
    data: Any = None,
    profile: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    extended_info = extended_info or {}
    profile = profile or {}
    fund_flow = extended_info.get("fund_flow") or {}
    rows = []

    def add_row(label: str, value: str, impact: str, basis: str) -> None:
        rows.append({"label": label, "value": value, "impact": impact, "basis": basis})

    main_flow = _num(fund_flow.get("main_net_inflow"))
    five_day_flow = _num(fund_flow.get("five_day_main_net_inflow"))
    super_flow = _num(fund_flow.get("super_large_net_inflow"))
    large_flow = _num(fund_flow.get("large_net_inflow"))
    main_ratio = _num(fund_flow.get("main_net_inflow_ratio"))
    turnover = _num(profile.get("turnover_rate"))
    capital_cost = _volume_weighted_cost(data, 20)

    add_row(
        "当日主力净流入",
        _fmt_money(main_flow),
        "偏多" if main_flow and main_flow > 0 else "偏空" if main_flow and main_flow < 0 else "暂无",
        "公开资金流",
    )
    add_row(
        "近5日主力净流入",
        _fmt_money(five_day_flow),
        "连续流入" if five_day_flow and five_day_flow > 0 else "连续流出" if five_day_flow and five_day_flow < 0 else "暂无",
        "公开资金流",
    )
    add_row(
        "超大/大单合计",
        _fmt_money((super_flow or 0) + (large_flow or 0)) if super_flow is not None or large_flow is not None else "暂无",
        "大单承接" if (super_flow or 0) + (large_flow or 0) > 0 else "大单分歧" if super_flow is not None or large_flow is not None else "暂无",
        "公开资金流",
    )
    add_row(
        "主力净占比",
        _fmt_percent(main_ratio, signed=True),
        "净买占优" if main_ratio and main_ratio > 0 else "净卖占优" if main_ratio and main_ratio < 0 else "暂无",
        "公开资金流",
    )
    add_row(
        "换手率",
        _fmt_percent(turnover),
        "活跃" if turnover and turnover >= 5 else "温和" if turnover is not None else "暂无",
        "公开行情/基础资料",
    )
    add_row(
        "20日量价成本",
        _fmt_level(capital_cost) if capital_cost is not None else "暂无",
        "模型推断",
        "真实收盘价×成交量推导",
    )
    return rows


def _score_valuation(profile: dict[str, Any]) -> tuple[int, str]:
    pe = _num(profile.get("pe_ttm") or profile.get("pe"))
    pb = _num(profile.get("pb"))
    score = 50
    notes = []
    if pe is not None:
        if 0 < pe <= 20:
            score += 18
            notes.append(f"PE {pe:.1f} 偏合理")
        elif 20 < pe <= 40:
            score += 4
            notes.append(f"PE {pe:.1f} 中性")
        elif pe > 60 or pe <= 0:
            score -= 18
            notes.append(f"PE {pe:.1f} 压力较大")
    if pb is not None:
        if 0 < pb <= 2.5:
            score += 12
            notes.append(f"PB {pb:.1f} 可控")
        elif pb > 5:
            score -= 12
            notes.append(f"PB {pb:.1f} 偏高")
    return _clamp_score(score), "；".join(notes) or "估值数据暂无"


def _score_growth(extended_info: dict[str, Any], profile: dict[str, Any]) -> tuple[int, str]:
    metrics = ((extended_info.get("financial") or {}).get("metrics") or {})
    score = 50
    notes = []
    for key, label in [
        ("归母净利润", "净利润"),
        ("经营现金流量净额", "经营现金流"),
        ("每股收益", "EPS"),
        ("营业总收入", "营收"),
    ]:
        value = _num(metrics.get(key) or profile.get(key))
        if value is not None:
            score += 10 if value > 0 else -12
            notes.append(f"{label}{'为正' if value > 0 else '承压'}")
    return _clamp_score(score), "；".join(notes[:3]) or "成长/财务数据暂无"


def _score_trend(snapshot: dict[str, Any], data: Any) -> tuple[int, str]:
    score = 50
    recommendation = str(snapshot.get("recommendation") or "")
    price = _num((snapshot.get("key_levels") or {}).get("price"))
    ma20 = _num((snapshot.get("key_levels") or {}).get("ma20"))
    ma60 = _latest_value(data, "ma60")
    if "偏多" in recommendation:
        score += 22
    if "偏空" in recommendation:
        score -= 22
    if price is not None and ma20 is not None:
        score += 10 if price >= ma20 else -10
    if price is not None and ma60 is not None:
        score += 8 if price >= ma60 else -8
    note = f"信号 {recommendation or '观望'}"
    if price is not None and ma20 is not None:
        note += f"；现价{'站上' if price >= ma20 else '跌破'}MA20"
    return _clamp_score(score), note


def _score_safety(snapshot: dict[str, Any], data: Any) -> tuple[int, str]:
    score = 72
    risks = snapshot.get("risk_alerts") or snapshot.get("risks") or []
    risk_level = snapshot.get("risk_level")
    if risk_level == "高":
        score -= 35
    elif risk_level == "中":
        score -= 15
    score -= min(25, len(risks) * 6)
    try:
        if data is not None and not data.empty and "close" in data.columns:
            close = data["close"].dropna()
            drawdown = (close / close.cummax() - 1).min() * 100
            if drawdown < -25:
                score -= 12
            elif drawdown > -10:
                score += 8
            note = f"风险等级 {risk_level or '--'}；最大回撤 {drawdown:.1f}%"
        else:
            note = f"风险等级 {risk_level or '--'}"
    except Exception:
        note = f"风险等级 {risk_level or '--'}"
    return _clamp_score(score), note


def _score_capital(extended_info: dict[str, Any], profile: dict[str, Any]) -> tuple[int, str]:
    fund_flow = extended_info.get("fund_flow") or {}
    main_flow = _num(fund_flow.get("main_net_inflow"))
    main_ratio = _num(fund_flow.get("main_net_inflow_ratio"))
    five_day = _num(fund_flow.get("five_day_main_net_inflow"))
    turnover = _num(profile.get("turnover_rate"))
    score = 50
    notes = []
    for value, label in [(main_flow, "主力净流入"), (five_day, "5日主力净流入")]:
        if value is not None:
            score += 14 if value > 0 else -14
            notes.append(f"{label}{'为正' if value > 0 else '为负'}")
    if main_ratio is not None:
        score += 8 if main_ratio > 0 else -8
        notes.append(f"主力占比 {main_ratio:+.1f}%")
    if turnover is not None:
        notes.append(f"换手 {turnover:.1f}%")
    return _clamp_score(score), "；".join(notes[:3]) or "资金流数据暂无"


def build_defense_dashboard(
    snapshot: dict[str, Any],
    data: Any = None,
    benchmark_data: Any = None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build five-dimensional risk/defense scores from real data sources."""
    extended_info = extended_info or {}
    profile = profile or {}
    dimensions = [
        ("估值", *_score_valuation(profile)),
        ("成长", *_score_growth(extended_info, profile)),
        ("趋势", *_score_trend(snapshot, data)),
        ("安全", *_score_safety(snapshot, data)),
        ("资金", *_score_capital(extended_info, profile)),
    ]
    average = _clamp_score(sum(score for _, score, _ in dimensions) / len(dimensions))
    if average >= 75:
        conclusion = "防御健康，可按交易计划分批执行"
    elif average >= 60:
        conclusion = "整体可观察，等待关键位确认"
    elif average >= 45:
        conclusion = "防御一般，轻仓或等待更稳妥"
    else:
        conclusion = "防御偏弱，优先回避或降仓"
    return {
        "overall": average,
        "conclusion": conclusion,
        "dimensions": [
            {"name": name, "score": score, "note": note}
            for name, score, note in dimensions
        ],
        "signal_state": _build_signal_state(snapshot, data),
        "core_metrics": _build_core_metrics(snapshot, data, benchmark_data, extended_info, profile),
        "capital_trace": _build_capital_trace(extended_info, data, profile),
        "data_basis": "公开真实数据源 + 技术指标推导；不可直接确认字段仅做模型推断",
    }


def _trade_plan_row(label: str, value: Any, hint: str = "") -> str:
    hint_html = f"<span>{html.escape(hint)}</span>" if hint else ""
    return (
        '<div class="trade-plan-row">'
        f"<span>{html.escape(label)}</span>"
        f"<b>{_escape(value)}</b>"
        f"{hint_html}"
        "</div>"
    )


def _render_trade_plan(plan: dict[str, Any], tone: str) -> None:
    body = (
        '<div class="trade-plan-hero">'
        f'<span>当前动作</span><strong>{_escape(plan.get("current_action"))}</strong>'
        f'<em>{_escape(plan.get("position"))}</em>'
        '</div>'
        '<div class="trade-plan-grid">'
        + _trade_plan_row("买入观察", plan.get("buy_zone"))
        + _trade_plan_row("加仓确认", plan.get("add_condition"))
        + _trade_plan_row("止损线", _fmt_level(plan.get("stop_loss")), "跌破且无法收回")
        + _trade_plan_row("第一压力", _fmt_level(plan.get("take_profit_1")), "观察减仓")
        + _trade_plan_row("第二目标", _fmt_level(plan.get("take_profit_2")), "突破后参考")
        + _trade_plan_row("仓位纪律", plan.get("position"), plan.get("risk_note", ""))
        + '</div>'
        + f'<div class="decision-mini-note">{_escape(plan.get("data_basis"))}</div>'
    )
    _panel("交易计划卡片", body, tone)


def _render_defense_dashboard(defense: dict[str, Any]) -> None:
    overall = int(defense.get("overall") or 0)
    tone = _tone_from_score(overall)
    state = defense.get("signal_state") or {}
    state_tone = state.get("tone") or "neutral"
    triggers = "".join(f"<li>{_escape(item)}</li>" for item in (state.get("triggers") or [])[:4])
    state_html = (
        f'<div class="signal-state-card {state_tone}">'
        f'<div><span>当前状态</span><strong>{_escape(state.get("name"))}</strong></div>'
        f'<p>{_escape(state.get("reason"))}</p>'
        f"<ul>{triggers}</ul>"
        "</div>"
    )
    metrics = "".join(
        f'<div class="defense-metric {html.escape(str(item.get("status") or "missing"))}">'
        '<div class="defense-metric-head">'
        f'<span>{_escape(item.get("name"))}</span>'
        f'<i>{_escape(item.get("status_label"))}</i>'
        '</div>'
        f'<strong>{_escape(item.get("value"))}</strong>'
        f'<em>{_escape(item.get("note"))}</em>'
        "</div>"
        for item in defense.get("core_metrics", [])
    )
    trace_rows = "".join(
        "<tr>"
        f"<td>{_escape(item.get('label'))}</td>"
        f"<td>{_escape(item.get('value'))}</td>"
        f"<td>{_escape(item.get('impact'))}</td>"
        f"<td>{_escape(item.get('basis'))}</td>"
        "</tr>"
        for item in defense.get("capital_trace", [])
    )
    bars = "".join(
        '<div class="defense-dimension">'
        f'<div><b>{_escape(item.get("name"))}</b><span>{_escape(item.get("note"))}</span></div>'
        f'{_progress_bar(item.get("score"), tone=_tone_from_score(item.get("score")))}'
        "</div>"
        for item in defense.get("dimensions", [])
    )
    body = (
        '<div class="defense-dashboard-layout">'
        '<div class="defense-top-row">'
        f'<div class="defense-overall {tone}"><strong><em>风控分</em>{overall}</strong><span>{_escape(defense.get("conclusion"))}</span></div>'
        f"{state_html}"
        '</div>'
        f'<div class="defense-metric-grid">{metrics}</div>'
        '<div class="defense-bottom-grid">'
        f'<div class="defense-dimension-list">{bars}</div>'
        '<div class="capital-trace-block">'
        '<div class="capital-trace-title">资金博弈溯源</div>'
        '<table class="capital-trace-table"><thead><tr><th>项目</th><th>数值</th><th>解读</th><th>依据</th></tr></thead>'
        f"<tbody>{trace_rows}</tbody></table>"
        '</div>'
        '</div>'
        '</div>'
        f'<div class="decision-mini-note">{_escape(defense.get("data_basis"))}</div>'
    )
    _panel("风控防御看板", body, tone)


def _render_hero(snapshot: dict[str, Any]) -> None:
    score = int(snapshot.get("score") or 0)
    tone = snapshot.get("tone", "neutral")
    confidence = int(snapshot.get("confidence") or 0)
    body = f"""
    <div class="decision-hero {tone}">
      <div class="decision-score-ring {tone}">
        <strong>{score}</strong>
        <span>决策分</span>
      </div>
      <div class="decision-hero-main">
        <div class="decision-eyebrow">A股决策委员会 · 决策分 · TradingAgents Lite</div>
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
    return (
        f'<div class="agent-card {tone}">'
        '<div class="agent-card-head">'
        "<div>"
        f'<div class="agent-name">{_escape(agent.get("name"), "Agent")}</div>'
        f'<div class="agent-summary">{_escape(agent.get("summary"))}</div>'
        "</div>"
        f'<span class="agent-score-pill {tone}">{delta:+}</span>'
        "</div>"
        '<div class="agent-meta-grid">'
        f'<span>立场 <b>{_escape(agent.get("stance"))}</b></span>'
        f"<span>权重 <b>{agent.get('weight', 0)}</b></span>"
        f"<span>原始分 <b>{raw_score:+}</b></span>"
        "</div>"
        f'{_progress_bar(agent.get("confidence"), tone="watch")}'
        '<div class="agent-detail-grid">'
        f"<div>{evidence}</div>"
        f"<div>{warnings}</div>"
        "</div>"
        "</div>"
    )


def render_decision_dashboard(
    data,
    signals: dict[str, Any],
    quote: dict[str, Any] | None,
    extended_info: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    benchmark_data: Any = None,
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

    st.markdown("#### 交易计划与风控防御")
    trade_plan = build_trade_plan(snapshot, data)
    defense = build_defense_dashboard(snapshot, data, benchmark_data, extended_info, profile)
    col_plan, col_defense = st.columns([0.9, 1.7])
    with col_plan:
        _render_trade_plan(trade_plan, snapshot.get("tone", "neutral"))
        _panel(
            "看多依据",
            _list_items(snapshot.get("bullish_points"), icon="多", empty="暂无明确看多证据", tone="bullish"),
            "bullish",
            compact=True,
        )
        _panel(
            "看空因素",
            _list_items(snapshot.get("bearish_points"), icon="空", empty="暂无明显看空风险", tone="neutral"),
            "neutral",
            compact=True,
        )
        risks = snapshot.get("risks") or snapshot.get("risk_alerts")
        _panel(
            "风险警报",
            _list_items(risks, icon="险", empty="暂无明显风险警报，仍需控制仓位", tone="bearish"),
            "bearish" if risks else "neutral",
            compact=True,
        )
    with col_defense:
        _render_defense_dashboard(defense)

    with st.expander("A股决策委员会：五层 Agent 观点", expanded=False):
        agent_cards = "".join(_render_agent_card(agent) for agent in snapshot.get("agents", []))
        st.markdown(f"<div class='agent-card-grid'>{agent_cards}</div>", unsafe_allow_html=True)
