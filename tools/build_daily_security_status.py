"""Build compact real daily ST/suspension history from Baostock."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.file_lock import atomic_write_text  # noqa: E402
from data.providers.baostock_status_provider import (  # noqa: E402
    BaostockProviderError,
    BaostockStatusProvider,
)
from tools.research_candidate_strategies import load_membership_history  # noqa: E402


DEFAULT_MEMBERSHIP_PATH = ROOT / ".cache" / "research_point_in_time_universe.json"
DEFAULT_OUTPUT_PATH = ROOT / ".cache" / "research_daily_security_status.json"
DEFAULT_STUDY_START = "2021-08-01"
STATUS_VERSION = "daily_security_status_v1"


def build_daily_security_status(
    membership: dict[str, list[dict[str, str | None]]],
    *,
    provider: Any,
    study_start: str,
    study_end: str,
    requested_symbols: list[str] | None = None,
    limit: int | None = None,
    existing_payload: dict[str, Any] | None = None,
    checkpoint_every: int = 50,
    checkpoint_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Query statuses sequentially and preserve verified complete checkpoints."""
    start = _date_text(study_start)
    end = _date_text(study_end)
    if not start or not end or start > end:
        raise ValueError(f"无效研究日期范围: {study_start!r} 至 {study_end!r}")

    trade_dates = provider.query_trade_dates(start, end)
    if not trade_dates:
        raise BaostockProviderError(f"{start} 至 {end}未返回真实交易日历")

    explicit = _normalize_symbols(requested_symbols)
    unknown_symbols = sorted(set(explicit) - set(membership))
    if unknown_symbols:
        raise ValueError(f"成员文件中不存在这些股票: {','.join(unknown_symbols[:20])}")

    candidates = explicit or sorted(membership)
    targets: list[tuple[str, list[str]]] = []
    for symbol in candidates:
        expected_dates = _expected_trade_dates(
            trade_dates,
            membership.get(symbol) or [],
            study_start=start,
            study_end=end,
        )
        if expected_dates:
            targets.append((symbol, expected_dates))
    if limit is not None:
        targets = targets[: max(0, int(limit))]

    reusable = _resume_symbols(
        existing_payload,
        study_start=start,
        study_end=end,
        trade_dates=trade_dates,
    )
    symbol_rows: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    reused = 0
    queried = 0

    for index, (symbol, expected_dates) in enumerate(targets, start=1):
        old_record = reusable.get(symbol)
        if old_record and _record_covers_expected_dates(old_record, expected_dates):
            symbol_rows[symbol] = old_record
            reused += 1
        else:
            queried += 1
            try:
                rows = _query_status_with_retry(
                    provider,
                    symbol,
                    expected_dates[0],
                    expected_dates[-1],
                )
                record = _compact_status_record(rows, expected_dates)
                symbol_rows[symbol] = record
                if not record["complete"]:
                    failures[symbol] = (
                        f"缺少{record['missing_trade_dates']}个应有交易日状态"
                    )
            except Exception as exc:
                symbol_rows[symbol] = {
                    "query_start": expected_dates[0],
                    "query_end": expected_dates[-1],
                    "expected_trade_dates": len(expected_dates),
                    "actual_trade_dates": 0,
                    "missing_trade_dates": len(expected_dates),
                    "complete": False,
                    "st_dates": [],
                    "suspended_dates": [],
                    "error": str(exc),
                }
                failures[symbol] = str(exc)

        if (
            checkpoint_callback
            and checkpoint_every > 0
            and (index % checkpoint_every == 0 or index == len(targets))
        ):
            checkpoint_callback(
                _build_payload(
                    study_start=start,
                    study_end=end,
                    trade_dates=trade_dates,
                    symbols=symbol_rows,
                    failures=failures,
                    requested=len(targets),
                    reused=reused,
                    queried=queried,
                    in_progress=index < len(targets),
                )
            )

    return _build_payload(
        study_start=start,
        study_end=end,
        trade_dates=trade_dates,
        symbols=symbol_rows,
        failures=failures,
        requested=len(targets),
        reused=reused,
        queried=queried,
        in_progress=False,
    )


