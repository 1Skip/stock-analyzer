"""Small escaped HTML helpers for Streamlit markdown blocks."""
from __future__ import annotations

import html
from typing import Any


def escape_text(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def badge(label: Any, tone: str = "neutral") -> str:
    safe_tone = "".join(ch for ch in str(tone or "neutral") if ch.isalnum() or ch in ("-", "_"))
    return f'<span class="ui-badge ui-badge-{safe_tone}">{escape_text(label)}</span>'


def metric_card(title: Any, value: Any, note: Any = "") -> str:
    note_html = f'<div class="ui-metric-note">{escape_text(note)}</div>' if note not in (None, "") else ""
    return (
        '<div class="ui-metric-card">'
        f'<div class="ui-metric-title">{escape_text(title)}</div>'
        f'<div class="ui-metric-value">{escape_text(value)}</div>'
        f"{note_html}"
        "</div>"
    )
