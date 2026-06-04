"""Report Streamlit unsafe_allow_html usage hotspots.

This is a report-only helper by default. Use --max-count to enforce a ceiling.
"""
from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_PATHS = [Path("ui"), Path("app.py")]


def scan_unsafe_html(paths: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                if "unsafe_allow_html=True" in line:
                    rows.append({
                        "path": str(path),
                        "line": number,
                        "dynamic": "f\"" in line or "f'" in line or "format(" in line,
                        "text": line.strip()[:160],
                    })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report unsafe_allow_html usage.")
    parser.add_argument("paths", nargs="*", help="Files or directories to scan.")
    parser.add_argument("--max-count", type=int, default=None, help="Fail if usage count exceeds this value.")
    args = parser.parse_args(argv)
    paths = [Path(item) for item in args.paths] if args.paths else DEFAULT_PATHS
    rows = scan_unsafe_html(paths)
    print(f"unsafe_allow_html usages: {len(rows)}")
    for row in rows:
        marker = "dynamic" if row["dynamic"] else "static"
        print(f"- {row['path']}:{row['line']} [{marker}] {row['text']}")
    if args.max_count is not None and len(rows) > args.max_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
