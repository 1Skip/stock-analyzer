"""Independent experimental quality-value-timing strategy helpers."""
from __future__ import annotations

from datetime import date, datetime
from math import sqrt
from typing import Any

import pandas as pd

from technical_indicators import TechnicalIndicators


EXPERIMENTAL_STRATEGY_NAME = "实验策略"
EXPERIMENTAL_STRATEGY_VERSION = "quality_value_timing_v1"
EXPERIMENTAL_UNIVERSE_LIMIT = 180
EXPERIMENTAL_DEEP_LIMIT = 24
EXPERIMENTAL_ESTIMATED_COST_PCT = 0.20


def select_experimental_universe(
    stocks: list[dict[str, Any]] | None,
    profile_index: dict[str, dict[str, Any]] | None,
    *,
    limit: int = EXPERIMENTAL_UNIVERSE_LIMIT,
    as_of: Any = None,
    allow_missing_listing: bool = False,
) -> list[dict[str, Any]]:
    """Select mature Shanghai/Shenzhen main-board companies for observation."""
    profile_index = profile_index if isinstance(profile_index, dict) else {}
    end_date = _parse_date(as_of) or date.today()
    eligible = []
    for stock in stocks or []:
        code = str(stock.get("code") or "").strip()
        name = str(stock.get("name") or "").strip()
        if not _is_main_board(code) or not name or "ST" in name.upper() or "退" in name:
            continue
        profile = profile_index.get(code) if isinstance(profile_index.get(code), dict) else {}
        listing = _parse_date(profile.get("listing_date"))
        if listing is None and not allow_missing_listing:
            continue
        if listing is not None and (end_date - listing).days < 365 * 5:
            continue
        item = dict(stock)
        item["_profile_index"] = profile
        item["_listing_age_days"] = (end_date - listing).days if listing is not None else -1
        eligible.append(item)

    shanghai = sorted(
        (item for item in eligible if str(item.get("code")).startswith("6")),
        key=lambda item: (-item["_listing_age_days"], str(item.get("code"))),
    )
    shenzhen = sorted(
        (item for item in eligible if not str(item.get("code")).startswith("6")),
        key=lambda item: (-item["_listing_age_days"], str(item.get("code"))),
    )
    result = []
    positions = [0, 0]
    buckets = [shanghai, shenzhen]
    while len(result) < max(0, int(limit)) and any(positions[i] < len(bucket) for i, bucket in enumerate(buckets)):
        for index, bucket in enumerate(buckets):
            if positions[index] >= len(bucket):
                continue
            result.append(bucket[positions[index]])
            positions[index] += 1
            if len(result) >= int(limit):
                break
    return result


