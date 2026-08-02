"""Compare candidate strategy rules against local real A-share daily K data."""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import json
from math import sqrt
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_strategy import (  # noqa: E402
    CAPITAL_FLOW_RULE_IDS,
    CANDIDATE_RULESET_VERSION,
    CANDIDATE_RULES,
    REGIME_FILTERED_RULE_IDS,
    candidate_rule_fingerprint,
    candidate_score,
    candidate_signal_mask,
    candidate_trade_levels,
    prepare_candidate_frame,
)
from data.file_lock import atomic_write_text  # noqa: E402


DEFAULT_COST_PCT = 0.20
DEFAULT_TOP_N = 5
DEFAULT_TRAIN_END = "2026-04-30"
DEFAULT_STUDY_START = "2025-11-01"
HORIZONS = (1, 5, 20)
MAIN_BOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
POINT_IN_TIME_COVERAGE_THRESHOLD_PCT = 99.0


def load_universe(
    cache_dir: Path,
    name_index_path: Path,
    *,
    membership: dict[str, list[dict[str, str | None]]] | None = None,
) -> dict[str, pd.DataFrame]:
    names = _load_names(name_index_path)
    frames: dict[str, pd.DataFrame] = {}
    preferred_files: dict[str, tuple[int, str, Path]] = {}
    period_rank = {"3mo": 3, "6mo": 6, "1y": 12, "2y": 24, "5y": 60}
    for path in sorted(cache_dir.glob("CN_*_1d_*.json")):
        parts = path.stem.split("_")
        if len(parts) < 5:
            continue
        symbol = parts[1]
        period = parts[2]
        candidate = (period_rank.get(period, 0), path.name, path)
        if candidate[:2] > preferred_files.get(symbol, (-1, "", path))[:2]:
            preferred_files[symbol] = candidate
    for symbol, (_, _, path) in sorted(preferred_files.items()):
        name = names.get(symbol, symbol)
        if membership and symbol in membership:
            eligible = symbol.startswith(MAIN_BOARD_PREFIXES)
        else:
            eligible = _eligible_main_board(symbol, name)
        if not eligible:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            frame = pd.DataFrame(payload["data"], columns=payload["columns"])
            frame.index = pd.to_datetime(payload["index"], errors="coerce")
            frame = frame[frame.index.notna()]
            prepared = prepare_candidate_frame(frame)
        except Exception:
            continue
        has_capital_fields = bool(
            "amount_20d" in prepared.columns
            and prepared["amount_20d"].notna().any()
            and "turnover" in prepared.columns
            and prepared["turnover"].notna().any()
        )
        if len(prepared) >= 80 and has_capital_fields:
            prepared.attrs["symbol"] = symbol
            prepared.attrs["name"] = name
            prepared.attrs["source_file"] = path.name
            frames[symbol] = prepared
    return frames


