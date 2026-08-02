"""Strategy K-line cache and fetch orchestration helpers."""
from __future__ import annotations

import io
import logging
import os
import re
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol

import pandas as pd

from config import CACHE_TTL_STRATEGY_KLINE, RUNTIME_CACHE_DIR
from data.file_lock import atomic_write_text, get_thread_lock, process_file_lock
from data.periods import assess_period_coverage, get_period_spec, slice_period
from data_fetcher import StockDataFetcher


STRATEGY_KLINE_CACHE_DIR = os.path.join(RUNTIME_CACHE_DIR, "strategy_kline_daily")
LOCAL_CACHE_SOURCE = "\u7b56\u7565K\u7ebf\u672c\u5730\u7f13\u5b58"
OFFLINE_CACHE_SOURCE = "\u79bb\u7ebf\u7f13\u5b58"
SINA_SOURCE = "\u65b0\u6d6a\u8d22\u7ecf"
MOOTDX_SOURCE = "\u901a\u8fbe\u4fe1mootdx"
THS_SOURCE = "\u540c\u82b1\u987a"
TENCENT_SOURCE = "\u817e\u8baf\u8d22\u7ecf"
EASTMONEY_SOURCE = "\u4e1c\u65b9\u8d22\u5bcc"
_ORIGINAL_GET_STOCK_DATA = StockDataFetcher.get_stock_data
logger = logging.getLogger(__name__)
STRICT_COVERAGE_PERIODS = {"1y", "2y", "5y"}
_MEMORY_CACHE: dict[str, pd.DataFrame] = {}
_MEMORY_CACHE_DEPTH = 0
_MEMORY_CACHE_LOCK = RLock()


class StrategyCacheOwner(Protocol):
    def _drop_weekend_bars(self, data: Any) -> Any:
        ...

    def _get_strategy_popular_cn_stocks(self) -> list[dict[str, Any]]:
        ...

    def _strategy_cache_trade_date(self) -> str:
        ...

    def _load_strategy_kline_cache(self, cache_key: str) -> Any:
        ...

    def _save_strategy_kline_cache(self, cache_key: str, data: Any) -> None:
        ...


def strategy_cache_trade_date() -> str:
    today = pd.Timestamp.now().normalize()
    if today.weekday() >= 5:
        today = today - pd.Timedelta(days=today.weekday() - 4)
    return today.strftime("%Y-%m-%d")


def strategy_kline_cache_path(cache_key: str) -> str:
    safe_key = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(cache_key))
    return os.path.join(STRATEGY_KLINE_CACHE_DIR, f"{safe_key}.json")


def strategy_kline_cache_is_fresh(cache_key: str) -> bool:
    path = Path(strategy_kline_cache_path(cache_key))
    try:
        stat = path.stat()
    except OSError:
        return False
    return bool(
        stat.st_size > 0
        and time.time() - stat.st_mtime <= max(0.0, float(CACHE_TTL_STRATEGY_KLINE))
    )


@contextmanager
def strategy_kline_memory_cache():
    """Reuse parsed daily K frames only for one explicit preheat job."""
    global _MEMORY_CACHE_DEPTH
    with _MEMORY_CACHE_LOCK:
        if _MEMORY_CACHE_DEPTH == 0:
            _MEMORY_CACHE.clear()
        _MEMORY_CACHE_DEPTH += 1
    try:
        yield
    finally:
        with _MEMORY_CACHE_LOCK:
            _MEMORY_CACHE_DEPTH = max(0, _MEMORY_CACHE_DEPTH - 1)
            if _MEMORY_CACHE_DEPTH == 0:
                _MEMORY_CACHE.clear()


def _remember_strategy_kline_cache(cache_key: str, data: pd.DataFrame | None) -> None:
    if data is None or getattr(data, "empty", True):
        return
    with _MEMORY_CACHE_LOCK:
        if _MEMORY_CACHE_DEPTH > 0:
            _MEMORY_CACHE[cache_key] = data.copy(deep=True)


