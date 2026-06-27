from short_term_learning import apply_short_term_learning, build_short_term_learning_profile


def _row(plan):
    return {"plan": plan}


def _plan(score, symbol="002001", strategy="短线"):
    return {
        "strategy": strategy,
        "sector": "全部",
        "generated_trade_date": "2026-06-01",
        "recommended": [
            {
                "symbol": symbol,
                "name": "测试股",
                "score": score,
                "latest_price": 10,
            }
        ],
    }


def test_short_term_learning_uses_real_completed_outcomes_for_threshold():
    rows = [_row(_plan(72 + (idx % 3), symbol=f"002{idx:03d}")) for idx in range(12)]

    def fake_outcomes(plan, *, quote_service, horizons):
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "status": "completed",
                    "returns": {"1d": 1.5},
                }
            ]
        }

    profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
    )

    assert profile["status"] == "active"
    assert profile["sample_count"] == 12
    assert profile["score_threshold"] == 70.0


def test_short_term_learning_keeps_classic_short_term_samples_separate():
    rows = [
        _row(_plan(72 + (idx % 3), symbol=f"002{idx:03d}", strategy="短线经典版"))
        for idx in range(12)
    ]
    rows.extend(
        _row(_plan(90, symbol=f"003{idx:03d}", strategy="短线"))
        for idx in range(3)
    )

    def fake_outcomes(plan, *, quote_service, horizons):
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "status": "completed",
                    "returns": {"1d": 1.5},
                }
            ]
        }

    classic_profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        strategy="短线经典版",
    )
    short_profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        strategy="短线",
    )

    assert classic_profile["strategy"] == "短线经典版"
    assert classic_profile["status"] == "active"
    assert classic_profile["sample_count"] == 12
    assert short_profile["strategy"] == "短线"
    assert short_profile["status"] == "insufficient_samples"
    assert short_profile["sample_count"] == 3


def test_short_term_learning_stays_observational_when_samples_are_insufficient():
    rows = [_row(_plan(90, symbol=f"002{idx:03d}")) for idx in range(3)]

    def fake_outcomes(plan, *, quote_service, horizons):
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "status": "completed",
                    "returns": {"1d": 2.0},
                }
            ]
        }

    profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
    )
    result = apply_short_term_learning(
        [{"symbol": "002001", "score": 50, "alpha_score": 60}],
        profile,
    )

    assert profile["status"] == "insufficient_samples"
    assert profile["score_threshold"] is None
    assert result[0]["learning_filtered"] is False
    assert result[0]["learning_bonus"] == 0.0


def test_short_term_learning_keeps_low_score_items_and_sorts_when_profile_is_active():
    profile = {
        "version": "short_term_learning_v1",
        "status": "active",
        "score_threshold": 70,
        "baseline_avg_1d_return_pct": 0.2,
        "bucket_stats": [
            {"score_min": 70, "score_max": 74.9, "sample_count": 6, "avg_1d_return_pct": 1.8, "win_rate_1d_pct": 66.67},
            {"score_min": 80, "score_max": 84.9, "sample_count": 6, "avg_1d_return_pct": 0.5, "win_rate_1d_pct": 50.0},
        ],
    }

    result = apply_short_term_learning(
        [
            {"symbol": "LOW", "score": 65, "alpha_score": 90},
            {"symbol": "A", "score": 72, "alpha_score": 70},
            {"symbol": "B", "score": 82, "alpha_score": 75},
        ],
        profile,
    )

    assert [item["symbol"] for item in result] == ["LOW", "B", "A"]
    assert all(item["learning_filtered"] is False for item in result)
    by_symbol = {item["symbol"]: item for item in result}
    assert by_symbol["A"]["learning_bonus"] > by_symbol["B"]["learning_bonus"]
    assert by_symbol["LOW"]["learning_below_threshold"] is True
    assert "仅影响排序，不剔除" in by_symbol["LOW"]["learning_threshold_note"]


def test_short_term_learning_excludes_star_market_as_experiment_pool_guard():
    result = apply_short_term_learning(
        [
            {"symbol": "688001", "score": 90, "alpha_score": 90},
            {"symbol": "002001", "score": 70, "alpha_score": 70},
        ],
        {"status": "insufficient_samples"},
    )

    assert [item["symbol"] for item in result] == ["002001"]
