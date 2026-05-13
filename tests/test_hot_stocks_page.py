"""热门板块页面工具测试。"""

from ui.hot_stocks_page import _run_hot_tasks


def test_run_hot_tasks_collects_results():
    result = _run_hot_tasks({
        "sectors": lambda: [{"板块": "电力"}],
        "concepts": lambda: [{"板块": "特高压"}],
    })

    assert result["sectors"][0]["板块"] == "电力"
    assert result["concepts"][0]["板块"] == "特高压"


def test_run_hot_tasks_isolates_failures():
    def fail():
        raise RuntimeError("blocked")

    result = _run_hot_tasks({
        "gainers": lambda: [{"代码": "000001"}],
        "losers": fail,
    })

    assert result["gainers"][0]["代码"] == "000001"
    assert result["losers"] == []


def test_hot_page_does_not_auto_fetch_on_first_render(monkeypatch):
    import streamlit as st
    import ui.hot_stocks_page as page

    class DummyContainer:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []

    monkeypatch.setattr(page, "get_cached_hot_stocks", lambda market: calls.append(market) or {})
    monkeypatch.setattr(st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(st, "selectbox", lambda *args, **kwargs: "CN")
    monkeypatch.setattr(st, "columns", lambda *args, **kwargs: [DummyContainer(), DummyContainer()])

    st.session_state.clear()
    page.hot_stocks_page()

    assert calls == []
