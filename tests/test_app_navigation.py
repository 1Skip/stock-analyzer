"""Navigation isolation tests for the Streamlit app shell."""

from ui.styles import CUSTOM_CSS


def test_all_sidebar_pages_route_to_renderer():
    from app import _render_selected_page

    pages = [
        "个股分析",
        "热门板块",
        "智能推荐",
        "股票对比",
        "回测验证",
        "历史日报",
        "配置推送",
    ]

    for page in pages:
        assert page in _render_selected_page.__code__.co_consts


def test_app_shell_uses_main_page_container():
    import inspect
    import app

    source = inspect.getsource(app.main)

    assert "main_page" in source
    assert "_sync_active_page(page)" in source
    assert "_render_main_page(page)" in source
    assert "options=nav_items" in source
    assert "key=\"main_page\"" in source


def test_main_page_renders_before_slow_sidebar_widgets():
    import inspect
    import app

    source = inspect.getsource(app.main)

    render_index = source.index("_render_main_page(page)")
    market_index = source.index("display_market_temperature()")
    watchlist_index = source.index("display_watchlist_sidebar()")

    assert render_index < market_index
    assert render_index < watchlist_index


def test_custom_css_does_not_keep_stale_pages_visible():
    assert ".stale-element" not in CUSTOM_CSS
    assert "[data-stale=\"true\"]" not in CUSTOM_CSS


def test_page_switch_clears_inactive_state_and_reruns(monkeypatch):
    import app
    import streamlit as st

    st.session_state.clear()
    st.session_state["_active_page"] = "配置推送"
    st.session_state["hot_data"] = {"old": True}
    st.session_state["hot_data_loaded"] = True
    st.session_state["rec_results"] = {"old": True}
    st.session_state["analyzed_data"] = object()
    reruns = []

    monkeypatch.setattr(st, "rerun", lambda: reruns.append(True))

    changed = app._sync_active_page("股票对比")

    assert changed is True
    assert st.session_state["_active_page"] == "股票对比"
    assert "hot_data" not in st.session_state
    assert "hot_data_loaded" not in st.session_state
    assert "rec_results" not in st.session_state
    assert "analyzed_data" not in st.session_state
    assert reruns == [True]


def test_page_switch_keeps_current_page_state(monkeypatch):
    import app
    import streamlit as st

    st.session_state.clear()
    st.session_state["_active_page"] = "股票对比"
    st.session_state["hot_data"] = {"current": True}
    reruns = []

    monkeypatch.setattr(st, "rerun", lambda: reruns.append(True))

    changed = app._sync_active_page("热门板块")

    assert changed is True
    assert st.session_state["_active_page"] == "热门板块"
    assert st.session_state["hot_data"] == {"current": True}
    assert reruns == [True]


def test_same_page_does_not_rerun(monkeypatch):
    import app
    import streamlit as st

    st.session_state.clear()
    st.session_state["_active_page"] = "股票对比"
    reruns = []

    monkeypatch.setattr(st, "rerun", lambda: reruns.append(True))

    changed = app._sync_active_page("股票对比")

    assert changed is False
    assert reruns == []


def test_main_returns_immediately_after_page_change(monkeypatch):
    import app
    import streamlit as st

    class DummySidebar:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    st.session_state.clear()
    st.session_state["main_page"] = "股票对比"
    calls = []

    monkeypatch.setattr(st, "sidebar", DummySidebar())
    monkeypatch.setattr(st, "title", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "radio", lambda *args, **kwargs: "股票对比", raising=False)
    monkeypatch.setattr(st, "rerun", lambda: calls.append("rerun"))
    monkeypatch.setattr(app, "_render_selected_page", lambda page: calls.append(f"render:{page}"))

    app.main()

    assert calls == ["rerun"]


def test_main_page_uses_stable_empty_container(monkeypatch):
    import app
    import streamlit as st

    calls = []

    class DummyEmpty:
        def container(self):
            return self
        def __enter__(self):
            calls.append("enter_container")
            return self
        def __exit__(self, exc_type, exc, tb):
            calls.append("exit_container")
            return False

    monkeypatch.setattr(st, "empty", lambda: calls.append("empty") or DummyEmpty())
    monkeypatch.setattr(app, "_render_selected_page", lambda page: calls.append(f"render:{page}"))

    app._render_main_page("股票对比")

    assert calls == ["empty", "enter_container", "render:股票对比", "exit_container"]


def test_page_switch_second_run_skips_slow_sidebar(monkeypatch):
    import app
    import streamlit as st

    class DummySidebar:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    st.session_state.clear()
    st.session_state["main_page"] = "股票对比"
    st.session_state["_active_page"] = "股票对比"
    st.session_state[app._PAGE_SWITCH_PENDING_KEY] = True
    calls = []

    monkeypatch.setattr(st, "sidebar", DummySidebar())
    monkeypatch.setattr(st, "title", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "radio", lambda *args, **kwargs: "股票对比", raising=False)
    monkeypatch.setattr(app, "_render_main_page", lambda page: calls.append(f"render:{page}"))
    monkeypatch.setattr(app, "display_market_temperature", lambda: calls.append("market"))
    monkeypatch.setattr(app, "display_watchlist_sidebar", lambda: calls.append("watchlist") or None)
    monkeypatch.setattr(app, "display_watchlist_mini_panel", lambda summaries: calls.append("mini"))
    monkeypatch.setattr(app, "display_data_source_selector", lambda: calls.append("source"))

    app.main()

    assert calls == ["render:股票对比"]
    assert app._PAGE_SWITCH_PENDING_KEY not in st.session_state
