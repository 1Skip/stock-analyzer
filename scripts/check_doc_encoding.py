"""Check project text documents are readable as UTF-8.

This is intentionally report-only. It does not rewrite files.
"""
from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_ROOTS = [
    Path("README.md"),
    Path("agent.md"),
    Path("docs"),
    Path(".codex"),
    Path(".github"),
    Path("pytest.ini"),
]
TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".ini"}
MOJIBAKE_MARKERS = ("鏂", "绾", "鐨", "涓", "鈥", "�")


def iter_text_files(paths: list[Path]):
    for path in paths:
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path
        elif path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES:
                    yield item


def check_paths(paths: list[Path]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for path in iter_text_files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            issues.append({"path": str(path), "reason": str(exc)})
        except OSError as exc:
            issues.append({"path": str(path), "reason": str(exc)})
            continue
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            issues.append({"path": str(path), "reason": "contains common mojibake markers"})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Markdown UTF-8 readability.")
    parser.add_argument("paths", nargs="*", help="Files or directories to check.")
    args = parser.parse_args()
    paths = [Path(item) for item in args.paths] if args.paths else DEFAULT_ROOTS
    issues = check_paths(paths)
    if not issues:
        print("文档编码检查通过：项目文本文件均可按 UTF-8 读取，未发现常见乱码标记")
        return 0
    print("文档编码检查发现问题：")
    for item in issues:
        print(f"- {item['path']}: {item['reason']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
