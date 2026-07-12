"""Strategy K-line cache and fetch orchestration helpers."""
from __future__ import annotations

import io
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from config import CACHE_TTL_STRATEGY_KLINE, RUNTIME_CACHE_DIR
from data.file_lock import atomic_write_text, get_thread_lock, process_file_lock
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


def load_strategy_kline_cache(owner: StrategyCacheOwner, cache_key: str) -> pd.DataFrame | None:
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
    if cached_data is not None:
        cached_data.attrs.setdefault("data_source", LOCAL_CACHE_SOURCE)
        return cached_data

    for source_label, source_func in _cn_sources(fetcher):
        try:
            data = source_func(symbol, period)
            if data is not None and len(data) >= 10:
                data = owner._drop_weekend_bars(data)
                data.attrs["data_source"] = source_label
                owner._save_strategy_kline_cache(cache_key, data)
                return data
        except Exception:
            logger.debug("策略K线数据源失败: symbol=%s source=%s", symbol, source_label, exc_info=True)
            continue

    try:
        data = fetcher._load_offline_cache(symbol)
        if data is not None and len(data) >= 10:
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
                if data is not None and len(data) >= 10:
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
