"""History report workspace page."""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from ui.loading import status_loading


def _history_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "reports" / "history"


def _list_reports() -> list[Path]:
    report_dir = _history_dir()
    if not report_dir.exists():
        return []
    reports = [path for path in report_dir.glob("*.md") if path.name != "latest.md"]
    return sorted(reports, key=lambda path: path.stat().st_mtime, reverse=True)


def _generate_today_report_task():
    from reports.daily_report_service import DailyReportService

    return DailyReportService().save_markdown(include_recommendations=False)


def report_history_page() -> None:
    st.markdown('<h1 class="main-header">历史日报</h1>', unsafe_allow_html=True)
    st.caption("查看每日 Markdown 决策仪表盘，支持预览和下载。")

    reports = _list_reports()
    col_generate, col_refresh, _ = st.columns([1.1, 1, 4])
    with col_generate:
        if st.button("生成今日日报", type="primary", use_container_width=True):
            with status_loading("\u6b63\u5728\u751f\u6210\u65e5\u62a5...", 20):
                paths = _generate_today_report_task()
            st.success(f"已生成：{paths.get('dated')}")
            st.rerun()
    with col_refresh:
        if st.button("刷新列表", use_container_width=True):
            st.rerun()

    reports = _list_reports()
    if not reports:
        st.info("还没有日报。可以点击「生成今日日报」，或运行 `python main.py --daily-report`。")
        return

    labels = [path.name for path in reports]
    selected_label = st.selectbox("选择报告", labels, index=0)
    selected = reports[labels.index(selected_label)]
    content = selected.read_text(encoding="utf-8")

    st.download_button(
        "下载 Markdown",
        data=content,
        file_name=selected.name,
        mime="text/markdown",
        use_container_width=True,
    )

    tab_preview, tab_source = st.tabs(["预览", "Markdown 源码"])
    with tab_preview:
        st.markdown(content)
    with tab_source:
        st.code(content, language="markdown")