def run_research(
    frames: dict[str, pd.DataFrame],
    *,
    train_end: str = DEFAULT_TRAIN_END,
    study_start: str = DEFAULT_STUDY_START,
    top_n: int = DEFAULT_TOP_N,
    cost_pct: float = DEFAULT_COST_PCT,
    membership: dict[str, list[dict[str, str | None]]] | None = None,
    daily_status: dict[str, Any] | None = None,
    benchmark: pd.DataFrame | None = None,
) -> dict[str, Any]:
    train_end_date = pd.Timestamp(train_end).normalize()
    rule_results = {}
    rule_trades = {}
    for rule_id in CANDIDATE_RULES:
        trades = build_trades(
            frames,
            rule_id=rule_id,
            top_n=top_n,
            cost_pct=cost_pct,
            study_start=study_start,
            membership=membership,
            daily_status=daily_status,
        )
        rule_trades[rule_id] = trades
        train = [row for row in trades if pd.Timestamp(row["signal_date"]) <= train_end_date]
        test = [row for row in trades if pd.Timestamp(row["signal_date"]) > train_end_date]
        rule_results[rule_id] = {
            "rule_id": rule_id,
            "label": CANDIDATE_RULES[rule_id].label,
            "train": summarize_trades(train, benchmark=benchmark),
            "test": summarize_trades(test, benchmark=benchmark),
        }
    training_gate_rule_id = select_rule_from_training(
        rule_results,
        eligible_rule_ids=CAPITAL_FLOW_RULE_IDS,
    )
    selected_rule_id = select_rule_for_promotion(
        rule_results,
        eligible_rule_ids=CAPITAL_FLOW_RULE_IDS,
    )
    training_leader_id = training_leader(
        rule_results,
        eligible_rule_ids=CAPITAL_FLOW_RULE_IDS,
    )
    walk_forward = build_walk_forward_analysis(
        rule_trades,
        study_start=study_start,
        benchmark=benchmark,
    )
    leader_trades = rule_trades.get(training_leader_id, [])
    sensitivity = build_execution_sensitivity(
        leader_trades,
        base_top_n=top_n,
        base_cost_pct=cost_pct,
        train_end=train_end,
        benchmark=benchmark,
    )
    research_end = max(
        (
            str(frame.index.max())[:10]
            for frame in frames.values()
            if frame is not None and not frame.empty
        ),
        default=train_end,
    )
    membership_expected = _membership_symbols_in_window(
        membership,
        start_date=study_start,
        end_date=research_end,
    )
    membership_covered = membership_expected & set(frames)
    membership_coverage_pct = (
        len(membership_covered) / len(membership_expected) * 100
        if membership_expected
        else None
    )
    status_covered = _historical_status_symbols_in_window(
        membership_expected,
        membership=membership,
        daily_status=daily_status,
        start_date=study_start,
        end_date=research_end,
    )
    historical_status_coverage_pct = (
        len(status_covered) / len(membership_expected) * 100
        if membership_expected
        else None
    )
    historical_status_available = bool(
        isinstance(daily_status, dict)
        and daily_status.get("valid") is True
        and daily_status.get("symbols")
    )
    historical_status_ready = bool(
        historical_status_available
        and historical_status_coverage_pct is not None
        and historical_status_coverage_pct >= POINT_IN_TIME_COVERAGE_THRESHOLD_PCT
    )
    point_in_time_ready = bool(
        membership
        and membership_coverage_pct is not None
        and membership_coverage_pct >= POINT_IN_TIME_COVERAGE_THRESHOLD_PCT
        and historical_status_ready
    )
    promotion_blockers = []
    if not membership:
        promotion_blockers.append("缺少历史时点股票池/退市股成员文件，存在幸存者偏差")
    elif (
        membership_coverage_pct is not None
        and membership_coverage_pct < POINT_IN_TIME_COVERAGE_THRESHOLD_PCT
    ):
        promotion_blockers.append(
            f"历史股票池日K覆盖仅{membership_coverage_pct:.2f}%，退市等成员日K尚未补齐"
        )
    if daily_status is None:
        promotion_blockers.append("缺少逐日历史ST/暂停上市状态，不能用当前名称反推历史资格")
    elif not daily_status.get("valid"):
        promotion_blockers.append(
            f"逐日历史ST/停牌状态文件无效: {daily_status.get('error') or '未知错误'}"
        )
    elif not historical_status_ready:
        coverage_text = (
            f"{historical_status_coverage_pct:.2f}%"
            if historical_status_coverage_pct is not None
            else "--"
        )
        promotion_blockers.append(
            f"逐日历史ST/停牌状态覆盖仅{coverage_text}，未达到"
            f"{POINT_IN_TIME_COVERAGE_THRESHOLD_PCT:.0f}%门槛"
        )
    if benchmark is None or getattr(benchmark, "empty", True):
        promotion_blockers.append("缺少真实沪深300历史行情，不能计算基准超额")
    if not walk_forward.get("folds"):
        promotion_blockers.append("滚动样本外窗口不足")
    if selected_rule_id == "":
        promotion_blockers.append("没有规则通过正式胜率、Wilson、收益和利润因子门槛")
    return {
        "status": "ok",
        "strategy_rule_set_version": CANDIDATE_RULESET_VERSION,
        "rule_fingerprints": {
            rule_id: candidate_rule_fingerprint(rule_id)
            for rule_id in CANDIDATE_RULES
        },
        "method": {
            "data": "本地真实前复权日K缓存",
            "universe": (
                "历史成员区间内且逐日非ST、正常交易的沪深主板股票"
                if historical_status_available
                else "历史成员区间内的沪深主板股票；逐日ST/停牌状态缺失时仅研究不转正"
            ),
            "survivorship_bias": not bool(membership),
            "selection_time": "收盘后，仅使用当日及以前数据",
            "entry": "下一交易日买入区间触发，涨停一字板不成交",
            "exit": "买入后最早下一交易日，按止损优先、第一止盈、持有期收盘顺序",
            "estimated_round_trip_cost_pct": cost_pct,
            "top_n_per_signal_date": top_n,
            "train_end": str(train_end_date.date()),
            "study_start": str(pd.Timestamp(study_start).date()),
            "test_start": str((train_end_date + pd.Timedelta(days=1)).date()),
            "benchmark": (
                benchmark.attrs.get("data_source") or "真实基准文件"
                if benchmark is not None and not benchmark.empty
                else "不可用"
            ),
        },
        "universe_size": len(frames),
        "data_quality": {
            "point_in_time_universe": point_in_time_ready,
            "membership_available": bool(membership),
            "membership_symbols": len(membership or {}),
            "membership_expected_symbols": len(membership_expected),
            "membership_kline_symbols": len(membership_covered),
            "membership_kline_coverage_pct": (
                round(membership_coverage_pct, 2)
                if membership_coverage_pct is not None
                else None
            ),
            "historical_status_available": historical_status_available,
            "historical_status_source": (
                daily_status.get("source")
                if isinstance(daily_status, dict) and daily_status.get("valid")
                else None
            ),
            "historical_status_expected_symbols": len(membership_expected),
            "historical_status_complete_symbols": len(status_covered),
            "historical_status_coverage_pct": (
                round(historical_status_coverage_pct, 2)
                if historical_status_coverage_pct is not None
                else None
            ),
            "survivorship_bias": not point_in_time_ready,
            "benchmark_available": benchmark is not None and not benchmark.empty,
            "promotion_blockers": promotion_blockers,
        },
        "rules": rule_results,
        "selected_rule_id": selected_rule_id,
        "selected_rule": rule_results.get(selected_rule_id),
        "training_gate_rule_id": training_gate_rule_id,
        "training_gate_rule": rule_results.get(training_gate_rule_id),
        "training_leader_id": training_leader_id,
        "training_leader": rule_results.get(training_leader_id),
        "walk_forward": walk_forward,
        "execution_sensitivity": sensitivity,
    }


