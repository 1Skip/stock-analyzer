"""Build a real A-share main-board membership history from exchange-facing APIs."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.file_lock import atomic_write_text  # noqa: E402
from data.runtime import run_with_timeout  # noqa: E402


DEFAULT_OUTPUT = ROOT / ".cache" / "research_point_in_time_universe.json"
MAIN_BOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")


def build_membership_rows(
    sh_current: pd.DataFrame,
    sz_current: pd.DataFrame,
    sh_delisted: pd.DataFrame,
    sz_delisted: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Normalize current and delisted exchange records without invented dates."""
    rows: dict[str, dict[str, Any]] = {}

    for record in _records(sh_current):
        _add_row(
            rows,
            symbol=record.get("证券代码"),
            name=record.get("公司简称") or record.get("证券简称"),
            listed_date=record.get("上市日期"),
            delisted_date=None,
            exchange="SH",
            status="listed",
            source="AKShare/上交所主板A股列表",
        )
    for record in _records(sz_current):
        if str(record.get("板块") or "").strip() != "主板":
            continue
        _add_row(
            rows,
            symbol=record.get("A股代码"),
            name=record.get("A股简称"),
            listed_date=record.get("A股上市日期"),
            delisted_date=None,
            exchange="SZ",
            status="listed",
            source="AKShare/深交所A股列表",
            industry=record.get("所属行业"),
        )
    for record in _records(sh_delisted):
        _add_row(
            rows,
            symbol=record.get("公司代码"),
            name=record.get("公司简称"),
            listed_date=record.get("上市日期"),
            delisted_date=record.get("暂停上市日期"),
            exchange="SH",
            status="delisted_or_suspended",
            source="AKShare/上交所暂停终止上市列表",
            end_date_semantics="暂停上市日期",
        )
    for record in _records(sz_delisted):
        _add_row(
            rows,
            symbol=record.get("证券代码"),
            name=record.get("证券简称"),
            listed_date=record.get("上市日期"),
            delisted_date=record.get("终止上市日期"),
            exchange="SZ",
            status="delisted",
            source="AKShare/深交所终止上市列表",
            end_date_semantics="终止上市日期",
        )
    return sorted(rows.values(), key=lambda row: (row["symbol"], row["listed_date"]))


def fetch_membership_history(*, timeout_seconds: float = 30) -> dict[str, Any]:
    import akshare as ak

    sources = {
        "sh_current": run_with_timeout(
            lambda: ak.stock_info_sh_name_code(symbol="主板A股"),
            timeout_seconds,
        ),
        "sz_current": run_with_timeout(
            lambda: ak.stock_info_sz_name_code(symbol="A股列表"),
            timeout_seconds,
        ),
        "sh_delisted": run_with_timeout(ak.stock_info_sh_delist, timeout_seconds),
        "sz_delisted": run_with_timeout(ak.stock_info_sz_delist, timeout_seconds),
    }
    rows = build_membership_rows(**sources)
    return {
        "version": "point_in_time_universe_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "AKShare封装的上交所/深交所公开列表",
        "real_data": True,
        "memberships": rows,
        "counts": {
            "memberships": len(rows),
            "listed": sum(row["status"] == "listed" for row in rows),
            "delisted_or_suspended": sum(row["status"] != "listed" for row in rows),
        },
        "limitations": [
            "上交所历史列表提供暂停上市日期，不等同于每只股票最终退市日期",
            "历史ST状态需要独立时点数据，不能从当前名称反推",
            "成员文件不自动补齐对应股票的历史日K",
        ],
    }


def _add_row(
    rows: dict[str, dict[str, Any]],
    *,
    symbol: Any,
    name: Any,
    listed_date: Any,
    delisted_date: Any,
    exchange: str,
    status: str,
    source: str,
    industry: Any = None,
    end_date_semantics: str | None = None,
) -> None:
    symbol_text = str(symbol or "").strip().zfill(6)
    listed_text = _date_text(listed_date)
    delisted_text = _date_text(delisted_date)
    if not symbol_text.startswith(MAIN_BOARD_PREFIXES) or not listed_text:
        return
    candidate = {
        "symbol": symbol_text,
        "name": str(name or symbol_text).strip(),
        "listed_date": listed_text,
        "delisted_date": delisted_text,
        "exchange": exchange,
        "status": status,
        "source": source,
        "industry": str(industry or "").strip() or None,
        "end_date_semantics": end_date_semantics,
    }
    existing = rows.get(symbol_text)
    if existing is None or (existing.get("status") != "listed" and status == "listed"):
        rows[symbol_text] = candidate


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict("records")


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value, errors="raise").date().isoformat()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    payload = fetch_membership_history(timeout_seconds=max(1, args.timeout_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.output, json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"output": str(args.output), **payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
