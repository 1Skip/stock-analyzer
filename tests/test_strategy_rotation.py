from candidate_strategy import (
    CANDIDATE_RULESET_VERSION,
    candidate_rule_fingerprint,
)
from strategy_rotation import (
    approved_rules_from_research,
    build_rotation_decision,
    strategy_version_for_rule,
)


RULE_ID = "capital_flow_pullback_regime_confirmed"


def _research():
    train_stats = {
        "samples": 200,
        "win_rate_pct": 60,
        "wilson_low_pct": 53,
        "avg_net_return_pct": 0.3,
        "profit_factor": 1.3,
        "max_drawdown_pct": -8,
    }
    test_stats = {
        "samples": 60,
        "win_rate_pct": 55,
        "wilson_low_pct": 45,
        "avg_net_return_pct": 0.2,
        "profit_factor": 1.2,
        "max_drawdown_pct": -9,
        "avg_excess_return_pct": 0.1,
    }
    return {
        "strategy_rule_set_version": CANDIDATE_RULESET_VERSION,
        "rule_fingerprints": {RULE_ID: candidate_rule_fingerprint(RULE_ID)},
        "data_quality": {
            "point_in_time_universe": True,
            "benchmark_available": True,
            "promotion_blockers": [],
        },
        "rules": {
            RULE_ID: {
                "train": {"plan_dates": 40, "horizons": {"1d": train_stats}},
                "test": {"plan_dates": 20, "horizons": {"1d": test_stats}},
            }
        },
    }


def _closed_trades(rule_id, version, pnls):
    return [
        {
            "strategy_rule_id": rule_id,
            "strategy_version": version,
            "pnl": pnl,
            "return_pct": pnl / 1000 * 100,
        }
        for pnl in pnls
    ]


def test_only_research_with_matching_fingerprint_and_oos_profit_is_approved():
    research = _research()

    assert [row["rule_id"] for row in approved_rules_from_research(research)] == [
        RULE_ID
    ]

    research["rule_fingerprints"][RULE_ID] = "stale"
    assert approved_rules_from_research(research) == []


def test_rotation_waits_for_30_settled_trades():
    decision = build_rotation_decision(
        {
            "active_rule_id": "pullback_recovery_regime",
            "active_strategy_version": "market_regime_pullback_v2",
        },
        _closed_trades(
            "pullback_recovery_regime",
            "market_regime_pullback_v2",
            [-10] * 29,
        ),
        _research(),
    )

    assert decision["action"] == "observe"


def test_losing_rule_switches_only_to_offline_approved_candidate():
    decision = build_rotation_decision(
        {
            "active_rule_id": "pullback_recovery_regime",
            "active_strategy_version": "market_regime_pullback_v2",
        },
        _closed_trades(
            "pullback_recovery_regime",
            "market_regime_pullback_v2",
            [-10] * 20 + [5] * 10,
        ),
        _research(),
    )

    assert decision["action"] == "switch"
    assert decision["next_rule"]["rule_id"] == RULE_ID
    assert decision["next_rule"]["strategy_version"] == strategy_version_for_rule(
        RULE_ID
    )


def test_losing_rule_moves_to_cash_when_no_candidate_passes():
    research = _research()
    research["rules"][RULE_ID]["test"]["horizons"]["1d"][
        "avg_net_return_pct"
    ] = -0.1
    decision = build_rotation_decision(
        {
            "active_rule_id": "pullback_recovery_regime",
            "active_strategy_version": "market_regime_pullback_v2",
        },
        _closed_trades(
            "pullback_recovery_regime",
            "market_regime_pullback_v2",
            [-10] * 30,
        ),
        research,
    )

    assert decision["action"] == "cash"