def build_trades(
    frames: dict[str, pd.DataFrame],
    *,
    rule_id: str,
    top_n: int,
    cost_pct: float,
    study_start: str,
    membership: dict[str, list[dict[str, str | None]]] | None = None,
    daily_status: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    study_start_date = pd.Timestamp(study_start).normalize()
    market_regime = _build_market_regime(frames) if rule_id in REGIME_FILTERED_RULE_IDS else {}
    for symbol, frame in frames.items():
        signal_mask = candidate_signal_mask(frame, rule_id=rule_id)
        positions = [
            frame.index.get_loc(index)
            for index in frame.index[signal_mask]
            if (
                index >= study_start_date
                and frame.index.get_loc(index) < len(frame) - 2
                and _eligible_on_date(symbol, index, membership, daily_status)
            )
        ]
        for position in positions:
            row = frame.iloc[position]
            metrics = {
                key: _number(row.get(key))
                for key in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount_20d",
                    "volume_ratio_20d",
                    "amount_ratio_20d",
                    "turnover",
                    "turnover_ratio_20d",
                    "ma5",
                    "ma10",
                    "ma20",
                    "ma60",
                    "ma120",
                    "return_1d",
                    "return_3d",
                    "return_20d",
                    "return_60d",
                    "volatility_20d",
                    "rsi_6",
                    "rsi_2",
                    "boll_mid",
                    "boll_upper",
                    "boll_lower",
                    "distance_to_high_60d",
                    "close_to_ma20",
                    "ma20_to_ma60",
                    "ma60_slope_5d",
                    "down_days_3",
                    "intraday_return",
                    "close_location",
                )
            }
            signal_date = str(frame.index[position])[:10]
            score = candidate_score(metrics, rule_id=rule_id)
            if score is None:
                continue
            candidates_by_date[signal_date].append({
                "symbol": symbol,
                "name": frame.attrs.get("name") or symbol,
                "position": position,
                "score": round(score, 3),
                "metrics": metrics,
                "levels": candidate_trade_levels(metrics, rule_id=rule_id),
            })

    trades = []
    for signal_date, candidates in sorted(candidates_by_date.items()):
        if rule_id in REGIME_FILTERED_RULE_IDS:
            regime = market_regime.get(signal_date) or {}
            if not regime.get("passed"):
                continue
        ranked = sorted(candidates, key=lambda item: (-item["score"], item["symbol"]))[:top_n]
        for candidate in ranked:
            frame = frames[candidate["symbol"]]
            trade = _simulate_trade(
                frame,
                candidate,
                signal_date=signal_date,
                rule_id=rule_id,
                cost_pct=cost_pct,
            )
            trades.append(trade)
    return trades


def _build_market_regime(frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    daily: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"above_ma20": [], "above_ma60": [], "return_20d": []}
    )
    for frame in frames.values():
        valid = frame[["close", "ma20", "ma60", "return_20d"]].dropna()
        for index, row in valid.iterrows():
            date = str(index)[:10]
            daily[date]["above_ma20"].append(float(row["close"] > row["ma20"]))
            daily[date]["above_ma60"].append(float(row["close"] > row["ma60"]))
            daily[date]["return_20d"].append(float(row["return_20d"]))
    result = {}
    for date, values in daily.items():
        count = len(values["return_20d"])
        breadth_20 = sum(values["above_ma20"]) / count if count else 0.0
        breadth_60 = sum(values["above_ma60"]) / count if count else 0.0
        median_20 = float(pd.Series(values["return_20d"]).median()) if count else None
        result[date] = {
            "stocks": count,
            "breadth_above_ma20": round(breadth_20, 4),
            "breadth_above_ma60": round(breadth_60, 4),
            "median_return_20d": round(median_20, 4) if median_20 is not None else None,
            "passed": (
                count >= 500
                and breadth_20 >= 0.55
                and breadth_60 >= 0.50
                and median_20 is not None
                and median_20 > 0
            ),
        }
    return result


