"""Controlled experimental-strategy rotation based on real paper results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from candidate_strategy import (
    CAPITAL_FLOW_RULE_IDS,
    CANDIDATE_RULESET_VERSION,
    CANDIDATE_RULES,
    candidate_rule_fingerprint,
)


MIN_SETTLED_TRADES = 30
MIN_OOS_TRADES = 30
MAX_ACCEPTABLE_DRAWDOWN_PCT = -15.0


def strategy_version_for_rule(rule_id: str) -> str:
    return f"{CANDIDATE_RULESET_VERSION}:{rule_id}"


def load_strategy_research(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def approved_rules_from_research(
    research: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return only immutable rules that pass train and out-of-sample gates."""
    research = research if isinstance(research, dict) else {}
    quality = research.get("data_quality") if isinstance(research.get("data_quality"), dict) else {}
    if (
        research.get("strategy_rule_set_version") != CANDIDATE_RULESET_VERSION
        or quality.get("point_in_time_universe") is not True
        or quality.get("benchmark_available") is not True
        or quality.get("promotion_blockers")
    ):
        return []
    fingerprints = (
        research.get("rule_fingerprints")
        if isinstance(research.get("rule_fingerprints"), dict)
        else {}
    )
    approved = []
    for rule_id, row in (research.get("rules") or {}).items():
        if (
            rule_id not in CANDIDATE_RULES
            or rule_id not in CAPITAL_FLOW_RULE_IDS
            or fingerprints.get(rule_id) != candidate_rule_fingerprint(rule_id)
            or not isinstance(row, dict)
        ):
            continue
        train = row.get("train") if isinstance(row.get("train"), dict) else {}
        test = row.get("test") if isinstance(row.get("test"), dict) else {}
        train_stats = ((train.get("horizons") or {}).get("1d") or {})
        test_stats = ((test.get("horizons") or {}).get("1d") or {})
        if not _passes_training_gate(train, train_stats):
            continue
        if not _passes_oos_gate(test, test_stats):
            continue
        approved.append({
            "rule_id": rule_id,
            "label": CANDIDATE_RULES[rule_id].label,
            "strategy_version": strategy_version_for_rule(rule_id),
            "rule_fingerprint": fingerprints[rule_id],
            "train": train_stats,
            "test": test_stats,
        })
    return sorted(
        approved,
        key=lambda row: (
            float((row.get("test") or {}).get("wilson_low_pct") or 0),
            float((row.get("test") or {}).get("avg_net_return_pct") or 0),
            float((row.get("test") or {}).get("profit_factor") or 0),
            row["rule_id"],
        ),
        reverse=True,
    )


def summarize_rule_performance(
    closed_trades: list[dict[str, Any]] | None,
    *,
    rule_id: str,
    strategy_version: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in closed_trades or []
        if str(row.get("strategy_rule_id") or "") == rule_id
        and str(row.get("strategy_version") or "") == strategy_version
    ]
    gains = sum(max(0.0, float(row.get("pnl") or 0)) for row in rows)
    losses = abs(sum(min(0.0, float(row.get("pnl") or 0)) for row in rows))
    net_pnl = gains - losses
    wins = sum(float(row.get("pnl") or 0) > 0 for row in rows)
    returns = [
        float(row["return_pct"])
        for row in rows
        if _number(row.get("return_pct")) is not None
    ]
    return {
        "rule_id": rule_id,
        "strategy_version": strategy_version,
        "settled_trades": len(rows),
        "wins": wins,
        "win_rate_pct": round(wins / len(rows) * 100, 2) if rows else None,
        "net_pnl": round(net_pnl, 4),
        "avg_net_return_pct": (
            round(sum(returns) / len(returns), 4) if returns else None
        ),
        "profit_factor": round(gains / losses, 4) if losses > 0 else None,
    }


def build_rotation_decision(
    control: dict[str, Any] | None,
    closed_trades: list[dict[str, Any]] | None,
    research: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep, switch, or move to cash without tuning parameters at runtime."""
    control = control if isinstance(control, dict) else {}
    rule_id = str(control.get("active_rule_id") or "")
    version = str(control.get("active_strategy_version") or "")
    if not rule_id or not version:
        return {"action": "cash", "reason": "没有活动规则", "metrics": {}}
    metrics = summarize_rule_performance(
        closed_trades,
        rule_id=rule_id,
        strategy_version=version,
    )
    if metrics["settled_trades"] < MIN_SETTLED_TRADES:
        return {
            "action": "observe",
            "reason": (
                f"已结算{metrics['settled_trades']}/{MIN_SETTLED_TRADES}笔，"
                "样本不足，不自动换策略"
            ),
            "metrics": metrics,
        }
    profit_factor = metrics.get("profit_factor")
    losing = (
        float(metrics.get("net_pnl") or 0) <= 0
        or (profit_factor is not None and float(profit_factor) < 1)
    )
    if not losing:
        return {
            "action": "keep",
            "reason": "当前规则扣费后仍为正收益，继续观察",
            "metrics": metrics,
        }
    failed_keys = {
        str(value)
        for value in control.get("failed_rule_versions") or []
        if str(value)
    }
    failed_keys.add(_rule_key(rule_id, version))
    alternatives = [
        row
        for row in approved_rules_from_research(research)
        if _rule_key(row["rule_id"], row["strategy_version"]) not in failed_keys
    ]
    if not alternatives:
        return {
            "action": "cash",
            "reason": "当前规则扣费后亏损，且没有通过五年训练和样本外门槛的候选规则",
            "metrics": metrics,
            "failed_rule_versions": sorted(failed_keys),
        }
    return {
        "action": "switch",
        "reason": "当前规则扣费后亏损，自动切换到已通过离线门槛的候选规则",
        "metrics": metrics,
        "failed_rule_versions": sorted(failed_keys),
        "next_rule": alternatives[0],
    }


def _passes_training_gate(summary: dict[str, Any], stats: dict[str, Any]) -> bool:
    return bool(
        int(stats.get("samples") or 0) >= 100
        and int(summary.get("plan_dates") or 0) >= 20
        and float(stats.get("win_rate_pct") or 0) >= 55
        and float(stats.get("wilson_low_pct") or 0) >= 50
        and float(stats.get("avg_net_return_pct") or 0) > 0
        and float(stats.get("profit_factor") or 0) > 1
        and _drawdown_passes(stats.get("max_drawdown_pct"))
    )


def _passes_oos_gate(summary: dict[str, Any], stats: dict[str, Any]) -> bool:
    return bool(
        int(stats.get("samples") or 0) >= MIN_OOS_TRADES
        and int(summary.get("plan_dates") or 0) >= 10
        and float(stats.get("win_rate_pct") or 0) >= 50
        and float(stats.get("avg_net_return_pct") or 0) > 0
        and float(stats.get("profit_factor") or 0) > 1
        and float(stats.get("avg_excess_return_pct") or 0) > 0
        and _drawdown_passes(stats.get("max_drawdown_pct"))
    )


def _drawdown_passes(value: Any) -> bool:
    number = _number(value)
    return number is not None and number >= MAX_ACCEPTABLE_DRAWDOWN_PCT


def _rule_key(rule_id: str, strategy_version: str) -> str:
    return f"{strategy_version}|{rule_id}"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None