def _load_strategy_kline_memory_cache(cache_key: str) -> pd.DataFrame | None:
    with _MEMORY_CACHE_LOCK:
        cached = _MEMORY_CACHE.get(cache_key) if _MEMORY_CACHE_DEPTH > 0 else None
        return cached.copy(deep=True) if cached is not None else None


def load_strategy_kline_cache(owner: StrategyCacheOwner, cache_key: str) -> pd.DataFrame | None:
    memory_cached = _load_strategy_kline_memory_cache(cache_key)
    if memory_cached is not None:
        memory_cached.attrs.setdefault("data_source", LOCAL_CACHE_SOURCE)
        return memory_cached
    path = Path(strategy_kline_cache_path(cache_key))
    if not os.path.exists(path):
        return None
    try:
        with get_thread_lock(path):
            modified_at = pd.Timestamp.fromtimestamp(os.path.getmtime(path))
            if pd.Timestamp.now() - modified_at > pd.Timedelta(seconds=CACHE_TTL_STRATEGY_KLINE):
                return None
            cached = path.read_text(encoding="utf-8")
        data = pd.read_json(io.StringIO(cached), orient="split")
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        if len(data) < 10:
            return None
        data = owner._drop_weekend_bars(data)
        data.attrs["data_source"] = LOCAL_CACHE_SOURCE
        _remember_strategy_kline_cache(cache_key, data)
        return data
    except Exception:
        logger.warning("读取策略K线缓存失败: key=%s path=%s", cache_key, path, exc_info=True)
        return None


def save_strategy_kline_cache(cache_key: str, data: Any) -> None:
    try:
        if data is None or getattr(data, "empty", True):
            return
        path = Path(strategy_kline_cache_path(cache_key))
        content = data.to_json(orient="split", date_format="iso")
        with get_thread_lock(path):
            with process_file_lock(path):
                atomic_write_text(path, content)
        _remember_strategy_kline_cache(cache_key, data)
    except Exception:
        logger.warning("写入策略K线缓存失败: key=%s", cache_key, exc_info=True)


def prune_strategy_kline_cache(
    cache_dir: str | os.PathLike[str] | None = None,
    *,
    max_age_seconds: float = CACHE_TTL_STRATEGY_KLINE,
    now: float | None = None,
) -> dict[str, int]:
    """Delete strategy K-line files that are already too old to be read."""
    root = Path(cache_dir or STRATEGY_KLINE_CACHE_DIR)
    if not root.exists():
        return {"removed": 0, "bytes_removed": 0, "errors": 0}
    cutoff = (time.time() if now is None else float(now)) - max(0.0, float(max_age_seconds))
    removed = 0
    bytes_removed = 0
    errors = 0
    for path in root.glob("*.json"):
        try:
            stat = path.stat()
            if stat.st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
            bytes_removed += stat.st_size
        except OSError:
            errors += 1
            logger.debug("清理过期策略K线缓存失败: %s", path, exc_info=True)
    return {"removed": removed, "bytes_removed": bytes_removed, "errors": errors}


def _cache_key(owner: StrategyCacheOwner, market: str, symbol: str, period: str, interval: str) -> str:
    return f"{market}:{symbol}:{period}:{interval}:{owner._strategy_cache_trade_date()}"


def _cn_sources(fetcher: StockDataFetcher) -> list[tuple[str, Callable[[str, str], Any]]]:
    return [
        (MOOTDX_SOURCE, fetcher._get_cn_stock_data_mootdx),
        (TENCENT_SOURCE, fetcher._get_cn_stock_data_akshare),
        (THS_SOURCE, fetcher._get_cn_stock_data_ths),
        (EASTMONEY_SOURCE, fetcher._get_cn_stock_data_akshare_em),
        (SINA_SOURCE, fetcher._get_cn_stock_data_sina_fallback),
    ]


