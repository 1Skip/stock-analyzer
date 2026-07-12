"""Cross-thread and cross-process helpers for atomic cache writes."""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


logger = logging.getLogger(__name__)
_FILE_LOCKS: weakref.WeakValueDictionary[Path, threading.Lock] = weakref.WeakValueDictionary()
_FILE_LOCKS_GUARD = threading.Lock()
_TEMP_PRUNE_TIMES: dict[Path, float] = {}
_TEMP_PRUNE_GUARD = threading.Lock()
_TEMP_PRUNE_INTERVAL_SECONDS = 3600.0
_ORPHAN_TEMP_MAX_AGE_SECONDS = 3600.0


def get_thread_lock(path: str | os.PathLike[str]) -> threading.Lock:
    resolved = Path(path).resolve()
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _FILE_LOCKS[resolved] = lock
        return lock


@contextmanager
def process_file_lock(
    path: str | os.PathLike[str],
    *,
    timeout_seconds: float = 30,
    stale_seconds: float = 60,
) -> Iterator[None]:
    """Serialize read-modify-write operations across local processes."""
    target = Path(path)
    lock_path = target.with_suffix(f"{target.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            payload = f"{os.getpid()}\n{time.time()}\n"
            os.write(fd, payload.encode("utf-8"))
        except FileExistsError:
            if _is_stale_process_lock(lock_path, stale_seconds):
                try:
                    lock_path.unlink(missing_ok=True)
                    continue
                except Exception:
                    logger.debug("清理过期文件锁失败: %s", lock_path, exc_info=True)
            if time.monotonic() > deadline:
                raise TimeoutError(f"cache lock timeout: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                logger.debug("释放文件锁失败: %s", lock_path, exc_info=True)


def atomic_write_text(path: str | os.PathLike[str], content: str, *, encoding: str = "utf-8") -> None:
    """Write text to a unique sibling file and atomically replace the target."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _prune_orphan_temp_files_once(target)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            tmp_path = Path(file.name)
        os.replace(tmp_path, target)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def prune_orphan_temp_files(
    path: str | os.PathLike[str],
    *,
    max_age_seconds: float = _ORPHAN_TEMP_MAX_AGE_SECONDS,
) -> dict[str, int]:
    """Remove stale atomic-write temp files for one target or cache directory."""
    candidate = Path(path)
    if candidate.is_dir():
        directory = candidate
        patterns = ("*.json.*.tmp", ".*.json.*.tmp")
    else:
        directory = candidate.parent
        patterns = (f"{candidate.name}.*.tmp", f".{candidate.name}.*.tmp")
    if not directory.exists():
        return {"removed": 0, "bytes_removed": 0, "errors": 0}

    cutoff = time.time() - max(0.0, float(max_age_seconds))
    removed = 0
    bytes_removed = 0
    errors = 0
    seen: set[Path] = set()
    for pattern in patterns:
        for temp_path in directory.glob(pattern):
            if temp_path in seen or not temp_path.is_file():
                continue
            seen.add(temp_path)
            try:
                stat = temp_path.stat()
                if stat.st_mtime >= cutoff:
                    continue
                temp_path.unlink()
                removed += 1
                bytes_removed += stat.st_size
            except OSError:
                errors += 1
                logger.debug("清理孤儿缓存临时文件失败: %s", temp_path, exc_info=True)
    return {"removed": removed, "bytes_removed": bytes_removed, "errors": errors}


def _prune_orphan_temp_files_once(target: Path) -> None:
    directory = target.parent.resolve()
    now = time.monotonic()
    with _TEMP_PRUNE_GUARD:
        last_run = _TEMP_PRUNE_TIMES.get(directory, 0.0)
        if now - last_run < _TEMP_PRUNE_INTERVAL_SECONDS:
            return
        _TEMP_PRUNE_TIMES[directory] = now
    result = prune_orphan_temp_files(directory)
    if result["removed"] or result["errors"]:
        logger.info(
            "缓存临时文件清理完成: target=%s removed=%s bytes=%s errors=%s",
            target,
            result["removed"],
            result["bytes_removed"],
            result["errors"],
        )


def _is_stale_process_lock(lock_path: Path, max_age_seconds: float) -> bool:
    try:
        stat = lock_path.stat()
    except OSError:
        return True
    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines()
        pid = int(lines[0].strip()) if lines else None
    except Exception:
        logger.debug("读取文件锁进程信息失败: %s", lock_path, exc_info=True)
        pid = None
    if pid and _process_exists(pid):
        return False
    return time.time() - stat.st_mtime > max_age_seconds or pid is not None


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
