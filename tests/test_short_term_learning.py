from datetime import date

from data.cache import JsonFileCache
import short_term_learning as learning_module
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
    plans = [_plan(72 + (idx % 3), symbol=f"002{idx:03d}") for idx in range(12)]
    for idx, plan in enumerate(plans, start=1):
        plan["generated_at"] = f"2026-06-{idx:02d}T15:45:00"
    rows = [_row(plan) for plan in plans]

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


def test_short_term_learning_profile_cache_reuses_same_history_within_ttl(
    monkeypatch,
    tmp_path,
):
    profile_cache = JsonFileCache("profiles", 900, cache_dir=tmp_path)
    outcome_cache = JsonFileCache("outcomes", 900, cache_dir=tmp_path)
    monkeypatch.setattr(learning_module, "_PROFILE_CACHE", profile_cache)
    monkeypatch.setattr(learning_module, "_OUTCOME_CACHE", outcome_cache)
    plans = [_plan(72 + (idx % 3), symbol=f"002{idx:03d}") for idx in range(12)]
    for idx, plan in enumerate(plans, start=1):
        plan["generated_at"] = f"2026-06-{idx:02d}T15:45:00"
    rows = [_row(plan) for plan in plans]
    evaluations = 0

    def fake_outcomes(plan, *, quote_service, horizons):
        nonlocal evaluations
        evaluations += 1
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

    first = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        use_profile_cache=True,
    )
    first_evaluations = evaluations
    current_plan = _plan(88, symbol="002999")
    current_plan["generated_at"] = f"{date.today().isoformat()}T15:45:00"
    second = build_short_term_learning_profile(
        [_row(current_plan), *rows],
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        use_profile_cache=True,
    )

    assert first_evaluations == 12
    assert evaluations == first_evaluations
    assert second == first


def test_short_term_learning_profile_cache_invalidates_when_older_history_changes(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        learning_module,
        "_PROFILE_CACHE",
        JsonFileCache("profiles", 900, cache_dir=tmp_path),
    )
    monkeypatch.setattr(
        learning_module,
        "_OUTCOME_CACHE",
        JsonFileCache("outcomes", 900, cache_dir=tmp_path),
    )
    first_plan = _plan(72, symbol="002001")
    first_plan["generated_at"] = "2026-06-01T15:45:00"
    second_plan = _plan(82, symbol="002002")
    second_plan["generated_at"] = "2026-06-02T15:45:00"
    evaluations = 0

    def fake_outcomes(plan, *, quote_service, horizons):
        nonlocal evaluations
        evaluations += 1
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "status": "completed",
                    "returns": {"1d": 1.0},
                }
            ]
        }

    first = build_short_term_learning_profile(
        [_row(first_plan)],
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        use_profile_cache=True,
    )
    second = build_short_term_learning_profile(
        [_row(second_plan), _row(first_plan)],
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        use_profile_cache=True,
    )

    assert evaluations == 2
    assert first["sample_count"] == 1
    assert second["sample_count"] == 2


def test_short_term_learning_profile_cache_is_strategy_specific(monkeypatch, tmp_path):
    monkeypatch.setattr(
        learning_module,
        "_PROFILE_CACHE",
        JsonFileCache("profiles", 900, cache_dir=tmp_path),
    )
    monkeypatch.setattr(
        learning_module,
        "_OUTCOME_CACHE",
        JsonFileCache("outcomes", 900, cache_dir=tmp_path),
    )
    rows = [
        _row(_plan(72, strategy="短线")),
        _row(_plan(82, strategy="短线经典版")),
    ]

    def fake_outcomes(plan, *, quote_service, horizons):
        stock = plan["recommended"][0]
        return {
            "items": [
                {
                    "symbol": stock["symbol"],
                    "status": "completed",
                    "returns": {"1d": 1.0},
                }
            ]
        }

    short_profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        strategy="短线",
        use_profile_cache=True,
    )
    classic_profile = build_short_term_learning_profile(
        rows,
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
        strategy="短线经典版",
        use_profile_cache=True,
    )

    assert short_profile["strategy"] == "短线"
    assert classic_profile["strategy"] == "短线经典版"
    assert short_profile["sample_count"] == 1
    assert classic_profile["sample_count"] == 1


def test_short_term_learning_skips_plan_entering_today_before_one_day_settlement(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        learning_module,
        "_OUTCOME_CACHE",
        JsonFileCache("outcomes", 900, cache_dir=tmp_path),
    )
    today = date.today().isoformat()
    plan = _plan(82, symbol="002999")
    plan.update({
        "generated_at": f"{today}T15:45:00",
        "generated_trade_date": today,
        "plan_for_trade_date": today,
    })
    evaluations = 0

    def fake_outcomes(saved_plan, *, quote_service, horizons):
        nonlocal evaluations
        evaluations += 1
        raise AssertionError("当天入场计划不应访问历史行情补算一日结果")

    profile = build_short_term_learning_profile(
        [_row(plan)],
        quote_service=object(),
        evaluate_plan_outcomes=fake_outcomes,
    )

    assert evaluations == 0
    assert profile["sample_count"] == 0
