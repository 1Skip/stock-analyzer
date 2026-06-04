"""Navigation isolation tests for the Streamlit app shell."""

from ui.styles import CUSTOM_CSS


def test_all_sidebar_pages_route_to_renderer():
    from app import _render_selected_page

    pages = [
        "个股分析",
        "涨跌排行",
        "智能推荐",
        "股票对比",
        "回测验证",
        "历史日报",
        "系统状态",
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
    assert "render_committee_status_card()" in source
    assert "系统状态" in source
    assert "render_system_status_page()" in inspect.getsource(app._render_selected_page)


def test_page_switch_does_not_clear_page_cache_state():
    import inspect
    import app

    source = inspect.getsource(app._sync_active_page)

    assert "st.session_state.pop" not in source
    assert "analyzed_data" not in source
    assert "hot_data" not in source
    assert "rec_results" not in source


def test_light_sidebar_renders_before_main_page():
    import inspect
    import app

    source = inspect.getsource(app.main)

    render_index = source.index("_render_main_page(page)")
    watchlist_index = source.index("display_watchlist_sidebar()")
    source_index = source.index("display_data_source_selector()")
    market_index = source.index("display_market_temperature()")

    assert watchlist_index < render_index
    assert source_index < render_index
    assert market_index < render_index


def test_custom_css_does_not_keep_stale_pages_visible():
    assert ".stale-element" not in CUSTOM_CSS
    assert "[data-stale=\"true\"]" not in CUSTOM_CSS


def test_committee_status_card_renders_local_status_only(monkeypatch):
    import inspect
    import app
    import config
    from ui.committee_status import build_committee_status

    source = inspect.getsource(app.main)

    assert "render_committee_status_card" in source

    monkeypatch.setattr(config, "AI_DEBATE_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(config, "DAILY_REPORT_ENABLED", True)
    monkeypatch.setattr(config, "T1_PLAN_AUTO_ENABLED", True)

    status = build_committee_status()
    labels = [item["label"] for item in status["stages"]]
    status_text = " ".join(
        [item["name"] for item in status["stages"]]
        + labels
        + ["本地日报", "LLM辩论", "T+1预热"]
    )

    assert len(status["stages"]) == 5
    assert "本地日报" in labels
    assert "LLM多空辩论" in labels
    assert "T+1缓存预热" in labels
    for removed_text in ["飞书", "企业微信", "Actions", "推送"]:
        assert removed_text not in status_text


def test_page_switch_preserves_page_state_and_reruns(monkeypatch):
    import app
    import streamlit as st

    st.session_state.clear()
    st.session_state["_active_page"] = "历史日报"
    st.session_state["hot_data"] = {"old": True}
    st.session_state["hot_data_loaded"] = True
    st.session_state["rec_results"] = {"old": True}
    st.session_state["analyzed_data"] = object()
    reruns = []

    monkeypatch.setattr(st, "rerun", lambda: reruns.append(True))

    changed = app._sync_active_page("股票对比")

    assert changed is True
    assert st.session_state["_active_page"] == "股票对比"
    assert st.session_state["hot_data"] == {"old": True}
    assert st.session_state["hot_data_loaded"] is True
    assert st.session_state["rec_results"] == {"old": True}
    assert "analyzed_data" in st.session_state
    assert reruns == [True]


def test_first_page_load_does_not_force_rerun():
    import app
    import streamlit as st

    st.session_state.clear()

    changed = app._sync_active_page("个股分析")

    assert changed is False
    assert st.session_state["_active_page"] == "个股分析"
    assert app._PAGE_SWITCH_PENDING_KEY not in st.session_state


def test_page_switch_keeps_current_page_state(monkeypatch):
    import app
    import streamlit as st

    st.session_state.clear()
    st.session_state["_active_page"] = "股票对比"
    st.session_state["hot_data"] = {"current": True}
    reruns = []

    monkeypatch.setattr(st, "rerun", lambda: reruns.append(True))

    changed = app._sync_active_page("涨跌排行")

    assert changed is True
    assert st.session_state["_active_page"] == "涨跌排行"
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
    st.session_state["_active_page"] = "个股分析"
    st.session_state["main_page"] = "股票对比"
    calls = []

    monkeypatch.setattr(st, "sidebar", DummySidebar())
    monkeypatch.setattr(st, "title", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(st, "radio", lambda *args, **kwargs: "股票对比", raising=False)
    monkeypatch.setattr(st, "rerun", lambda: calls.append("rerun"))
    monkeypatch.setattr(app, "_render_selected_page", lambda page: calls.append(f"render:{page}"))
    monkeypatch.setattr(app, "render_committee_status_card", lambda: None)
    monkeypatch.setattr(app, "display_market_temperature", lambda: None)
    monkeypatch.setattr(app, "display_watchlist_sidebar", lambda: None)
    monkeypatch.setattr(app, "display_data_source_selector", lambda: None)

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


def test_page_switch_second_run_keeps_light_sidebar(monkeypatch):
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
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(st, "radio", lambda *args, **kwargs: "股票对比", raising=False)
    monkeypatch.setattr(app, "_render_main_page", lambda page: calls.append(f"render:{page}"))
    monkeypatch.setattr(app, "render_committee_status_card", lambda: calls.append("committee"))
    monkeypatch.setattr(app, "display_market_temperature", lambda: calls.append("market"))
    monkeypatch.setattr(app, "display_watchlist_sidebar", lambda: calls.append("watchlist") or None)
    monkeypatch.setattr(app, "display_data_source_selector", lambda: calls.append("source"))

    app.main()

    assert calls == ["committee", "watchlist", "source", "market", "render:股票对比"]
    assert app._PAGE_SWITCH_PENDING_KEY not in st.session_state
