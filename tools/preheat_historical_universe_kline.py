"""Fill missing point-in-time-universe K-lines from existing real data providers."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.file_lock import atomic_write_text  # noqa: E402
from data.periods import get_period_spec, period_date_range  # noqa: E402
from data.providers.baostock_status_provider import BaostockStatusProvider  # noqa: E402
from recommendation_modules.strategy_cache import (  # noqa: E402
    _has_requested_period_coverage,
    get_strategy_stock_data,
)
from stock_recommendation import StockRecommender  # noqa: E402
from tools.research_candidate_strategies import (  # noqa: E402
    load_membership_history,
    load_universe,
)


def expected_symbols(
    membership: dict[str, list[dict[str, str | None]]],
    *,
    study_start: str,
    study_end: str,
    minimum_history_calendar_days: int = 120,
) -> set[str]:
    history_cutoff = (
        pd.Timestamp(study_end).normalize()
        - pd.Timedelta(days=max(0, minimum_history_calendar_days))
    ).date().isoformat()
    return {
        symbol
        for symbol, intervals in membership.items()
        if any(
            interval["listed_date"] <= history_cutoff
            and (
                not interval.get("delisted_date")
                or str(interval["delisted_date"]) >= study_start
            )
            for interval in intervals
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--membership-history",
        type=Path,
        default=ROOT / ".cache" / "research_point_in_time_universe.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / ".cache" / "strategy_kline_daily",
    )
    parser.add_argument(
        "--name-index",
        type=Path,
        default=ROOT / ".cache" / "stock_name_index.json",
    )
    parser.add_argument("--study-start", default="2025-11-01")
    parser.add_argument("--study-end", default=pd.Timestamp.now().date().isoformat())
    parser.add_argument("--period", default="1y")
    parser.add_argument("--min-rows", type=int, default=0)
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument(
        "--upgrade-all",
        action="store_true",
        help="把研究期全部成员升级到指定周期，而不只补缺失股票",
    )
    parser.add_argument(
        "--baostock-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="既有真实行情源失败后，顺序使用Baostock前复权日K补缺",
    )
    parser.add_argument("--baostock-timeout-seconds", type=float, default=15)
    args = parser.parse_args()

    membership = load_membership_history(args.membership_history)
    before = load_universe(
        args.cache_dir,
        args.name_index,
        membership=membership,
    )
    expected = expected_symbols(
        membership,
        study_start=args.study_start,
        study_end=args.study_end,
    )
    minimum_rows = args.min_rows or get_period_spec(args.period).minimum_rows
    if args.upgrade_all:
        missing = sorted(
            symbol
            for symbol in expected
            if symbol not in before
            or not _has_requested_period_coverage(before[symbol], args.period)
            or not _has_research_capital_fields(before[symbol])
        )
    else:
        missing = sorted(expected - set(before))
    owner = StockRecommender()
    refreshed = []
    failed = []

    def fetch(symbol: str) -> tuple[str, int]:
        frame = get_strategy_stock_data(
            owner,
            symbol,
            period=args.period,
            interval="1d",
            market="CN",
        )
        rows = (
            0
            if frame is None or not _has_research_capital_fields(frame)
            else len(frame)
        )
        if rows >= minimum_rows:
            _save_research_kline(
                args.cache_dir,
                symbol=symbol,
                period=args.period,
                frame=frame,
            )
        return symbol, rows

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        futures = {executor.submit(fetch, symbol): symbol for symbol in missing}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, rows = future.result()
            except Exception:
                rows = 0
            if rows >= minimum_rows:
                refreshed.append(symbol)
            else:
                failed.append(symbol)

    baostock_refreshed = []
    if failed and args.baostock_fallback:
        legacy_failed = list(failed)
        failed = []
        start_raw, end_raw = period_date_range(args.period)
        query_start = pd.to_datetime(start_raw, errors="raise").date().isoformat()
        query_end = pd.to_datetime(end_raw, errors="raise").date().isoformat()
        with BaostockStatusProvider(
            timeout_seconds=max(1, args.baostock_timeout_seconds)
        ) as provider:
            for symbol in legacy_failed:
                try:
                    frame = provider.query_daily_bars(
                        symbol,
                        query_start,
                        query_end,
                    )
                    if frame is None or len(frame) < minimum_rows:
                        failed.append(symbol)
                        continue
                    _save_research_kline(
                        args.cache_dir,
                        symbol=symbol,
                        period=args.period,
                        frame=frame,
                    )
                    refreshed.append(symbol)
                    baostock_refreshed.append(symbol)
                except Exception:
                    failed.append(symbol)

    after = load_universe(
        args.cache_dir,
        args.name_index,
        membership=membership,
    )
    covered = expected & set(after)
    period_covered = {
        symbol
        for symbol in expected & set(after)
        if _has_requested_period_coverage(after[symbol], args.period)
    }
    print(json.dumps({
        "status": "ok",
        "expected": len(expected),
        "before": len(expected & set(before)),
        "missing_before": len(missing),
        "refreshed": len(refreshed),
        "baostock_refreshed": len(baostock_refreshed),
        "failed": len(failed),
        "covered_after": len(covered),
        "coverage_after_pct": round(len(covered) / len(expected) * 100, 2) if expected else None,
        "period": args.period,
        "period_covered_after": len(period_covered),
        "period_coverage_after_pct": (
            round(len(period_covered) / len(expected) * 100, 2) if expected else None
        ),
        "failed_symbols": sorted(failed),
        "source_policy": "项目既有真实行情源优先，Baostock顺序兜底，缺失不造数",
    }, ensure_ascii=False))
    return 0


def _save_research_kline(
    cache_dir: Path,
    *,
    symbol: str,
    period: str,
    frame: pd.DataFrame,
) -> Path:
    """Save one verified real frame in the existing split-orient cache format."""
    if frame is None or frame.empty:
        raise ValueError(f"{symbol}没有可保存的真实日K")
    last_date = pd.Timestamp(frame.index.max()).date().isoformat()
    path = cache_dir / f"CN_{symbol}_{period}_1d_{last_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, frame.to_json(orient="split", date_format="iso"))
    return path


def _has_research_capital_fields(frame: pd.DataFrame | None) -> bool:
    """Require observed amount plus real turnover or shares for capital features."""
    if frame is None or frame.empty:
        return False
    columns = {str(column).lower() for column in frame.columns}
    return (
        {"open", "high", "low", "close", "volume", "amount"} <= columns
        and bool({"turnover", "turnover_rate", "outstanding_share"} & columns)
    )


if __name__ == "__main__":
    raise SystemExit(main())
