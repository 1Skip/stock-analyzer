"""Inspect local cache files without modifying them."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


DEFAULT_CACHE_DIRS = [Path(".cache"), Path("reports/history")]


def inspect_cache_dirs(paths: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for directory in paths:
        if not directory.exists():
            rows.append({"path": str(directory), "status": "missing"})
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                stat = path.stat()
                rows.append({
                    "path": str(path),
                    "status": "ok",
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                })
            except OSError as exc:
                rows.append({"path": str(path), "status": "error", "reason": str(exc)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local cache status.")
    parser.add_argument("paths", nargs="*", help="Cache directories to inspect.")
    args = parser.parse_args()
    paths = [Path(item) for item in args.paths] if args.paths else DEFAULT_CACHE_DIRS
    print(json.dumps(inspect_cache_dirs(paths), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