def get_strategy_stock_data(
    owner: StrategyCacheOwner,
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    market: str = "CN",
    fetcher: StockDataFetcher | None = None,
) -> Any:
    fetcher = fetcher or StockDataFetcher()
    if market != "CN":
        return fetcher.get_stock_data(symbol, period=period, interval=interval, market=market)
    if type(fetcher) is StockDataFetcher and StockDataFetcher.get_stock_data is not _ORIGINAL_GET_STOCK_DATA:
        return fetcher.get_stock_data(symbol, period=period, interval=interval, market=market)

    cache_key = _cache_key(owner, market, symbol, period, interval)
    cached_data = owner._load_strategy_kline_cache(cache_key)
    if cached_data is not None and _has_requested_period_coverage(cached_data, period):
        cached_data.attrs.setdefault("data_source", LOCAL_CACHE_SOURCE)
        return cached_data

    for source_label, source_func in _cn_sources(fetcher):
        try:
            data = source_func(symbol, period)
            if (
                data is not None
                and len(data) >= 10
                and _has_requested_period_coverage(data, period)
            ):
                data = owner._drop_weekend_bars(data)
                data.attrs["data_source"] = source_label
                owner._save_strategy_kline_cache(cache_key, data)
                return data
        except Exception:
            logger.debug("策略K线数据源失败: symbol=%s source=%s", symbol, source_label, exc_info=True)
            continue

    try:
        data = fetcher._load_offline_cache(symbol)
        if (
            data is not None
            and len(data) >= 10
            and _has_requested_period_coverage(data, period)
        ):
            data = owner._drop_weekend_bars(data)
            data.attrs["data_source"] = data.attrs.get("data_source") or OFFLINE_CACHE_SOURCE
            owner._save_strategy_kline_cache(cache_key, data)
            return data
    except Exception:
        logger.debug("策略K线离线缓存失败: symbol=%s", symbol, exc_info=True)
    return None


def refresh_strategy_kline_cache(
    owner: StrategyCacheOwner,
    stocks: list[dict[str, Any]] | None = None,
    period: str = "3mo",
    interval: str = "1d",
    market: str = "CN",
    max_workers: int = 8,
) -> dict[str, int]:
    stocks = list(stocks or owner._get_strategy_popular_cn_stocks())
    cleanup = prune_strategy_kline_cache()
    if cleanup["removed"] or cleanup["errors"]:
        logger.info(
            "策略K线缓存清理完成: removed=%s bytes=%s errors=%s",
            cleanup["removed"],
            cleanup["bytes_removed"],
            cleanup["errors"],
        )
    fetcher = StockDataFetcher()
    refreshed = 0
    failed = 0

    def refresh_one(stock: dict[str, Any]) -> bool:
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return False
        cache_key = _cache_key(owner, market, symbol, period, interval)
        for _, source_func in _cn_sources(fetcher):
            try:
                data = source_func(symbol, period)
                if (
                    data is not None
                    and len(data) >= 10
                    and _has_requested_period_coverage(data, period)
                ):
                    data = owner._drop_weekend_bars(data)
                    owner._save_strategy_kline_cache(cache_key, data)
                    return True
            except Exception:
                continue
        return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(refresh_one, stock): stock for stock in stocks}
        for future in as_completed(futures):
            try:
                if future.result():
                    refreshed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    return {"total": len(stocks), "refreshed": refreshed, "failed": failed}


