"""数据服务运行期治理工具。"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")
logger = logging.getLogger(__name__)
_TIMEOUT_WORKERS = max(1, int(os.getenv("DATA_TIMEOUT_WORKERS", "16")))
_TIMEOUT_CAPACITY = max(_TIMEOUT_WORKERS, int(os.getenv("DATA_TIMEOUT_CAPACITY", "32")))
_TIMEOUT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=_TIMEOUT_WORKERS,
    thread_name_prefix="stock-data-timeout",
)
_TIMEOUT_SLOTS = threading.BoundedSemaphore(_TIMEOUT_CAPACITY)


def _run_and_release(func: Callable[[], T]) -> T:
    try:
        return func()
    finally:
        _TIMEOUT_SLOTS.release()


def run_with_timeout(func: Callable[[], T], timeout_seconds: float) -> T:
    """在线程中执行无超时参数的第三方接口，超时后不阻塞主流程。"""
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than 0")

    deadline = time.monotonic() + timeout
    if not _TIMEOUT_SLOTS.acquire(timeout=timeout):
        raise TimeoutError(f"timeout worker capacity exhausted after {timeout:.2f}s")

    try:
        future = _TIMEOUT_EXECUTOR.submit(_run_and_release, func)
    except Exception:
        _TIMEOUT_SLOTS.release()
        raise

    remaining = max(0.001, deadline - time.monotonic())
    try:
        return future.result(timeout=remaining)
    except concurrent.futures.TimeoutError as exc:
        if future.cancel():
            _TIMEOUT_SLOTS.release()
        raise TimeoutError(f"data source timed out after {timeout:.2f}s") from exc


def safe_call(func: Callable[[], T], default: T, *, label: str, logger_: logging.Logger | None = None) -> T:
    """统一捕获非关键数据源异常，返回默认值。"""
    try:
        return func()
    except Exception as exc:
        (logger_ or logger).info("%s 失败: %s", label, exc)
        return default
