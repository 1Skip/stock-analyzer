"""Shared indicator display context for analysis and recommendation pages."""

from __future__ import annotations

from typing import Any

import pandas as pd

from technical_indicators import TechnicalIndicators


DISPLAY_INDICATOR_PERIOD = "1y"


def is_valid_realtime_quote(quote: dict[str, Any] | None) -> bool:
    if not isinstance(quote, dict):
        return False
    price = _safe_float(quote.get("price"))
    high = _safe_float(quote.get("high"))
    low = _safe_float(quote.get("low"))
    open_price = _safe_float(quote.get("open"))
    if price is None or price <= 0:
        return False
    if high is not None and high <= 0:
        return False
    if low is not None and low <= 0:
        return False
    if open_price is not None and open_price <= 0:
        return False
    return True


def quote_from_last_row(data: pd.DataFrame | None) -> dict[str, Any] | None:
    if data is None or data.empty:
        return None
    row = data.iloc[-1]
    price = _safe_float(row.get("close"))
    if price is None:
        return None
    open_price = _safe_float(row.get("open")) or price
    high = _safe_float(row.get("high")) or price
    low = _safe_float(row.get("low")) or price
    prev_close = _safe_float(data.iloc[-2].get("close")) if len(data) > 1 else price
    change = ((price / prev_close - 1) * 100) if prev_close else 0.0
    return {
        "price": price,
        "open": open_price,
        "high": high,
        "low": low,
        "volume": _safe_float(row.get("volume")) or 0,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change,
        "source": "历史K线兜底",
    }


def prepare_indicator_frame(
    data: pd.DataFrame | None,
    quote: dict[str, Any] | None = None,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    """Return indicator-ready daily data using the shared Tonghuashun-style display口径."""
    frame = _normalize_daily_frame(data)
    if frame is None or frame.empty:
        return None
    return TechnicalIndicators.calculate_all(frame)


def merge_realtime_quote(
    data: pd.DataFrame | None,
    quote: dict[str, Any] | None,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    """Merge a real intraday quote into the last daily bar for display indicators only."""
    frame = _normalize_daily_frame(data)
    if frame is None or frame.empty or not is_valid_realtime_quote(quote):
        return frame
    if str((quote or {}).get("source") or "") == "历史K线兜底":
        return frame

    current = now or pd.Timestamp.now()
    today = current.normalize()
    if today.dayofweek >= 5:
        return frame

    price = _safe_float(quote.get("price"))
    open_price = _safe_float(quote.get("open")) or price
    high = _safe_float(quote.get("high")) or price
    low = _safe_float(quote.get("low")) or price
    volume = _safe_float(quote.get("volume"))
    if price is None:
        return frame

    last_date = frame.index[-1].normalize()
    if last_date == today:
        idx = frame.index[-1]
        frame.loc[idx, "close"] = price
        frame.loc[idx, "high"] = max(_safe_float(frame.loc[idx, "high"]) or price, high or price)
        frame.loc[idx, "low"] = min(_safe_float(frame.loc[idx, "low"]) or price, low or price)
        frame.loc[idx, "open"] = _safe_float(frame.loc[idx, "open"]) or open_price
        if volume is not None:
            frame.loc[idx, "volume"] = volume
        return frame

    if volume is None or volume <= 0:
        return frame
    realtime_row = pd.DataFrame(
        {
            "open": [open_price],
            "high": [high],
            "low": [low],
            "close": [price],
            "volume": [volume],
        },
        index=[today],
    )
    return pd.concat([frame, realtime_row])


def build_indicator_snapshot(data: pd.DataFrame | None) -> dict[str, float]:
    if data is None or data.empty:
        return {}
    latest = data.iloc[-1]
    keys = {
        "macd": 3,
        "macd_signal": 3,
        "macd_hist": 3,
        "rsi": 2,
        "rsi_6": 2,
        "rsi_12": 2,
        "rsi_24": 2,
        "kdj_k": 2,
        "kdj_d": 2,
        "kdj_j": 2,
        "boll_upper": 2,
        "boll_mid": 2,
        "boll_lower": 2,
        "ma5": 2,
        "ma10": 2,
        "ma20": 2,
        "ma30": 2,
        "ma60": 2,
        "main_accumulation": 2,
        "accumulation_risk": 2,
        "accumulation_trend": 2,
    }
    snapshot: dict[str, float] = {}
    for key, precision in keys.items():
        value = _safe_float(latest.get(key))
        if value is not None:
            snapshot[key] = round(value, precision)
    return snapshot


def _normalize_daily_frame(data: pd.DataFrame | None) -> pd.DataFrame | None:
    if data is None or data.empty:
        return None
    frame = data.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).set_index("date")
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[frame.index.notna()]
    if frame.empty or "close" not in frame.columns:
        return None
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for column in ("open", "high", "low"):
        if column not in frame.columns:
            frame[column] = frame["close"]
    if "volume" not in frame.columns:
        frame["volume"] = 0
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame.attrs.update(getattr(data, "attrs", {}))
    return frame


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except (TypeError, ValueError):
        return None
