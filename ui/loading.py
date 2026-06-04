"""Unified Streamlit loading indicators."""

from __future__ import annotations

import html
from contextlib import contextmanager
from typing import Iterator

import streamlit as st


def render_status_loading(container, message: str, percent: int | None = None) -> None:
    """Render a compact non-spinner loading strip."""
    text = str(message or "正在处理...")
    if percent is not None:
        safe_percent = max(0, min(100, int(percent or 0)))
        text = f"{text}｜{safe_percent}%"

    with container.container():
        st.info(text)


class ProgressReporter:
    """Small helper for rendering deterministic progress updates."""

    def __init__(self, container, title: str = "正在处理", *, context: str | None = None):
        self.container = container
        self.title = title
        self.context = context
        self.last_percent = 0

    def update(self, stage: str, percent: int | None = None, metrics: dict | None = None) -> None:
        if percent is None:
            percent = self.last_percent
        percent = max(self.last_percent, max(0, min(100, int(percent or 0))))
        self.last_percent = percent
        message = self._format_message(stage, metrics or {})
        render_status_loading(self.container, message, percent)

    def step(self, stage: str, done: int, total: int, *, base: int = 0, span: int = 100) -> None:
        total = max(1, int(total or 1))
        done = max(0, min(total, int(done or 0)))
        percent = base + int(span * done / total)
        self.update(stage, percent, {"已完成": done, "总数": total})

    def complete(self, stage: str = "完成") -> None:
        self.update(stage, 100)

    def empty(self) -> None:
        self.container.empty()

    def _format_message(self, stage: str, metrics: dict) -> str:
        parts = [str(self.title or "正在处理")]
        if self.context:
            parts.append(str(self.context))
        if stage:
            parts.append(f"阶段：{stage}")
        for key, value in metrics.items():
            parts.append(f"{key} {value}")
        return " · ".join(parts)


def make_progress_reporter(container, title: str, *, context: str | None = None) -> ProgressReporter:
    return ProgressReporter(container, title, context=context)


@contextmanager
def status_loading(message: str, percent: int | None = None) -> Iterator:
    """Context manager replacement for st.spinner."""
    placeholder = st.empty()
    render_status_loading(placeholder, message, percent)
    try:
        yield placeholder
    finally:
        placeholder.empty()
