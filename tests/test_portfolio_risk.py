from portfolio_risk import PortfolioRiskEngine, PortfolioRiskLimits


def _engine():
    return PortfolioRiskEngine(
        PortfolioRiskLimits(
            max_drawdown_pct=10,
            max_daily_loss_pct=3,
            max_industry_exposure_pct=40,
            max_order_participation_pct=0.5,
            max_data_age_days=3,
        )
    )


def test_drawdown_breach_blocks_new_entries():
    account = {
        "equity_curve": [{"date": "2026-07-01", "equity": 100_000}],
        "risk_state": {"peak_equity": 100_000},
    }

    risk = _engine().update_account_state(account, equity=89_000, as_of_date="2026-07-02")

    assert risk["block_new_entries"] is True
    assert "组合最大回撤熔断" in risk["automatic_breaches"]
    assert "组合单日亏损熔断" in risk["automatic_breaches"]


def test_entry_is_blocked_by_capacity_industry_and_stale_data():
    account = {
        "positions": {
            "600001": {
                "industry": "电力",
                "average_price": 10,
                "quantity": 3000,
            }
        },
        "risk_state": {"block_new_entries": False},
    }

    decision = _engine().evaluate_entry(
        account,
        order_notional=20_000,
        industry="电力",
        daily_amount=1_000_000,
        market_date="2026-07-01",
        as_of_date="2026-07-10",
        equity=100_000,
    )

    assert decision["allowed"] is False
    assert any("成交额" in reason for reason in decision["reasons"])
    assert any("暴露" in reason for reason in decision["reasons"])
    assert any("陈旧" in reason for reason in decision["reasons"])
