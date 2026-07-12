import os
import time

from data.file_lock import prune_orphan_temp_files


def test_prune_orphan_temp_files_removes_only_stale_cache_temps(tmp_path):
    target = tmp_path / "stock_research.json"
    stale_legacy = tmp_path / "stock_research.json.123.tmp"
    stale_current = tmp_path / ".stock_research.json.random.tmp"
    recent = tmp_path / "stock_research.json.456.tmp"
    unrelated = tmp_path / "other.json.123.tmp"
    for path in (stale_legacy, stale_current, recent, unrelated):
        path.write_text("temp", encoding="utf-8")
    old = time.time() - 7200
    os.utime(stale_legacy, (old, old))
    os.utime(stale_current, (old, old))

    result = prune_orphan_temp_files(target, max_age_seconds=3600)

    assert result == {"removed": 2, "bytes_removed": 8, "errors": 0}
    assert not stale_legacy.exists()
    assert not stale_current.exists()
    assert recent.exists()
    assert unrelated.exists()