def _query_status_with_retry(
    provider: Any,
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return provider.query_daily_status(symbol, start_date, end_date)
        except Exception as exc:
            last_error = exc
            reconnect = getattr(provider, "reconnect", None)
            if attempt == 0 and callable(reconnect):
                reconnect()
                continue
            break
    raise BaostockProviderError(f"{symbol}逐日状态查询失败: {last_error}")


def _compact_status_record(
    rows: list[dict[str, Any]],
    expected_dates: list[str],
) -> dict[str, Any]:
    expected = set(expected_dates)
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_date = _date_text(row.get("date"))
        if not row_date or row_date not in expected:
            continue
        if row_date in by_date:
            raise BaostockProviderError(f"{row_date}返回了重复证券状态")
        by_date[row_date] = row

    actual_dates = set(by_date)
    missing_dates = sorted(expected - actual_dates)
    return {
        "query_start": expected_dates[0],
        "query_end": expected_dates[-1],
        "expected_trade_dates": len(expected_dates),
        "actual_trade_dates": len(actual_dates),
        "missing_trade_dates": len(missing_dates),
        "missing_dates_preview": missing_dates[:10],
        "complete": not missing_dates,
        "st_dates": sorted(
            row_date for row_date, row in by_date.items() if bool(row.get("is_st"))
        ),
        "suspended_dates": sorted(
            row_date
            for row_date, row in by_date.items()
            if int(row.get("trade_status") or 0) != 1
        ),
    }


def _expected_trade_dates(
    trade_dates: list[str],
    intervals: list[dict[str, str | None]],
    *,
    study_start: str,
    study_end: str,
) -> list[str]:
    return [
        trade_date
        for trade_date in trade_dates
        if study_start <= trade_date <= study_end
        and any(
            str(interval.get("listed_date") or "") <= trade_date
            and (
                not interval.get("delisted_date")
                or trade_date < str(interval["delisted_date"])
            )
            for interval in intervals
        )
    ]


def _resume_symbols(
    existing_payload: dict[str, Any] | None,
    *,
    study_start: str,
    study_end: str,
    trade_dates: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(existing_payload, dict):
        return {}
    query = existing_payload.get("query") or {}
    if (
        existing_payload.get("version") != STATUS_VERSION
        or query.get("study_start") != study_start
        or query.get("study_end") != study_end
        or existing_payload.get("trade_dates") != trade_dates
    ):
        return {}
    symbols = existing_payload.get("symbols")
    return symbols if isinstance(symbols, dict) else {}


def _record_covers_expected_dates(
    record: dict[str, Any],
    expected_dates: list[str],
) -> bool:
    return bool(
        isinstance(record, dict)
        and record.get("complete") is True
        and record.get("query_start") <= expected_dates[0]
        and record.get("query_end") >= expected_dates[-1]
        and int(record.get("expected_trade_dates") or 0) == len(expected_dates)
        and int(record.get("actual_trade_dates") or 0) == len(expected_dates)
    )


def _build_payload(
    *,
    study_start: str,
    study_end: str,
    trade_dates: list[str],
    symbols: dict[str, dict[str, Any]],
    failures: dict[str, str],
    requested: int,
    reused: int,
    queried: int,
    in_progress: bool,
) -> dict[str, Any]:
    complete = sum(bool(record.get("complete")) for record in symbols.values())
    return {
        "version": STATUS_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Baostock证券宝公开历史行情字段 tradestatus/isST",
        "real_data": True,
        "status": "building" if in_progress else ("ok" if not failures else "partial"),
        "query": {
            "study_start": study_start,
            "study_end": study_end,
        },
        "trade_dates": trade_dates,
        "symbols": dict(sorted(symbols.items())),
        "failures": [
            {"symbol": symbol, "error": error}
            for symbol, error in sorted(failures.items())
        ],
        "counts": {
            "requested_symbols": requested,
            "processed_symbols": len(symbols),
            "complete_symbols": complete,
            "failed_or_incomplete_symbols": len(symbols) - complete,
            "coverage_pct": round(complete / requested * 100, 2) if requested else None,
            "reused_symbols": reused,
            "queried_symbols": queried,
            "trade_dates": len(trade_dates),
        },
        "storage": {
            "format": "compact_anomaly_dates",
            "normal_dates_omitted": True,
            "completeness_evidence": (
                "每只股票保存应有/实有交易日数；仅 complete=true 时正常日期可由全局交易日历恢复"
            ),
        },
    }


def _normalize_symbols(symbols: list[str] | None) -> list[str]:
    result = []
    for value in symbols or []:
        for item in str(value).split(","):
            symbol = item.strip()
            if symbol:
                result.append(symbol.zfill(6))
    return sorted(set(result))


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except (TypeError, ValueError):
        return None


def _load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _save_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--membership-history", type=Path, default=DEFAULT_MEMBERSHIP_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--study-start", default=DEFAULT_STUDY_START)
    parser.add_argument(
        "--study-end",
        default=datetime.now().date().isoformat(),
    )
    parser.add_argument(
        "--symbols",
        action="append",
        default=[],
        help="只查询指定股票，可重复传入或使用逗号分隔",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args()

    membership = load_membership_history(args.membership_history)
    if not membership:
        raise SystemExit(f"未读取到真实历史成员文件: {args.membership_history}")

    def checkpoint(payload: dict[str, Any]) -> None:
        _save_payload(args.output, payload)
        counts = payload["counts"]
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "processed": counts["processed_symbols"],
                    "requested": counts["requested_symbols"],
                    "complete": counts["complete_symbols"],
                    "failed": counts["failed_or_incomplete_symbols"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    existing = _load_existing(args.output)
    with BaostockStatusProvider(timeout_seconds=args.timeout_seconds) as provider:
        payload = build_daily_security_status(
            membership,
            provider=provider,
            study_start=args.study_start,
            study_end=args.study_end,
            requested_symbols=args.symbols,
            limit=args.limit,
            existing_payload=existing,
            checkpoint_every=max(1, args.checkpoint_every),
            checkpoint_callback=checkpoint,
        )
    _save_payload(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": payload["status"],
                **payload["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
