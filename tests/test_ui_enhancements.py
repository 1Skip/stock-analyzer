"""UI workspace enhancement tests."""

import pandas as pd

from ui.decision_dashboard import build_decision_snapshot
from ui.styles import CUSTOM_CSS
from ui.compare_page import (
    build_compare_insights,
    build_trend_dashboard_figure,
    build_trend_metrics,
    resolve_compare_inputs,
)
from ui.report_history_page import _list_reports
from ui.stock_search import parse_suggestion_label, suggest_stock_inputs


def test_stock_search_suggests_popular_cn_aliases():
    result = suggest_stock_inputs("\u8305\u53f0", "CN", limit=3)

    assert result[0]["symbol"] == "600519"
    assert result[0]["name"] == "\u8d35\u5dde\u8305\u53f0"
    assert parse_suggestion_label(result[0]["label"]) == ("600519", "\u8d35\u5dde\u8305\u53f0")


def test_stock_search_tolerates_common_near_match():
    result = suggest_stock_inputs("\u745e\u9e3d", "CN", limit=3)

    assert result[0]["symbol"] == "002997"
    assert result[0]["name"] == "\u745e\u9e44\u6a21\u5177"


def test_stock_search_tolerates_transposed_name(monkeypatch):
    import ui.stock_search as stock_search

    monkeypatch.setattr(
        stock_search,
        "_cn_stock_pool",
        lambda: (("002609", "\u6377\u987a\u79d1\u6280"), ("600021", "\u4e0a\u6d77\u7535\u529b")),
    )

    result = suggest_stock_inputs("\u987a\u6377\u79d1\u6280", "CN", limit=3)

    assert result[0]["symbol"] == "002609"
    assert result[0]["name"] == "\u6377\u987a\u79d1\u6280"


def test_compare_inputs_accept_names_and_codes(monkeypatch):
    monkeypatch.setattr(
        "ui.compare_page.resolve_cached_stock_input",
        lambda text, market: {
            "\u8305\u53f0": ("600519", "\u8d35\u5dde\u8305\u53f0"),
            "\u62db\u884c": ("600036", "\u62db\u5546\u94f6\u884c"),
        }.get(text),
    )
    monkeypatch.setattr(
        "ui.compare_page.quote_service.get_stock_name",
        lambda symbol, market: {"000858": "\u4e94\u7cae\u6db2"}.get(symbol, symbol),
    )

    resolved, warnings = resolve_compare_inputs(["\u8305\u53f0", "000858", "\u62db\u884c", "\u8305\u53f0"], "CN")

    assert [item["symbol"] for item in resolved] == ["600519", "000858", "600036"]
    assert resolved[0]["name"] == "\u8d35\u5dde\u8305\u53f0"
    assert any("\u91cd\u590d" in warning for warning in warnings)


def test_compare_inputs_accept_fuzzy_corrected_names(monkeypatch):
    monkeypatch.setattr(
        "ui.compare_page.resolve_cached_stock_input",
        lambda text, market: {"\u987a\u6377\u79d1\u6280": ("002609", "\u6377\u987a\u79d1\u6280")}.get(text),
    )

    resolved, warnings = resolve_compare_inputs(["\u987a\u6377\u79d1\u6280", "600021"], "CN")

    assert [item["symbol"] for item in resolved] == ["002609", "600021"]
    assert resolved[0]["name"] == "\u6377\u987a\u79d1\u6280"
    assert warnings == []


def test_compare_trend_metrics_include_return_risk_and_trend():
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    prices = [100 + i for i in range(40)] + [130 - i * 0.5 for i in range(40)]
    data = pd.DataFrame({"close": prices}, index=dates)

    metrics = build_trend_metrics("600519", "\u8d35\u5dde\u8305\u53f0", data)

    assert metrics["symbol"] == "600519"
    assert metrics["return_20d"] < 0
    assert metrics["return_60d"] is not None
    assert metrics["max_drawdown"] < 0
    assert metrics["volatility"] > 0
    assert 0 <= metrics["up_day_ratio"] <= 100
    assert metrics["ma_status"] in {"\u591a\u5934\u6392\u5217", "\u7a7a\u5934\u6392\u5217", "\u7ad9\u4e0aMA20", "\u8dcc\u7834MA20"}


def test_compare_insights_pick_best_candidates():
    metrics = [
        {
            "symbol": "600519",
            "name": "\u8d35\u5dde\u8305\u53f0",
            "return_20d": 8.0,
            "volatility": 20.0,
            "max_drawdown": -12.0,
            "trend_slope_20d": 0.2,
        },
        {
            "symbol": "600036",
            "name": "\u62db\u5546\u94f6\u884c",
            "return_20d": 3.0,
            "volatility": 12.0,
            "max_drawdown": -5.0,
            "trend_slope_20d": 0.5,
        },
    ]

    insights = build_compare_insights(metrics)
    values = [(title, item["symbol"]) for title, item, _ in insights]

    assert ("\u8fd120\u65e5\u6700\u5f3a", "600519") in values
    assert ("\u8d8b\u52bf\u659c\u7387\u6700\u5f3a", "600036") in values
    assert ("\u6ce2\u52a8\u6700\u4f4e", "600036") in values
    assert ("\u56de\u64a4\u6700\u5c0f", "600036") in values


