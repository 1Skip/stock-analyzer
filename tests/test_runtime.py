import threading
import time

import pytest

from data.runtime import run_with_timeout


def test_run_with_timeout_returns_without_waiting_for_slow_worker():
    release = threading.Event()

    def slow_call():
        release.wait(timeout=2)

    started = time.perf_counter()
    try:
        with pytest.raises(TimeoutError, match="timed out"):
            run_with_timeout(slow_call, 0.05)
        elapsed = time.perf_counter() - started
        assert elapsed < 0.3
    finally:
        release.set()


def test_run_with_timeout_returns_result_before_deadline():
    assert run_with_timeout(lambda: "ok", 0.5) == "ok"


def test_run_with_timeout_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="greater than 0"):
        run_with_timeout(lambda: None, 0)
