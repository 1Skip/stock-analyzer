"""Shared period definitions and historical-data coverage checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PeriodSpec:
    code: str
    label: str
    calendar_days: int
    minimum_rows: int
    months: int = 0
    years: int = 0


PERIOD_SPECS: dict[str, PeriodSpec] = {
    "1wk": PeriodSpec("1wk", "1周", 7, 2),
    "1mo": PeriodSpec("1mo", "1月", 31, 10, months=1),
    "3mo": PeriodSpec("3mo", "3月", 93, 30, months=3),
    "6mo": PeriodSpec("6mo", "6月", 186, 60, months=6),
    "1y": PeriodSpec("1y", "1年", 366, 120, years=1),
    "2y": PeriodSpec("2y", "2年", 731, 240, years=2),
    "5y": PeriodSpec("5y", "5年", 1827, 600, years=5),
}

PERIOD_DAYS = {code: spec.calendar_days for code, spec in PERIOD_SPECS.items()}
ANALYSIS_PERIOD_CODES = tuple(PERIOD_SPECS)
BACKTEST_PERIOD_CODES = ("6mo", "1y", "2y", "5y")


def get_period_spec(period: str) -> PeriodSpec:
    try:
        return PERIOD_SPECS[str(period)]
    except KeyError as exc:
        raise ValueError(f"不支持的数据周期: {period}") from exc


def period_start(period: str, end: Any | None = None) -> pd.Timestamp:
    spec = get_period_spec(period)
    end_ts = pd.Timestamp(end if end is not None else pd.Timestamp.now()).normalize()
    if spec.years:
        return end_ts - pd.DateOffset(years=spec.years)
    if spec.months:
        return end_ts - pd.DateOffset(months=spec.months)
    return end_ts - pd.Timedelta(days=spec.calendar_days)


def period_date_range(period: str, end: Any | None = None) -> tuple[str, str]:
    end_ts = pd.Timestamp(end if end is not None else pd.Timestamp.now()).normalize()
    start_ts = period_start(period, end_ts)
    return start_ts.strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")


def period_for_start_date(start: Any, end: Any | None = None) -> str:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end if end is not None else pd.Timestamp.now()).normalize()
    for code in ANALYSIS_PERIOD_CODES:
        if period_start(code, end_ts) <= start_ts:
            return code
    return "5y"


def slice_period(data: pd.DataFrame, period: str, end: Any | None = None) -> pd.DataFrame:
    if data is None or data.empty:
        return data
    frame = data
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[frame.index.notna()]
    end_ts = pd.Timestamp(end).normalize() if end is not None else frame.index.max().normalize()
    return frame[frame.index >= period_start(period, end_ts)].copy()


def assess_period_coverage(
    data: pd.DataFrame | None,
    period: str,
    *,
    end: Any | None = None,
    tolerance_days: int = 10,
) -> dict[str, Any]:
    spec = get_period_spec(period)
    requested_end = pd.Timestamp(end if end is not None else pd.Timestamp.now()).normalize()
    requested_start = period_start(period, requested_end)
    result: dict[str, Any] = {
        "period": period,
        "period_label": spec.label,
        "requested_start": requested_start.strftime("%Y-%m-%d"),
        "requested_end": requested_end.strftime("%Y-%m-%d"),
        "actual_start": None,
        "actual_end": None,
        "rows": 0,
        "minimum_rows": spec.minimum_rows,
        "coverage_ratio": 0.0,
        "status": "empty",
        "is_complete": False,
    }
    if data is None or getattr(data, "empty", True):
        return result

    index = data.index
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.to_datetime(index, errors="coerce")
    index = pd.DatetimeIndex(index).dropna()
    if index.empty:
        result["status"] = "invalid_index"
        return result

    actual_start = index.min().normalize()
    actual_end = index.max().normalize()
    rows = len(index)
    requested_span = max((requested_end - requested_start).days, 1)
    actual_span = max((min(actual_end, requested_end) - max(actual_start, requested_start)).days, 0)
    start_covered = actual_start <= requested_start + pd.Timedelta(days=tolerance_days)
    row_count_covered = rows >= spec.minimum_rows
    complete = bool(start_covered and row_count_covered)
    result.update(
        {
            "actual_start": actual_start.strftime("%Y-%m-%d"),
            "actual_end": actual_end.strftime("%Y-%m-%d"),
            "rows": rows,
            "coverage_ratio": round(min(actual_span / requested_span, 1.0), 4),
            "status": "complete" if complete else "partial",
            "is_complete": complete,
        }
    )
    return result


def tag_period_coverage(data: pd.DataFrame, period: str, *, end: Any | None = None) -> dict[str, Any]:
    coverage = assess_period_coverage(data, period, end=end)
    data.attrs["requested_period"] = period
    data.attrs["period_coverage"] = coverage
    data.attrs["period_coverage_status"] = coverage["status"]
    return coverage
