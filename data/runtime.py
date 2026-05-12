"""数据服务运行期治理工具。"""
from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_with_timeout(func: Callable[[], T], timeout_seconds: float) -> T:
    """在线程中执行无超时参数的第三方接口，超时后不阻塞主流程。"""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func)
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def safe_call(func: Callable[[], T], default: T, *, label: str, logger_: logging.Logger | None = None) -> T:
    """统一捕获非关键数据源异常，返回默认值。"""
    try:
        return func()
    except Exception as exc:
        (logger_ or logger).info("%s 失败: %s", label, exc)
        return default