def summarize_trades(
    trades: list[dict[str, Any]],
    *,
    benchmark: pd.DataFrame | None = None,
) -> dict[str, Any]:
    plan_dates = sorted({row["signal_date"] for row in trades})
    filled = [row for row in trades if row.get("status") == "completed"]
    result = {
        "signals": len(trades),
        "plan_dates": len(plan_dates),
        "filled": len(filled),
        "not_triggered": sum(1 for row in trades if row.get("status") == "not_triggered"),
        "untradeable": sum(1 for row in trades if row.get("status") == "untradeable"),
        "fill_rate_pct": round(len(filled) / len(trades) * 100, 2) if trades else None,
        "date_start": plan_dates[0] if plan_dates else None,
        "date_end": plan_dates[-1] if plan_dates else None,
        "horizons": {},
    }
    for horizon in HORIZONS:
        key = f"{horizon}d"
        returns = [row["returns"][key] for row in filled if row["returns"].get(key) is not None]
        wins = sum(value > 0 for value in returns)
        ci_low, ci_high = _wilson_interval(wins, len(returns))
        gains = sum(value for value in returns if value > 0)
        losses = abs(sum(value for value in returns if value <= 0))
        benchmark_returns, excess_returns = _benchmark_trade_returns(
            filled,
            benchmark,
            horizon_key=key,
        )
        result["horizons"][key] = {
            "samples": len(returns),
            "wins": wins,
            "win_rate_pct": round(wins / len(returns) * 100, 2) if returns else None,
            "wilson_low_pct": ci_low,
            "wilson_high_pct": ci_high,
            "avg_net_return_pct": round(sum(returns) / len(returns), 3) if returns else None,
            "median_net_return_pct": round(float(pd.Series(returns).median()), 3) if returns else None,
            "profit_factor": round(gains / losses, 3) if losses > 0 else None,
            "max_drawdown_pct": _max_drawdown(trades, key),
            "benchmark_samples": len(benchmark_returns),
            "avg_benchmark_return_pct": (
                round(sum(benchmark_returns) / len(benchmark_returns), 3)
                if benchmark_returns
                else None
            ),
            "avg_excess_return_pct": (
                round(sum(excess_returns) / len(excess_returns), 3)
                if excess_returns
                else None
            ),
        }
    return result


def build_walk_forward_analysis(
    rule_trades: dict[str, list[dict[str, Any]]],
    *,
    study_start: str,
    benchmark: pd.DataFrame | None,
    train_days: int = 120,
    test_days: int = 30,
) -> dict[str, Any]:
    """Select on rolling training windows and report the leader's next window."""
    all_dates = sorted({
        pd.Timestamp(row["signal_date"]).normalize()
        for trades in rule_trades.values()
        for row in trades
    })
    if not all_dates:
        return {"folds": [], "summary": {"folds": 0}}
    first_test_start = pd.Timestamp(study_start).normalize() + pd.Timedelta(days=train_days)
    last_date = all_dates[-1]
    folds = []
    test_start = first_test_start
    while test_start <= last_date:
        train_start = test_start - pd.Timedelta(days=train_days)
        train_end = test_start - pd.Timedelta(days=1)
        test_end = test_start + pd.Timedelta(days=test_days - 1)
        fold_rules = {}
        for rule_id, trades in rule_trades.items():
            train_rows = [
                row
                for row in trades
                if train_start <= pd.Timestamp(row["signal_date"]) <= train_end
            ]
            test_rows = [
                row
                for row in trades
                if test_start <= pd.Timestamp(row["signal_date"]) <= test_end
            ]
            fold_rules[rule_id] = {
                "rule_id": rule_id,
                "train": summarize_trades(train_rows, benchmark=benchmark),
                "test": summarize_trades(test_rows, benchmark=benchmark),
            }
        promoted = select_rule_from_training(fold_rules)
        leader = training_leader(fold_rules)
        evaluated_rule = promoted or leader
        evaluated = fold_rules.get(evaluated_rule) or {}
        test_stats = ((evaluated.get("test") or {}).get("horizons") or {}).get("1d") or {}
        folds.append({
            "train_start": train_start.date().isoformat(),
            "train_end": train_end.date().isoformat(),
            "test_start": test_start.date().isoformat(),
            "test_end": min(test_end, last_date).date().isoformat(),
            "promoted_rule_id": promoted,
            "training_leader_id": leader,
            "evaluated_rule_id": evaluated_rule,
            "formally_promoted": bool(promoted),
            "test_samples_1d": test_stats.get("samples", 0),
            "test_win_rate_1d_pct": test_stats.get("win_rate_pct"),
            "test_avg_net_return_1d_pct": test_stats.get("avg_net_return_pct"),
            "test_profit_factor_1d": test_stats.get("profit_factor"),
            "test_avg_excess_return_1d_pct": test_stats.get("avg_excess_return_pct"),
        })
        test_start += pd.Timedelta(days=test_days)
    evaluable = [row for row in folds if row["test_samples_1d"] > 0]
    positive = [
        row
        for row in evaluable
        if (row.get("test_avg_net_return_1d_pct") or 0) > 0
    ]
    return {
        "method": {
            "train_calendar_days": train_days,
            "test_calendar_days": test_days,
            "selection": "每个窗口只用训练段选规则，再读取下一段结果",
        },
        "folds": folds,
        "summary": {
            "folds": len(folds),
            "evaluable_folds": len(evaluable),
            "positive_test_folds": len(positive),
            "positive_test_fold_rate_pct": (
                round(len(positive) / len(evaluable) * 100, 2) if evaluable else None
            ),
            "formal_promotion_folds": sum(bool(row["formally_promoted"]) for row in folds),
        },
    }