def preheat_strategy_kline_cache(
    owner: StrategyCacheOwner,
    stocks: list[dict[str, Any]] | None = None,
    periods: tuple[str, ...] = ("1y", "6mo", "3mo"),
    interval: str = "1d",
    market: str = "CN",
    max_workers: int = 32,
) -> dict[str, Any]:
    """Warm all strategy periods with one longest-period fetch per symbol."""
    stocks = list(stocks or owner._get_strategy_popular_cn_stocks())
    unique_periods = list(dict.fromkeys(str(period) for period in periods if str(period)))
    unique_periods.sort(key=lambda period: get_period_spec(period).calendar_days, reverse=True)
    if not unique_periods:
        return {
            "total": len(stocks),
            "refreshed": 0,
            "cached": 0,
            "failed": len(stocks),
            "periods": [],
        }

    cleanup = prune_strategy_kline_cache()
    if cleanup["removed"] or cleanup["errors"]:
        logger.info(
            "策略K线缓存清理完成: removed=%s bytes=%s errors=%s",
            cleanup["removed"],
            cleanup["bytes_removed"],
            cleanup["errors"],
        )

    primary_period = unique_periods[0]
    fetcher = StockDataFetcher()
    refreshed = 0
    cached = 0
    failed = 0

    def preheat_one(stock: dict[str, Any]) -> str:
        symbol = str((stock or {}).get("code") or "").strip()
        if not symbol:
            return "failed"

        missing_periods: list[str] = []
        for requested_period in unique_periods:
            cache_key = _cache_key(owner, market, symbol, requested_period, interval)
            if not strategy_kline_cache_is_fresh(cache_key):
                missing_periods.append(requested_period)
        primary_key = _cache_key(owner, market, symbol, primary_period, interval)
        primary_data = (
            owner._load_strategy_kline_cache(primary_key)
            if strategy_kline_cache_is_fresh(primary_key)
            else None
        )
        primary_from_cache = bool(
            primary_data is not None
            and len(primary_data) >= 10
            and _has_requested_period_coverage(primary_data, primary_period)
        )
        if not primary_from_cache:
            primary_data = None
            for _, source_func in _cn_sources(fetcher):
                try:
                    primary_data = source_func(symbol, primary_period)
                    if (
                        primary_data is not None
                        and len(primary_data) >= 10
                        and _has_requested_period_coverage(primary_data, primary_period)
                    ):
                        primary_data = owner._drop_weekend_bars(primary_data)
                        break
                except Exception:
                    primary_data = None
                    continue
        if (
            primary_data is None
            or len(primary_data) < 10
            or not _has_requested_period_coverage(primary_data, primary_period)
        ):
            return "failed"

        for requested_period in unique_periods:
            period_data = (
                primary_data
                if requested_period == primary_period
                else slice_period(primary_data, requested_period)
            )
            if period_data is None or len(period_data) < 10:
                return "failed"
            cache_key = _cache_key(owner, market, symbol, requested_period, interval)
            _remember_strategy_kline_cache(cache_key, period_data)
            if requested_period in missing_periods or not primary_from_cache:
                owner._save_strategy_kline_cache(cache_key, period_data)
        return "cached" if not missing_periods and primary_from_cache else "refreshed"

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers or 1))) as executor:
        futures = [executor.submit(preheat_one, stock) for stock in stocks]
        for future in as_completed(futures):
            try:
                outcome = future.result()
            except Exception:
                outcome = "failed"
            if outcome == "refreshed":
                refreshed += 1
            elif outcome == "cached":
                cached += 1
            else:
                failed += 1

    return {
        "total": len(stocks),
        "refreshed": refreshed,
        "cached": cached,
        "failed": failed,
        "periods": unique_periods,
    }


def _has_requested_period_coverage(data: Any, period: str) -> bool:
    """Reject long-period labels when the real frame only covers a short span."""
    if period not in STRICT_COVERAGE_PERIODS:
        return True
    if data is None or getattr(data, "empty", True):
        return False
    try:
        index = data.index
        if not isinstance(index, pd.DatetimeIndex):
            index = pd.to_datetime(index, errors="coerce")
        index = pd.DatetimeIndex(index).dropna()
        if index.empty:
            return False
        frame = data.copy()
        frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[frame.index.notna()]
        coverage = assess_period_coverage(frame, period, end=index.max())
        return bool(coverage["is_complete"])
    except Exception:
        return False
