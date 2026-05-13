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
    assert "page_container = st.empty()" in source
    assert "_render_selected_page(page)" in source
    assert "options=nav_items" in source
    assert "key=\"main_page\"" in source


def test_main_page_renders_before_slow_sidebar_widgets():
    import inspect
    import app

    source = inspect.getsource(app.main)

    render_index = source.index("_render_selected_page(page)")
    market_index = source.index("display_market_temperature()")
    watchlist_index = source.index("display_watchlist_sidebar()")

    assert render_index < market_index
    assert render_index < watchlist_index


def test_custom_css_does_not_keep_stale_pages_visible():
    assert ".stale-element" not in CUSTOM_CSS
    assert "[data-stale=\"true\"]" not in CUSTOM_CSS