def build_execution_sensitivity(
    trades: list[dict[str, Any]],
    *,
    base_top_n: int,
    base_cost_pct: float,
    train_end: str,
    benchmark: pd.DataFrame | None,
) -> dict[str, Any]:
    """Stress the training leader across position-count and cost assumptions."""
    if not trades:
        return {"scenarios": [], "summary": {"scenarios": 0}}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trades:
        grouped[row["signal_date"]].append(row)
    top_n_values = sorted({max(1, min(3, base_top_n)), max(1, base_top_n)})
    cost_values = sorted({round(base_cost_pct, 3), round(base_cost_pct + 0.10, 3)})
    train_end_date = pd.Timestamp(train_end).normalize()
    scenarios = []
    for top_n in top_n_values:
        selected = []
        for rows in grouped.values():
            selected.extend(sorted(rows, key=lambda item: (-float(item.get("score") or 0), item["symbol"]))[:top_n])
        for stressed_cost in cost_values:
            adjusted = _adjust_trade_costs(
                selected,
                cost_delta_pct=stressed_cost - base_cost_pct,
            )
            train_rows = [
                row
                for row in adjusted
                if pd.Timestamp(row["signal_date"]) <= train_end_date
            ]
            test_rows = [
                row
                for row in adjusted
                if pd.Timestamp(row["signal_date"]) > train_end_date
            ]
            train = summarize_trades(train_rows, benchmark=benchmark)
            test = summarize_trades(test_rows, benchmark=benchmark)
            scenarios.append({
                "top_n": top_n,
                "round_trip_cost_pct": stressed_cost,
                "train": train,
                "test": test,
                "train_positive": (
                    ((train.get("horizons") or {}).get("1d") or {}).get("avg_net_return_pct")
                    or 0
                ) > 0,
                "test_positive": (
                    ((test.get("horizons") or {}).get("1d") or {}).get("avg_net_return_pct")
                    or 0
                ) > 0,
            })
    return {
        "method": "训练领先规则的每日持仓数与往返成本压力测试",
        "scenarios": scenarios,
        "summary": {
            "scenarios": len(scenarios),
            "train_positive_scenarios": sum(row["train_positive"] for row in scenarios),
            "test_positive_scenarios": sum(row["test_positive"] for row in scenarios),
        },
    }


def select_rule_from_training(
    rule_results: dict[str, dict[str, Any]],
    *,
    eligible_rule_ids: set[str] | None = None,
) -> str:
    """Return only rules that pass the same formal promotion gate as production."""
    eligible = []
    for rule_id, row in rule_results.items():
        if eligible_rule_ids is not None and rule_id not in eligible_rule_ids:
            continue
        stats = row["train"]["horizons"]["1d"]
        if stats["samples"] < 100 or row["train"]["plan_dates"] < 20:
            continue
        if (stats["win_rate_pct"] or 0) < 55 or (stats["wilson_low_pct"] or 0) < 50:
            continue
        if (stats["avg_net_return_pct"] or 0) <= 0 or (stats["profit_factor"] or 0) <= 1:
            continue
        eligible.append((
            stats["wilson_low_pct"] or 0,
            stats["avg_net_return_pct"] or 0,
            stats["profit_factor"] or 0,
            rule_id,
        ))
    if eligible:
        return max(eligible)[-1]
    return ""


def select_rule_for_promotion(
    rule_results: dict[str, dict[str, Any]],
    *,
    eligible_rule_ids: set[str] | None = None,
) -> str:
    """Require both training and untouched out-of-sample performance."""
    eligible = []
    for rule_id, row in rule_results.items():
        if eligible_rule_ids is not None and rule_id not in eligible_rule_ids:
            continue
        train = row["train"]
        test = row["test"]
        train_stats = train["horizons"]["1d"]
        test_stats = test["horizons"]["1d"]
        if (
            train_stats["samples"] < 100
            or train["plan_dates"] < 20
            or (train_stats["win_rate_pct"] or 0) < 55
            or (train_stats["wilson_low_pct"] or 0) < 50
            or (train_stats["avg_net_return_pct"] or 0) <= 0
            or (train_stats["profit_factor"] or 0) <= 1
        ):
            continue
        if (
            test_stats["samples"] < 30
            or test["plan_dates"] < 10
            or (test_stats["win_rate_pct"] or 0) < 50
            or (test_stats["avg_net_return_pct"] or 0) <= 0
            or (test_stats["profit_factor"] or 0) <= 1
            or (test_stats["avg_excess_return_pct"] or 0) <= 0
            or test_stats["max_drawdown_pct"] is None
            or test_stats["max_drawdown_pct"] < -15
        ):
            continue
        eligible.append((
            test_stats["wilson_low_pct"] or 0,
            test_stats["avg_net_return_pct"] or 0,
            test_stats["profit_factor"] or 0,
            rule_id,
        ))
    return max(eligible)[-1] if eligible else ""


def training_leader(
    rule_results: dict[str, dict[str, Any]],
    *,
    eligible_rule_ids: set[str] | None = None,
) -> str:
    """Report the relative leader without implying that it passed promotion gates."""
    fallback = []
    for rule_id, row in rule_results.items():
        if eligible_rule_ids is not None and rule_id not in eligible_rule_ids:
            continue
        stats = row["train"]["horizons"]["1d"]
        fallback.append((
            stats["wilson_low_pct"] or 0,
            stats["avg_net_return_pct"] or -999,
            stats["samples"],
            rule_id,
        ))
    return max(fallback)[-1] if fallback else ""


