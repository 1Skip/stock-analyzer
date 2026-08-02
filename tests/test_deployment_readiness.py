from deployment_readiness import DeploymentReadinessService


def _paper():
    return {
        "closed_trades": 100,
        "recent_closed_trades": [
            {"plan_identity": f"p{index % 20}"} for index in range(100)
        ],
        "win_rate_pct": 60,
        "avg_return_pct": 0.5,
        "audit": {"valid": True},
        "last_reconciliation": {"status": "ok"},
        "risk": {"block_new_entries": False},
    }


def test_launch_sequence_blocks_later_stages_when_research_fails(tmp_path):
    service = DeploymentReadinessService(
        research_path=tmp_path / "research.json",
        portfolio_path=tmp_path / "portfolio.json",
    )

    report = service.evaluate(
        research={
            "status": "ok",
            "selected_rule_id": "",
            "data_quality": {
                "point_in_time_universe": False,
                "promotion_blockers": ["没有规则通过门槛"],
            },
        },
        portfolio={
            "status": "ok",
            "metrics": {
                "closed_trades": 200,
                "total_return_pct": 20,
                "excess_return_pct": 10,
                "max_drawdown_pct": -5,
            },
            "audit": {"valid": True},
            "reconciliation": {"status": "ok"},
        },
        paper_summary=_paper(),
        broker_readiness={
            "mode": "qmt_live",
            "ready": True,
            "read_only": False,
            "live_order_enabled": True,
        },
    )

    assert report["status"] == "blocked"
    assert report["current_stage"] == "策略研究转正"
    assert all(row["status"] == "blocked" for row in report["stages"])


def test_launch_sequence_reaches_live_only_when_every_prior_gate_passes(tmp_path):
    service = DeploymentReadinessService(
        research_path=tmp_path / "research.json",
        portfolio_path=tmp_path / "portfolio.json",
    )

    report = service.evaluate(
        research={
            "status": "ok",
            "selected_rule_id": "validated",
            "data_quality": {
                "point_in_time_universe": True,
                "promotion_blockers": [],
            },
        },
        portfolio={
            "status": "ok",
            "metrics": {
                "closed_trades": 200,
                "total_return_pct": 20,
                "excess_return_pct": 10,
                "max_drawdown_pct": -5,
            },
            "audit": {"valid": True},
            "reconciliation": {"status": "ok"},
        },
        paper_summary=_paper(),
        broker_readiness={
            "mode": "qmt_live",
            "ready": True,
            "read_only": False,
            "live_order_enabled": True,
        },
    )

    assert [row["status"] for row in report["stages"][:4]] == ["passed"] * 4
    assert report["stages"][4]["status"] == "blocked"
    assert report["automatic_live_promotion"] is False
