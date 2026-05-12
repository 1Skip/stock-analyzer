"""报告导出工具。"""
from __future__ import annotations

from pathlib import Path


def ensure_report_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_markdown_report(content: str, report_date: str, output_dir: str | Path = "reports/history") -> dict[str, str]:
    """保存日期报告和 latest.md。"""
    path = ensure_report_dir(output_dir)
    dated_path = path / f"{report_date}.md"
    latest_path = path / "latest.md"
    dated_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return {
        "dated": str(dated_path),
        "latest": str(latest_path),
    }

