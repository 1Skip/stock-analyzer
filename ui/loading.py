"""Unified Streamlit loading indicators."""

from __future__ import annotations

import html
from contextlib import contextmanager
from typing import Iterator

import streamlit as st


def render_status_loading(container, message: str, percent: int | None = None) -> None:
    """Render a compact non-spinner loading strip."""
    safe_message = html.escape(str(message or "正在处理..."))
    percent_html = ""
    bar_html = ""
    if percent is not None:
        safe_percent = max(0, min(100, int(percent)))
        percent_html = f'<span class="status-loading-percent">{safe_percent}%</span>'
        bar_html = (
            '<div class="status-loading-bar">'
            f'<div style="width:{safe_percent}%"></div>'
            '</div>'
        )

    with container.container():
        st.markdown(
            f"""
            <div class="status-loading-strip">
              <div class="status-loading-main">
                <span class="status-loading-dot"></span>
                <div class="status-loading-copy">{safe_message}</div>
                {percent_html}
              </div>
              {bar_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


@contextmanager
def status_loading(message: str, percent: int | None = None) -> Iterator:
    """Context manager replacement for st.spinner."""
    placeholder = st.empty()
    render_status_loading(placeholder, message, percent)
    try:
        yield placeholder
    finally:
        placeholder.empty()