def _simulate_trade(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    *,
    signal_date: str,
    rule_id: str,
    cost_pct: float,
) -> dict[str, Any]:
    position = int(candidate["position"])
    levels = candidate["levels"]
    entry_row = frame.iloc[position + 1]
    entry_date = str(frame.index[position + 1])[:10]
    previous_close = _number(frame.iloc[position].get("close"))
    entry_open = _number(entry_row.get("open"))
    entry_high = _number(entry_row.get("high"))
    entry_low = _number(entry_row.get("low"))
    base = {
        "rule_id": rule_id,
        "symbol": candidate["symbol"],
        "name": candidate["name"],
        "signal_date": signal_date,
        "entry_date": entry_date,
        "score": candidate["score"],
        "levels": levels,
        "returns": {},
    }
    if None in (previous_close, entry_open, entry_high, entry_low):
        return {**base, "status": "untradeable", "reason": "入场日价格缺失"}
    entry_change = entry_open / previous_close - 1
    one_price_limit_up = entry_change >= 0.095 and entry_open == entry_high == entry_low
    if one_price_limit_up or _number(entry_row.get("volume")) in (None, 0):
        return {**base, "status": "untradeable", "reason": "涨停一字板或停牌"}
    buy_low = _number(levels.get("buy_zone_low"))
    buy_high = _number(levels.get("buy_zone_high"))
    if buy_low is None or buy_high is None or entry_high < buy_low or entry_low > buy_high:
        return {**base, "status": "not_triggered", "reason": "入场日未触及买入区间"}
    entry_price = min(max(entry_open, buy_low), buy_high)
    returns = {}
    exit_dates = {}
    for horizon in HORIZONS:
        resolved = _resolve_exit(
            frame.iloc[position + 2 :],
            horizon=horizon,
            stop_loss=_number(levels.get("stop_loss")),
            take_profit=_number(levels.get("take_profit_1")),
            previous_close=_number(entry_row.get("close")),
        )
        key = f"{horizon}d"
        if resolved is None:
            returns[key] = None
            exit_dates[key] = None
            continue
        exit_price, exit_date = resolved
        returns[key] = round((exit_price / entry_price - 1) * 100 - cost_pct, 4)
        exit_dates[key] = exit_date
    return {
        **base,
        "status": "completed",
        "entry_price": round(entry_price, 3),
        "returns": returns,
        "exit_dates": exit_dates,
    }


def _resolve_exit(
    rows: pd.DataFrame,
    *,
    horizon: int,
    stop_loss: float | None,
    take_profit: float | None,
    previous_close: float | None,
) -> tuple[float, str] | None:
    pending_exit = False
    for holding_index, (index, row) in enumerate(rows.iterrows(), start=1):
        open_price = _number(row.get("open"))
        high = _number(row.get("high"))
        low = _number(row.get("low"))
        close = _number(row.get("close"))
        if None in (open_price, high, low, close):
            continue
        one_price_limit_down = (
            previous_close is not None
            and open_price / previous_close - 1 <= -0.095
            and open_price == high == low
        )
        stop_hit = stop_loss is not None and low <= stop_loss
        target_hit = take_profit is not None and high >= take_profit
        holding_period_ended = holding_index >= horizon
        if one_price_limit_down and (pending_exit or stop_hit or target_hit or holding_period_ended):
            pending_exit = True
            previous_close = close
            continue
        if pending_exit:
            return open_price, str(index)[:10]
        if stop_loss is not None and open_price <= stop_loss:
            return open_price, str(index)[:10]
        if take_profit is not None and open_price >= take_profit:
            return open_price, str(index)[:10]
        if stop_hit:
            return stop_loss, str(index)[:10]
        if target_hit:
            return take_profit, str(index)[:10]
        if holding_period_ended:
            return close, str(index)[:10]
        previous_close = close
    return None


def _max_drawdown(trades: list[dict[str, Any]], horizon_key: str) -> float | None:
    daily: dict[str, list[float]] = defaultdict(list)
    for row in trades:
        value = row.get("returns", {}).get(horizon_key)
        if row.get("status") == "completed" and value is not None:
            daily[row["signal_date"]].append(float(value) / 100)
    if not daily:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for date in sorted(daily):
        equity *= 1 + sum(daily[date]) / len(daily[date])
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    return round(max_drawdown * 100, 3)


def _benchmark_trade_returns(
    trades: list[dict[str, Any]],
    benchmark: pd.DataFrame | None,
    *,
    horizon_key: str,
) -> tuple[list[float], list[float]]:
    if benchmark is None or getattr(benchmark, "empty", True) or "close" not in benchmark.columns:
        return [], []
    close = pd.to_numeric(benchmark["close"], errors="coerce").dropna().sort_index()
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index, errors="coerce")
        close = close[close.index.notna()]
    benchmark_returns = []
    excess_returns = []
    for trade in trades:
        stock_return = (trade.get("returns") or {}).get(horizon_key)
        exit_date = (trade.get("exit_dates") or {}).get(horizon_key)
        entry_date = trade.get("entry_date")
        if stock_return is None or not entry_date or not exit_date:
            continue
        before_entry = close[close.index <= pd.Timestamp(entry_date)]
        before_exit = close[close.index <= pd.Timestamp(exit_date)]
        if before_entry.empty or before_exit.empty:
            continue
        entry_close = float(before_entry.iloc[-1])
        exit_close = float(before_exit.iloc[-1])
        if entry_close <= 0:
            continue
        benchmark_return = (exit_close / entry_close - 1) * 100
        benchmark_returns.append(benchmark_return)
        excess_returns.append(float(stock_return) - benchmark_return)
    return benchmark_returns, excess_returns


