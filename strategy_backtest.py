"""Read-only validation of saved real T+1 recommendation plans."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import RUNTIME_CACHE_DIR
from data.periods import assess_period_coverage, get_period_spec, period_start
from quality_monitor import build_plan_history_identity
from experimental_strategy import (
    EXPERIMENTAL_STRATEGY_NAME,
    build_experimental_validation_gate,
    sample_tier,
    wilson_interval,
)


STRATEGIES = ("短线", "短线经典版", "激进突破型", "多因子稳健型", EXPERIMENTAL_STRATEGY_NAME)
HORIZONS = (1, 5, 20)


class _StrategyOutcomeQuoteService:
    """Reuse real strategy K-line files before making any network request."""

    def __init__(self, fallback: Any):
        self.fallback = fallback
        self.cache_dir = Path(RUNTIME_CACHE_DIR) / "strategy_kline_daily"
        self._memory: dict[tuple[str, str], pd.DataFrame | None] = {}

    def get_stock_data(self, symbol: str, period: str = "3mo", market: str = "CN"):
        key = (str(symbol), str(period))
        if key in self._memory:
            return self._memory[key]
        candidates = []
        requested_days = get_period_spec(period).calendar_days
        for candidate_period in ("3mo", "6mo", "1y", "2y", "5y"):
            if get_period_spec(candidate_period).calendar_days < requested_days:
                continue
            candidates.extend(self.cache_dir.glob(f"CN_{symbol}_{candidate_period}_1d_*.json"))
        cached_frames = []
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                frame = pd.DataFrame(payload["data"], columns=payload["columns"])
                frame.index = pd.to_datetime(payload["index"], errors="coerce")
                frame = frame[frame.index.notna()]
                if not frame.empty:
                    cached_frames.append((frame.index.max(), len(frame), path, frame))
            except Exception:
                continue
        if cached_frames:
            _, _, path, frame = max(cached_frames, key=lambda item: (item[0], item[1]))
            frame.attrs["data_source"] = "策略K线本地真实缓存"
            frame.attrs["cache_file"] = path.name
            self._memory[key] = frame
            return frame
        frame = self.fallback.get_stock_data(symbol, period=period, market=market)
        self._memory[key] = frame
        return frame


def _plan_date(row: dict[str, Any], plan: dict[str, Any]) -> str:
    return str(
        plan.get("plan_for_trade_date")
        or row.get("plan_for_trade_date")
        or plan.get("generated_trade_date")
        or plan.get("generated_at")
        or row.get("generated_at")
        or ""
    )[:10]


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _win_rate(values: list[float]) -> float | None:
    return round(sum(1 for value in values if value > 0) / len(values) * 100, 2) if values else None


class StrategyBacktestAdapter:
    """Aggregate actual saved strategy selections against later real closes."""

    def __init__(self, service: Any | None = None):
        if service is None:
            from recommendation_service import RecommendationService

            service = RecommendationService()
        self.service = service
        fallback_quote_service = getattr(service, "quote_service", None)
        self.outcome_quote_service = (
            _StrategyOutcomeQuoteService(fallback_quote_service)
            if fallback_quote_service is not None
            else None
        )

    def run(self, period: str = "1y") -> dict[str, Any]:
        spec = get_period_spec(period)
        requested_end = pd.Timestamp.now().normalize()
        requested_start = period_start(period, requested_end)
        history = self.service.list_t1_plan_history(limit=5000)

        selected: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        seen_plans = set()
        for row in history:
            plan = row.get("plan") or {}
            strategy = str(plan.get("strategy") or row.get("strategy") or "")
            trade_date = _plan_date(row, plan)
            parsed_date = pd.to_datetime(trade_date, errors="coerce")
            if strategy not in STRATEGIES or pd.isna(parsed_date):
                continue
            identity = build_plan_history_identity(plan)
            if identity in seen_plans:
                continue
            if requested_start <= parsed_date.normalize() <= requested_end:
                seen_plans.add(identity)
                selected.append((row, plan, trade_date))

        buckets: dict[str, dict[str, Any]] = {
            strategy: {
                "strategy": strategy,
                "plans": 0,
                "recommended": 0,
                "completed": 0,
                "pending": 0,
                "not_triggered": 0,
                "returns": defaultdict(list),
                "dates": [],
            }
            for strategy in STRATEGIES
        }
        plan_rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []

        for row, plan, trade_date in selected:
            strategy = str(plan.get("strategy") or row.get("strategy") or "")
            if self.outcome_quote_service is None:
                outcome = self.service.evaluate_t1_plan_outcomes(plan)
            else:
                from quality_monitor import evaluate_plan_outcomes

                outcome = evaluate_plan_outcomes(plan, quote_service=self.outcome_quote_service)
            items = outcome.get("items") or []
            bucket = buckets[strategy]
            bucket["plans"] += 1
            bucket["recommended"] += len(items)
            bucket["dates"].append(trade_date)
            completed_count = 0
            pending_count = 0
            not_triggered_count = 0
            for item in items:
                returns = item.get("returns") or {}
                available = False
                for horizon in HORIZONS:
                    value = returns.get(f"{horizon}d")
                    if value is not None:
                        bucket["returns"][horizon].append(float(value))
                        available = True
                if available:
                    completed_count += 1
                elif item.get("status") == "not_triggered":
                    not_triggered_count += 1
                else:
                    pending_count += 1
                detail_rows.append(
                    {
                        "strategy": strategy,
                        "sector": plan.get("sector") or row.get("sector") or "--",
                        "plan_date": trade_date,
                        "symbol": item.get("symbol"),
                        "name": item.get("name"),
                        "status": item.get("status"),
                        "return_1d_pct": returns.get("1d"),
                        "return_5d_pct": returns.get("5d"),
                        "return_20d_pct": returns.get("20d"),
                        "reason": item.get("reason") or "",
                    }
                )
            bucket["completed"] += completed_count
            bucket["pending"] += pending_count
            bucket["not_triggered"] += not_triggered_count
            plan_rows.append(
                {
                    "strategy": strategy,
                    "sector": plan.get("sector") or row.get("sector") or "--",
                    "plan_date": trade_date,
                    "recommended": len(items),
                    "completed": completed_count,
                    "pending": pending_count,
                    "not_triggered": not_triggered_count,
                }
            )

        strategy_rows = []
        for strategy in STRATEGIES:
            bucket = buckets[strategy]
            returns = bucket.pop("returns")
            dates = bucket.pop("dates")
            row = dict(bucket)
            row["actual_start"] = min(dates) if dates else None
            row["actual_end"] = max(dates) if dates else None
            row["distinct_plan_dates"] = len(set(dates))
            for horizon in HORIZONS:
                values = returns[horizon]
                row[f"samples_{horizon}d"] = len(values)
                row[f"wins_{horizon}d"] = sum(value > 0 for value in values)
                row[f"avg_{horizon}d_return_pct"] = _average(values)
                row[f"win_rate_{horizon}d_pct"] = _win_rate(values)
                ci_low, ci_high = wilson_interval(row[f"wins_{horizon}d"], len(values))
                row[f"win_rate_{horizon}d_ci_low_pct"] = ci_low
                row[f"win_rate_{horizon}d_ci_high_pct"] = ci_high
            row["sample_tier"] = sample_tier(row["samples_1d"])
            if row["plans"] == 0:
                row["conclusion"] = "无历史计划"
            elif row["completed"] == 0:
                row["conclusion"] = "等待后续数据"
            elif row["samples_1d"] < 30:
                row["conclusion"] = "仅观察"
            elif row["avg_1d_return_pct"] is not None and row["avg_1d_return_pct"] < 0:
                row["conclusion"] = "近期偏弱"
            elif (
                row["avg_1d_return_pct"] is not None
                and row["avg_1d_return_pct"] > 0
                and row["win_rate_1d_pct"] is not None
                and row["win_rate_1d_pct"] >= 50
            ):
                row["conclusion"] = "近期占优"
            else:
                row["conclusion"] = "表现一般"
            if strategy == EXPERIMENTAL_STRATEGY_NAME:
                row["validation_gate"] = build_experimental_validation_gate(row)
                row["conclusion"] = row["validation_gate"]["label"]
            strategy_rows.append(row)

        all_dates = [trade_date for _, _, trade_date in selected]
        coverage_frame = (
            pd.DataFrame({"plan": [1] * len(all_dates)}, index=pd.to_datetime(all_dates))
            if all_dates
            else None
        )
        coverage = assess_period_coverage(coverage_frame, period, end=requested_end)
        return {
            "period": period,
            "period_label": spec.label,
            "requested_start": requested_start.strftime("%Y-%m-%d"),
            "requested_end": requested_end.strftime("%Y-%m-%d"),
            "coverage": coverage,
            "strategies": strategy_rows,
            "plans": plan_rows,
            "details": detail_rows,
            "summary": {
                "strategy_count": len(STRATEGIES),
                "strategies_with_plans": sum(1 for row in strategy_rows if row["plans"] > 0),
                "plan_count": len(plan_rows),
                "recommended_count": sum(row["recommended"] for row in strategy_rows),
                "completed_count": sum(row["completed"] for row in strategy_rows),
            },
            "source": "已保存的真实T+1推荐计划 + 买入区间触发 + 后续真实日K",
        }
