"""Loading indicator regression tests."""

from pathlib import Path

from ui.styles import CUSTOM_CSS


def test_business_ui_does_not_use_native_streamlit_spinner():
    roots = [Path("ui"), Path("backtest_ui.py")]
    offenders = []

    for root in roots:
        files = root.rglob("*.py") if root.is_dir() else [root]
        for path in files:
            text = path.read_text(encoding="utf-8")
            if "st.spinner(" in text:
                offenders.append(str(path))

    assert offenders == []


def test_custom_css_hides_native_spinner_fallback():
    assert '[data-testid="stSpinner"]' in CUSTOM_CSS
    assert "status-loading-strip" in CUSTOM_CSS
