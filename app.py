"""股票分析系统 Streamlit 入口。"""
import streamlit as st


st.set_page_config(
    page_title="股票分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.styles import CUSTOM_CSS

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

from config import MARKET_INDEX_ENABLED
from ui.analyze_page import analyze_stock_page
from ui.compare_page import compare_stocks_page
from ui.hot_stocks_page import hot_stocks_page
from ui.recommend_page import recommended_stocks_page
from ui.report_history_page import report_history_page
from ui.committee_status import render_committee_status_card
from ui.sidebar import (
    display_data_source_selector,
    display_market_temperature,
    display_watchlist_sidebar,
)

from ui.charts import (  # noqa: F401
    _indicator_layout,
    plot_boll_chart,
    plot_candlestick_chart,
    plot_intraday_chart,
    plot_kdj_chart,
    plot_macd_chart,
    plot_main_accumulation_chart,
    plot_rsi_chart,
    plot_volume_chart,
)
from ui.ai_analysis_ui import AI_MODEL_OPTIONS, _detect_provider  # noqa: F401
from ui.analyze_page import _validate_symbol, display_signals  # noqa: F401


_PAGE_SWITCH_PENDING_KEY = "_page_switch_pending"


def _sync_active_page(page):
    """切换主页面时 rerun 卸载旧 DOM，同时保留各页面已加载状态。"""
    if "_active_page" not in st.session_state:
        st.session_state["_active_page"] = page
        return False
    if st.session_state.get("_active_page") == page:
        return False
    st.session_state["_active_page"] = page
    st.session_state[_PAGE_SWITCH_PENDING_KEY] = True
    st.rerun()
    return True


def _render_selected_page(page):
    """渲染当前选中的主页面，避免各页面输出逻辑散落在入口中。"""
    if page == "个股分析":
        analyze_stock_page()
    elif page == "热门板块":
        hot_stocks_page()
    elif page == "智能推荐":
        recommended_stocks_page()
    elif page == "股票对比":
        compare_stocks_page()
    elif page == "回测验证":
        from backtest_ui import backtest_page

        backtest_page()
    elif page == "历史日报":
        report_history_page()


def _render_main_page(page):
    """把主页面挂在稳定占位容器内，避免切页时旧页面长列表残留。"""
    main_slot = st.empty()
    with main_slot.container():
        _render_selected_page(page)


def main():
    """渲染主应用。"""
    nav_items = [
        "个股分析",
        "热门板块",
        "智能推荐",
        "股票对比",
        "回测验证",
        "历史日报",
    ]
    nav_emoji = {
        "个股分析": "📈",
        "热门板块": "🔥",
        "智能推荐": "💡",
        "股票对比": "📊",
        "回测验证": "⏱️",
        "历史日报": "📄",
    }

    if "main_page" not in st.session_state:
        st.session_state.main_page = nav_items[0]
    pending_main_page = st.session_state.pop("pending_main_page", None)
    if pending_main_page in nav_items:
        st.session_state.main_page = pending_main_page

    with st.sidebar:
        st.title("股票分析系统")
        st.markdown("---")

        page = st.radio(
            "功能菜单",
            options=nav_items,
            key="main_page",
            format_func=lambda item: f"{nav_emoji.get(item, '')} {item}",
        )
        render_committee_status_card()

        display_watchlist_sidebar()
        display_data_source_selector()
        if MARKET_INDEX_ENABLED:
            display_market_temperature()

        st.caption("风险提示：本系统仅供参考，不构成投资建议")

    if _sync_active_page(page):
        return

    page_switch_pending = st.session_state.pop(_PAGE_SWITCH_PENDING_KEY, False)

    _render_main_page(page)

    if page_switch_pending:
        return


if __name__ == "__main__":
    main()