def _adjust_trade_costs(
    trades: list[dict[str, Any]],
    *,
    cost_delta_pct: float,
) -> list[dict[str, Any]]:
    adjusted = deepcopy(trades)
    for trade in adjusted:
        returns = trade.get("returns") or {}
        for key, value in list(returns.items()):
            if value is not None:
                returns[key] = round(float(value) - cost_delta_pct, 4)
    return adjusted


def load_membership_history(path: Path | None) -> dict[str, list[dict[str, str | None]]]:
    """Load point-in-time universe intervals from a real CSV or JSON file."""
    if path is None or not path.exists():
        return {}
    try:
        if path.suffix.lower() == ".csv":
            rows = pd.read_csv(path).to_dict("records")
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("memberships", []) if isinstance(payload, dict) else payload
    except Exception:
        return {}
    result: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("code") or "").strip()
        listed_date = _date_value(row.get("listed_date") or row.get("start_date"))
        delisted_date = _date_value(row.get("delisted_date") or row.get("end_date"))
        if symbol and listed_date:
            result[symbol].append({
                "listed_date": listed_date,
                "delisted_date": delisted_date,
            })
    return dict(result)


def load_benchmark_history(path: Path | None) -> pd.DataFrame | None:
    """Load real benchmark history without inventing missing prices."""
    if path is None or not path.exists():
        return None
    try:
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path)
            frame = frame.rename(columns={"日期": "date", "收盘": "close"})
            if "date" not in frame.columns:
                return None
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frame = frame.dropna(subset=["date"]).set_index("date")
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            frame = pd.DataFrame(payload["data"], columns=payload["columns"])
            frame.index = pd.to_datetime(payload["index"], errors="coerce")
            frame = frame[frame.index.notna()]
        frame.columns = [str(column).lower() for column in frame.columns]
        if "close" not in frame.columns:
            return None
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["close"]).sort_index()
        if frame.empty:
            return None
        frame.attrs["data_source"] = f"真实基准文件/{path.name}"
        return frame
    except Exception:
        return None


def load_daily_status_history(path: Path | None) -> dict[str, Any] | None:
    """Load compact real daily ST/suspension history for fail-closed filtering."""
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "valid": False,
            "error": f"状态文件读取失败: {exc}",
            "symbols": {},
            "trade_dates": set(),
        }
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "error": "状态文件根节点不是对象",
            "symbols": {},
            "trade_dates": set(),
        }
    if payload.get("real_data") is not True:
        return {
            "valid": False,
            "error": "状态文件未声明 real_data=true",
            "symbols": {},
            "trade_dates": set(),
        }
    raw_trade_dates = payload.get("trade_dates")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_trade_dates, list) or not isinstance(raw_symbols, dict):
        return {
            "valid": False,
            "error": "状态文件缺少 trade_dates 或 symbols",
            "symbols": {},
            "trade_dates": set(),
        }

    trade_dates = {_date_value(value) for value in raw_trade_dates}
    trade_dates.discard(None)
    if not trade_dates:
        return {
            "valid": False,
            "error": "状态文件没有有效交易日历",
            "symbols": {},
            "trade_dates": set(),
        }

    symbols: dict[str, dict[str, Any]] = {}
    for symbol, record in raw_symbols.items():
        if not isinstance(record, dict):
            continue
        symbols[str(symbol).zfill(6)] = {
            **record,
            "st_dates": {
                date_text
                for value in record.get("st_dates") or []
                if (date_text := _date_value(value))
            },
            "suspended_dates": {
                date_text
                for value in record.get("suspended_dates") or []
                if (date_text := _date_value(value))
            },
        }
    return {
        "valid": True,
        "error": None,
        "version": payload.get("version"),
        "source": payload.get("source"),
        "query": payload.get("query") if isinstance(payload.get("query"), dict) else {},
        "trade_dates": trade_dates,
        "symbols": symbols,
        "counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
    }


def _eligible_on_date(
    symbol: str,
    signal_date: Any,
    membership: dict[str, list[dict[str, str | None]]] | None,
    daily_status: dict[str, Any] | None = None,
) -> bool:
    date_text = _date_value(signal_date)
    if not date_text:
        return False
    if membership:
        intervals = membership.get(symbol) or []
        if not any(
            interval["listed_date"] <= date_text
            and (
                not interval.get("delisted_date")
                or date_text < str(interval["delisted_date"])
            )
            for interval in intervals
        ):
            return False
    if daily_status is None:
        return True
    if daily_status.get("valid") is not True:
        return False
    record = (daily_status.get("symbols") or {}).get(symbol)
    if not isinstance(record, dict) or record.get("complete") is not True:
        return False
    if date_text not in (daily_status.get("trade_dates") or set()):
        return False
    query_start = _date_value(record.get("query_start"))
    query_end = _date_value(record.get("query_end"))
    if not query_start or not query_end or not query_start <= date_text <= query_end:
        return False
    if date_text in (record.get("st_dates") or set()):
        return False
    if date_text in (record.get("suspended_dates") or set()):
        return False
    return True