def evaluate_experimental_technical(data: pd.DataFrame | None) -> dict[str, Any]:
    """Apply stable-trend timing rules to real daily K-line data."""
    if data is None or getattr(data, "empty", True) or len(data) < 80:
        return {"passed": False, "reason": "K线不足80个交易日"}
    frame = TechnicalIndicators.calculate_all(data.copy())
    latest = frame.iloc[-1]
    close = _number(latest.get("close"))
    ma20 = _number(latest.get("ma20"))
    ma60 = _number(latest.get("ma60"))
    prior_ma20 = _number(frame.iloc[-6].get("ma20")) if len(frame) >= 6 else None
    rsi = _number(latest.get("rsi_6") if latest.get("rsi_6") is not None else latest.get("rsi"))
    recent_close = pd.to_numeric(frame["close"], errors="coerce").dropna()
    recent_volume = pd.to_numeric(frame["volume"], errors="coerce").dropna()
    if close is None or len(recent_close) < 61:
        return {"passed": False, "reason": "收盘价或长均线数据缺失"}
    return_20d = (close / float(recent_close.iloc[-21]) - 1) * 100 if len(recent_close) >= 21 else None
    returns = recent_close.pct_change().dropna().tail(20)
    volatility_20d = float(returns.std() * 100) if len(returns) >= 15 else None
    volume_base = float(recent_volume.iloc[-21:-1].mean()) if len(recent_volume) >= 21 else None
    volume_ratio = float(recent_volume.iloc[-1] / volume_base) if volume_base and volume_base > 0 else None
    high_20 = float(recent_close.tail(20).max())
    drawdown_20d = (close / high_20 - 1) * 100 if high_20 > 0 else None

    checks = {
        "价格站上MA20": close is not None and ma20 is not None and close > ma20,
        "MA20高于MA60": ma20 is not None and ma60 is not None and ma20 > ma60,
        "MA20持续上行": ma20 is not None and prior_ma20 is not None and ma20 > prior_ma20,
        "RSI处于45至70": rsi is not None and 45 <= rsi <= 70,
        "20日涨幅0至20%": return_20d is not None and 0 <= return_20d <= 20,
        "量比0.7至2.0": volume_ratio is not None and 0.7 <= volume_ratio <= 2.0,
        "20日波动不高于4.5%": volatility_20d is not None and volatility_20d <= 4.5,
        "距20日高点不超过12%": drawdown_20d is not None and drawdown_20d >= -12,
    }
    matched = sum(bool(value) for value in checks.values())
    score = round(matched / len(checks) * 100, 1)
    return {
        "passed": all(checks.values()),
        "score": score,
        "checks": checks,
        "latest": latest,
        "frame": frame,
        "metrics": {
            "return_20d_pct": round(return_20d, 2) if return_20d is not None else None,
            "volatility_20d_pct": round(volatility_20d, 2) if volatility_20d is not None else None,
            "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
            "drawdown_20d_pct": round(drawdown_20d, 2) if drawdown_20d is not None else None,
        },
        "reason": "全部稳定趋势条件通过" if all(checks.values()) else f"稳定趋势条件命中 {matched}/{len(checks)}",
    }


def build_experimental_candidate(
    stock: dict[str, Any],
    technical: dict[str, Any],
    valuation: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    extended_info: dict[str, Any] | None = None,
    risk_blocked: bool = False,
    risk_note: str = "",
) -> dict[str, Any] | None:
    """Combine valuation quality and timing; missing evidence rejects the stock."""
    if not technical.get("passed") or valuation.get("status") != "ok" or risk_blocked:
        return None
    valuation_score = _number(valuation.get("score"))
    base_margin = _number(valuation.get("base_margin_of_safety_pct"))
    facts = valuation.get("facts") if isinstance(valuation.get("facts"), dict) else {}
    if valuation_score is None or valuation_score < 65 or base_margin is None or base_margin < 15:
        return None
    if (_number(facts.get("annualized_net_profit")) or 0) <= 0:
        return None
    if (_number(facts.get("annualized_operating_cash_flow")) or 0) <= 0:
        return None

    technical_score = float(technical.get("score") or 0)
    total_score = round(valuation_score * 0.60 + technical_score * 0.40, 1)
    latest = technical.get("latest")
    latest_price = _number(latest.get("close")) if latest is not None else None
    if latest_price is None:
        return None
    code = str(stock.get("code") or "").strip()
    metrics = technical.get("metrics") or {}
    return {
        "symbol": code,
        "name": stock.get("name") or code,
        "sector": None,
        "board": "沪市主板" if code.startswith("6") else "深市主板",
        "score": total_score,
        "rating": "实验观察候选",
        "signals": {
            "技术形态": technical.get("reason"),
            "估值状态": f"筛选级估值 {valuation_score:.1f}，基础安全边际 {base_margin:.2f}%",
            "实验纪律": "仅进入自动观察仓，验证门槛达标前不作为实盘依据",
        },
        "latest_price": latest_price,
        "change_pct": None,
        "strategy": EXPERIMENTAL_STRATEGY_NAME,
        "strategy_version": EXPERIMENTAL_STRATEGY_VERSION,
        "strategy_checks": {
            **(technical.get("checks") or {}),
            "估值评分≥65": True,
            "基础安全边际≥15%": True,
            "盈利与经营现金流为正": True,
            "无重大风险事件": True,
        },
        "required_checks": {
            "主板且上市满5年": True,
            "稳定趋势条件全部通过": True,
            "估值证据可计算": True,
            "无重大风险事件": True,
        },
        "strategy_details": {
            "估值方法": "芒格质量 + 巴菲特所有者收益代理 + Codex证据纪律",
            "估值等级": valuation.get("grade_label"),
            "基础情景价值": valuation.get("base_value_per_share"),
            "基础安全边际": f"{base_margin:.2f}%",
            "技术波动": f"20日波动 {metrics.get('volatility_20d_pct')}%",
            "风险排除": risk_note or "未发现规则内重大风险事件",
            "实验纪律": "达到100个已结算样本及统计门槛前，只观察、不转正式策略",
        },
        "indicators": _indicators(latest),
        "valuation_snapshot": valuation,
        "extended_info": extended_info or {},
        "profile": profile or {},
        "market_cap": (profile or {}).get("market_cap"),
    }