def test_compare_trend_dashboard_has_three_chart_layers():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    history = {
        "600519": pd.DataFrame({"close": [100 + i for i in range(30)]}, index=dates),
        "600036": pd.DataFrame({"close": [100 + i * 0.5 for i in range(30)]}, index=dates),
    }

    fig = build_trend_dashboard_figure(history, {"600519": "\u8d35\u5dde\u8305\u53f0", "600036": "\u62db\u5546\u94f6\u884c"})

    assert len(fig.data) == 6
    assert "\u533a\u95f4\u56de\u64a4" in fig.layout.annotations[1].text
    assert "\u76f8\u5bf9\u5f3a\u5f31" in fig.layout.annotations[2].text


def test_history_reports_hide_latest_alias(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    (history_dir / "latest.md").write_text("latest", encoding="utf-8")
    (history_dir / "2026-05-13.md").write_text("dated", encoding="utf-8")

    monkeypatch.setattr("ui.report_history_page._history_dir", lambda: history_dir)

    assert [path.name for path in _list_reports()] == ["2026-05-13.md"]


def test_data_source_copy_mentions_new_sources():
    import inspect
    from ui.sidebar import display_data_source_selector

    source = inspect.getsource(display_data_source_selector)

    for keyword in ["东方财富", "腾讯财经", "同花顺", "巨潮", "研报", "EPS", "名称搜索"]:
        assert keyword in source


def test_decision_snapshot_scores_bullish_signal():
    snapshot = build_decision_snapshot(
        data=None,
        signals={
            "recommendation": "\u504f\u591a\u4fe1\u53f7",
            "macd": "\u91d1\u53c9\uff08\u504f\u591a\u4fe1\u53f7\uff09",
            "rsi": "\u4e2d\u6027",
            "kdj": "\u91d1\u53c9\uff08\u504f\u591a\u4fe1\u53f7\uff09",
            "boll": "\u4e2d\u8f68\u4e0a\u65b9\uff0c\u504f\u591a",
        },
        quote={"price": 10, "change": 1.2},
    )

    assert snapshot["score"] >= 60
    assert snapshot["tone"] in {"watch", "bullish"}


def test_decision_snapshot_exposes_stage2_dashboard_fields():
    snapshot = build_decision_snapshot(
        data=None,
        signals={
            "recommendation": "\u504f\u591a\u4fe1\u53f7",
            "macd": "\u91d1\u53c9",
            "kdj": "\u91d1\u53c9",
            "boll": "\u4e2d\u8f68\u4e0a\u65b9",
        },
        quote={"price": 12.34, "change": 1.8},
        extended_info={
            "fund_flow": {"main_net_inflow": 12000000, "main_net_inflow_ratio": 2.1},
            "research": {"reports": [{"title": "\u7814\u62a5"}]},
            "sector_attribution": {
                "industry": {"name": "\u7535\u529b", "change_pct": 1.2},
                "concepts": [{"name": "\u7eff\u7535", "change_pct": 2.5}],
            },
        },
    )

    assert snapshot["confidence"] > 0
    assert snapshot["position"]
    assert snapshot["entry_hint"]
    assert snapshot["key_levels"]["price"] == 12.34
    assert len(snapshot["agents"]) == 5
    for agent in snapshot["agents"]:
        assert {"name", "weight", "raw_score", "score_delta", "confidence", "evidence", "warnings"} <= set(agent)


def test_decision_dashboard_stage2_css_classes_exist():
    for class_name in [
        "decision-hero",
        "decision-score-ring",
        "decision-panel",
        "decision-chip",
        "decision-level-row",
        "agent-card-grid",
        "agent-score-pill",
    ]:
        assert class_name in CUSTOM_CSS


def test_agent_card_html_is_not_markdown_code_block():
    from ui.decision_dashboard import _render_agent_card

    html = _render_agent_card({
        "name": "技术分析 Agent",
        "summary": "趋势判断：中性",
        "stance": "中性",
        "weight": 30,
        "raw_score": 0,
        "score_delta": 0,
        "confidence": 55,
        "evidence": ["MACD 中性"],
        "warnings": [],
    })

    assert html.startswith("<div")
    assert "\n    <div" not in html
    assert 'class="agent-card neutral"' in html


def test_extended_info_exposes_latest_news_date():
    from ui.analyze_page import _latest_news_date

    assert _latest_news_date([
        {"title": "旧新闻", "date": "2026-05-13 15:00:00"},
        {"title": "测试新闻", "date": "2026-05-14 09:30:00"},
    ]) == "2026-05-14 09:30:00"
    assert _latest_news_date([]) == "--"


def test_analyze_page_renders_extended_info_placeholder():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert 'extended_info = extended_info or {"loading": True}' in source
    assert "扩展信息仍在加载或当前请求未及时返回" in source
    assert 'extended_info = futures[\'extended_info\'].result(timeout=2.5)' in source


def test_analyze_page_uses_code_name_title_card():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "个股分析标的" in source
    assert "当前标的" in source
    assert "def _render_current_stock_header" in source
    assert "display_name = stock_name if stock_name and stock_name != symbol else" in source
    assert "{html.escape(symbol)}{f\" · {html.escape(display_name)}\" if display_name else \"\"}" in source


def test_analyze_page_renders_market_news_section():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _render_market_news" in source
    assert "市场快讯 / 催化消息" in source
    assert "_render_market_news(extended_info)" in source


def test_stock_profile_section_is_never_dropped_when_loading():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert 'profile = profile or {"loading": True}' in source
    assert "基础资料仍在加载或当前请求未及时返回" in source
    assert 'with st.expander("基础资料 / 估值", expanded=False)' in source
    assert "profile = futures['profile'].result(timeout=2.5)" in source


def test_analyze_page_keeps_top_watchlist_action():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _render_watchlist_quick_action" in source
    assert "_render_watchlist_quick_action(" in source
    assert "quick_watchlist_" in source
    assert "加入自选" in source


def test_analyze_page_does_not_rewrite_instantiated_symbol_input():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")
    after_widget = source.split('key="analyze_symbol_input"', 1)[1]

    assert "st.session_state.analyze_symbol_input = symbol" not in after_widget


def test_analyze_page_explains_code_or_name_input():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "支持输入股票代码或名称" in source
    assert "000001、平安银行、贵州茅台、AAPL、00700" in source
    assert 'label_visibility="collapsed"' not in source.split('key="analyze_symbol_input"', 1)[0].split('st.text_input(', 1)[1]


def test_sidebar_watchlist_shows_full_list_and_single_detail():
    from pathlib import Path

    source = Path("ui/sidebar.py").read_text(encoding="utf-8")

    assert 'with st.expander(f"自选股（{len(watchlist)}）")' in source
    assert "wl_pick_" in source
    assert "wl_remove_" in source
    assert "_cached_watchlist_summary(" not in source
    assert "def display_watchlist_mini_panel" not in source
    assert "_cached_mini_analysis" not in source
    assert "自选详情" not in source
    assert "在主页查看完整分析" not in source


def test_sidebar_watchlist_click_opens_main_analysis():
    from pathlib import Path

    source = Path("ui/sidebar.py").read_text(encoding="utf-8")

    assert "def _open_watchlist_stock_in_main" in source
    assert "st.session_state.analyze_symbol = symbol" in source
    assert "st.session_state.analyze_symbol_input = symbol" in source
    assert "st.session_state.trigger_analysis = True" in source
    assert 'st.session_state.pending_main_page = "个股分析"' in source
    assert "_open_watchlist_stock_in_main(symbol, market, name)" in source


def test_sidebar_watchlist_click_does_not_keep_mini_panel_state():
    from pathlib import Path

    source = Path("ui/sidebar.py").read_text(encoding="utf-8")

    assert "wl_view_symbol" not in source
    assert "wl_view_market" not in source
    assert "wl_view_name" not in source


def test_app_applies_pending_main_page_before_radio():
    from pathlib import Path

    source = Path("app.py").read_text(encoding="utf-8")

    pending_index = source.index('pending_main_page = st.session_state.pop("pending_main_page", None)')
    radio_index = source.index("page = st.radio(")
    assert pending_index < radio_index


def test_backtest_page_resolves_name_and_renders_target_header():
    from pathlib import Path

    source = Path("backtest_ui.py").read_text(encoding="utf-8")

    assert "def _resolve_backtest_target" in source
    assert "resolve_cached_stock_input(query, market)" in source
    assert "股票代码或名称" in source
    assert 'with st.form("backtest_form")' in source
    assert 'st.form_submit_button("开始回测"' in source
    assert "回测标的" in source
    assert "_render_backtest_target_header(symbol, stock_name, market" in source
    assert "adapter.save_results(symbol, market, output)" in source


def test_settings_page_documents_wechat_push_setup():
    from pathlib import Path

    source = Path("ui/settings_page.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/daily_analysis.yml").read_text(encoding="utf-8")

    assert "企业微信" in source
    assert 'setx NOTIFY_CHANNELS "wechat"' in source
    assert 'setx WECHAT_WEBHOOK_URL "你的企业微信机器人Webhook"' in source
    assert 'setx NOTIFY_CHANNELS "feishu,wechat"' in source
    assert 'channel_labels = {"feishu": "飞书", "wechat": "企业微信"}' in source
    assert "format_func=lambda channel: channel_labels.get(channel, channel)" in source
    assert "WECHAT_WEBHOOK_URL" in workflow
    assert "vars.NOTIFY_CHANNELS" in workflow


def test_ai_analysis_ui_is_optional_auxiliary():
    from pathlib import Path

    source = Path("ui/ai_analysis_ui.py").read_text(encoding="utf-8")

    assert "AI 辅助解读（可选）" in source
    assert "主结论以 A股决策委员会 为准" in source
    assert 'with st.expander("展开 AI 辅助解读", expanded=False)' in source