def _membership_symbols_in_window(
    membership: dict[str, list[dict[str, str | None]]] | None,
    *,
    start_date: Any,
    end_date: Any,
) -> set[str]:
    if not membership:
        return set()
    start = _date_value(start_date)
    end = _date_value(end_date)
    if not start or not end:
        return set()
    return {
        symbol
        for symbol, intervals in membership.items()
        if any(
            interval["listed_date"] <= end
            and (not interval.get("delisted_date") or str(interval["delisted_date"]) >= start)
            for interval in intervals
        )
    }


def _historical_status_symbols_in_window(
    expected_symbols: set[str],
    *,
    membership: dict[str, list[dict[str, str | None]]] | None,
    daily_status: dict[str, Any] | None,
    start_date: Any,
    end_date: Any,
) -> set[str]:
    if (
        not expected_symbols
        or not membership
        or not isinstance(daily_status, dict)
        or daily_status.get("valid") is not True
    ):
        return set()
    start = _date_value(start_date)
    end = _date_value(end_date)
    trade_dates = sorted(daily_status.get("trade_dates") or [])
    symbols = daily_status.get("symbols") or {}
    if not start or not end or not trade_dates or not isinstance(symbols, dict):
        return set()

    covered = set()
    for symbol in expected_symbols:
        record = symbols.get(symbol)
        if not isinstance(record, dict) or record.get("complete") is not True:
            continue
        expected_dates = [
            trade_date
            for trade_date in trade_dates
            if start <= trade_date <= end
            and any(
                interval["listed_date"] <= trade_date
                and (
                    not interval.get("delisted_date")
                    or trade_date < str(interval["delisted_date"])
                )
                for interval in membership.get(symbol) or []
            )
        ]
        if not expected_dates:
            continue
        query_start = _date_value(record.get("query_start"))
        query_end = _date_value(record.get("query_end"))
        if (
            query_start
            and query_end
            and query_start <= expected_dates[0]
            and query_end >= expected_dates[-1]
        ):
            covered.add(symbol)
    return covered


def _date_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value, errors="raise").date().isoformat()
    except Exception:
        return None


def _wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    proportion = wins / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return round(max(0, center - margin) * 100, 2), round(min(1, center + margin) * 100, 2)


def _load_names(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(row.get("code") or ""): str(row.get("name") or "")
            for row in payload.get("stocks", [])
            if row.get("code")
        }
    except Exception:
        return {}


def _eligible_main_board(symbol: str, name: str) -> bool:
    return (
        symbol.startswith(MAIN_BOARD_PREFIXES)
        and "ST" not in name.upper()
        and "退" not in name
    )


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "strategy_kline_daily")
    parser.add_argument("--name-index", type=Path, default=ROOT / ".cache" / "stock_name_index.json")
    parser.add_argument("--train-end", default=DEFAULT_TRAIN_END)
    parser.add_argument("--study-start", default=DEFAULT_STUDY_START)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--cost-pct", type=float, default=DEFAULT_COST_PCT)
    parser.add_argument(
        "--membership-history",
        type=Path,
        default=None,
        help="真实历史股票池CSV/JSON，字段 symbol/listed_date/delisted_date",
    )
    parser.add_argument(
        "--daily-status-history",
        type=Path,
        default=ROOT / ".cache" / "research_daily_security_status.json",
        help="Baostock逐日历史ST/停牌状态JSON；缺失时研究可运行但禁止转正",
    )
    parser.add_argument(
        "--benchmark-history",
        type=Path,
        default=None,
        help="真实沪深300历史CSV或项目JSON缓存",
    )
    parser.add_argument(
        "--benchmark-live",
        action="store_true",
        help="通过项目现有AKShare口径获取真实沪深300历史行情",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="保存完整研究结果JSON；运行缓存不应提交",
    )
    args = parser.parse_args()
    membership = load_membership_history(args.membership_history)
    daily_status = load_daily_status_history(args.daily_status_history)
    frames = load_universe(
        args.cache_dir,
        args.name_index,
        membership=membership,
    )
    benchmark = load_benchmark_history(args.benchmark_history)
    if benchmark is None and args.benchmark_live:
        try:
            from ui.cached_data import get_cached_benchmark_data

            benchmark = get_cached_benchmark_data("000300", "1y", timeout_seconds=12)
        except Exception:
            benchmark = None
    result = run_research(
        frames,
        train_end=args.train_end,
        study_start=args.study_start,
        top_n=max(1, args.top_n),
        cost_pct=max(0.0, args.cost_pct),
        membership=membership,
        daily_status=daily_status,
        benchmark=benchmark,
    )
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(args.output, serialized)
        print(json.dumps({
            "output": str(args.output),
            "status": result.get("status"),
            "universe_size": result.get("universe_size"),
            "selected_rule_id": result.get("selected_rule_id"),
            "promotion_blockers": (result.get("data_quality") or {}).get("promotion_blockers"),
        }, ensure_ascii=False))
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