def build_experimental_validation_gate(row: dict[str, Any] | None) -> dict[str, Any]:
    """Return promotion/rejection status from saved real T+1 outcomes."""
    row = row if isinstance(row, dict) else {}
    samples = int(row.get("samples_1d") or 0)
    wins = int(row.get("wins_1d") or 0)
    win_rate = _number(row.get("win_rate_1d_pct"))
    avg_return = _number(row.get("avg_1d_return_pct"))
    plan_dates = int(row.get("distinct_plan_dates") or 0)
    ci_low, ci_high = wilson_interval(wins, samples)
    net_avg = round(avg_return - EXPERIMENTAL_ESTIMATED_COST_PCT, 2) if avg_return is not None else None

    criteria = {
        "已结算样本≥100": samples >= 100,
        "独立计划日≥20": plan_dates >= 20,
        "1日胜率≥55%": win_rate is not None and win_rate >= 55,
        "胜率95%区间下限≥50%": ci_low is not None and ci_low >= 50,
        "扣估算成本后1日均收益>0": net_avg is not None and net_avg > 0,
    }
    if samples < 30:
        status = "collecting"
        label = "观察积累"
        message = f"已结算 {samples}/30，暂不判断策略有效性。"
    elif (avg_return is not None and avg_return < 0) or (ci_high is not None and ci_high < 50):
        status = "rejected"
        label = "淘汰当前版本"
        message = "当前版本达到最低样本后仍未显示正向优势，需修改规则并升级版本后重新观察。"
    elif samples < 100:
        status = "reference"
        label = "参考验证"
        message = f"已结算 {samples}/100，只能参考，不能转为正式策略。"
    elif all(criteria.values()):
        status = "promotable"
        label = "可评估转正"
        message = "样本和统计门槛均达标，可人工复核不同市场阶段后再决定是否转正。"
    else:
        status = "validation_failed"
        label = "未通过转正门槛"
        message = "样本已足够，但胜率、置信区间、收益或计划日覆盖未同时达标。"
    return {
        "version": EXPERIMENTAL_STRATEGY_VERSION,
        "status": status,
        "label": label,
        "message": message,
        "samples": samples,
        "wins": wins,
        "win_rate_ci_low_pct": ci_low,
        "win_rate_ci_high_pct": ci_high,
        "estimated_cost_pct": EXPERIMENTAL_ESTIMATED_COST_PCT,
        "net_avg_1d_return_pct": net_avg,
        "criteria": criteria,
    }


def sample_tier(samples: int) -> dict[str, str]:
    if samples < 30:
        return {"status": "observation", "label": "仅观察"}
    if samples < 100:
        return {"status": "reference", "label": "可参考"}
    return {"status": "comparison", "label": "可横向比较"}


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    proportion = max(0, min(wins, total)) / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return round(max(0, center - margin) * 100, 2), round(min(1, center + margin) * 100, 2)


def _indicators(latest: Any) -> dict[str, Any]:
    if latest is None:
        return {}
    keys = (
        "macd", "macd_signal", "macd_hist", "rsi", "rsi_6", "rsi_12", "rsi_24",
        "kdj_k", "kdj_d", "kdj_j", "boll_upper", "boll_mid", "boll_lower",
    )
    return {key: round(float(latest.get(key)), 3) for key in keys if _number(latest.get(key)) is not None}


def _is_main_board(code: str) -> bool:
    return str(code).startswith(("600", "601", "603", "605", "000", "001", "002", "003"))


def _parse_date(value: Any) -> date | None:
    try:
        parsed = pd.to_datetime(value, errors="raise")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None
