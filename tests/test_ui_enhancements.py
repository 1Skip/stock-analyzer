"""UI workspace enhancement tests."""

import pandas as pd

from ui.decision_dashboard import build_decision_snapshot, build_defense_dashboard, build_trade_plan
from ui.styles import CUSTOM_CSS
from ui.compare_page import (
    build_compare_insights,
    build_trend_dashboard_figure,
    build_trend_metrics,
    resolve_compare_inputs,
)
from ui.report_history_page import _list_reports
from ui.stock_search import parse_suggestion_label, suggest_stock_inputs
from ui.ai_analysis_ui import _agent_has_displayable_content, _has_meaningful_content


def test_stock_search_suggests_popular_cn_aliases():
    result = suggest_stock_inputs("\u8305\u53f0", "CN", limit=3)

    assert result[0]["symbol"] == "600519"
    assert result[0]["name"] == "\u8d35\u5dde\u8305\u53f0"
    assert parse_suggestion_label(result[0]["label"]) == ("600519", "\u8d35\u5dde\u8305\u53f0")


def test_ai_analysis_empty_structured_fields_are_not_meaningful():
    empty_structured = {
        "MACD解读": "",
        "RSI解读": " ",
        "风险因素": [],
        "关注点位": {},
    }

    assert not _has_meaningful_content(empty_structured)
    assert _has_meaningful_content({"MACD解读": "金叉形成"})


def test_ai_analysis_agent_fallback_content_is_displayable():
    empty_structured_agent = {
        "structured": {"风险等级": "", "风险因素": [], "关注点位": {}},
        "content": "",
        "error": "",
    }
    raw_content_agent = {
        "structured": {"风险等级": "", "风险因素": [], "关注点位": {}},
        "content": "模型返回了原始风险说明",
        "error": "",
    }

    assert not _agent_has_displayable_content(empty_structured_agent)
    assert _agent_has_displayable_content(raw_content_agent)


def test_long_running_pages_use_stable_loading_contexts():
    from pathlib import Path

    pages = [
        Path("ui/analyze_page.py"),
        Path("ui/hot_stocks_page.py"),
        Path("ui/recommend_page.py"),
        Path("ui/compare_page.py"),
        Path("backtest_ui.py"),
        Path("ui/report_history_page.py"),
    ]

    for page in pages:
        source = page.read_text(encoding="utf-8")
        assert "ui.background_tasks" not in source
        assert (
            "status_loading" in source
            or "make_progress_reporter" in source
            or "_render_analysis_loading" in source
            or "_render_hot_loading" in source
        )


def test_analyze_page_keeps_analyzed_target_separate_from_input():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "st.session_state.analyzed_symbol = symbol" in source
    assert "st.session_state.analyzed_market = market" in source
    assert "st.session_state.analyzed_period = period" in source
    assert "cached_symbol = st.session_state.get(\"analyzed_symbol\"" in source


def test_analyze_page_uses_single_unified_target_header():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _render_analysis_target_header" in source
    assert "当前分析标的" in source
    assert "个股分析标的" not in source
    assert "analyzed_target = _get_analyzed_target()" in source


def test_analyze_page_hides_stale_result_when_input_changes():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _is_current_input_analyzed" in source
    assert "analyzed_target = _get_analyzed_target() if _is_current_input_analyzed() else None" in source
    assert "has_fresh_task_result" in source
    assert "if _is_current_input_analyzed() or has_fresh_task_result" in source
    assert "def _clear_analyzed_result" in source
    assert "_clear_analyzed_result()" in source


def test_analyze_page_syncs_cached_result_when_returning_to_page():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _sync_analyze_input_to_cached_result" in source
    assert "st.session_state.analyze_symbol_input = analyzed_symbol" in source
    assert "if not pending_watchlist_analysis and not pending_quick_match:" in source
    assert "_sync_analyze_input_to_cached_result()" in source


def test_analyze_page_binds_cached_result_to_target_key():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _analysis_target_key" in source
    assert "def _has_valid_analyzed_result" in source
    assert "def _tag_analysis_data" in source
    assert "def _data_matches_target" in source
    assert "st.session_state.analyzed_target_key = _analysis_target_key(symbol, market, period)" in source
    assert "st.session_state.pending_analyze_input_sync" in source
    assert "_analysis_target_key(" in source.split("has_fresh_task_result", 1)[1]


def test_analyze_page_rejects_cross_symbol_quote_cache():
    from ui.analyze_page import _quote_for_target, _quote_matches_target

    data = pd.DataFrame({
        "open": [9.8, 10.0],
        "high": [10.2, 10.3],
        "low": [9.7, 9.9],
        "close": [10.0, 10.1],
        "volume": [1000, 1200],
    })
    stale_quote = {
        "symbol": "600519",
        "price": 41.09,
        "open": 40.0,
        "high": 42.0,
        "low": 39.8,
        "volume": 10000,
    }

    assert _quote_matches_target(stale_quote, "000001", "CN") is False
    fallback = _quote_for_target(stale_quote, "000001", "CN", data)
    assert fallback["price"] == 10.1
    assert fallback["source"] == "历史K线兜底"


def test_analyze_page_rejects_cross_symbol_dataframe_cache():
    import streamlit as st
    from ui.analyze_page import _has_valid_analyzed_result, _is_current_input_analyzed, _tag_analysis_data

    st.session_state.clear()
    data = pd.DataFrame({"close": [10.0, 10.1]})
    st.session_state.analyze_symbol = "000001"
    st.session_state.analyze_symbol_input = "000001"
    st.session_state.analyze_market = "CN"
    st.session_state.analyze_period = "1y"
    st.session_state.analyzed_symbol = "000001"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("000001", "CN", "1y")
    st.session_state.analyzed_data = _tag_analysis_data(data, "600519", "CN", "1y")

    assert _has_valid_analyzed_result() is False
    assert _is_current_input_analyzed() is False


def test_analyze_page_rejects_stale_cn_daily_kline_after_close(monkeypatch):
    import streamlit as st
    import ui.analyze_page as analyze_page
    from ui.analyze_page import (
        _has_stale_analyzed_result_for_current_input,
        _has_valid_analyzed_result,
        _tag_analysis_data,
    )

    class FakeTimestamp(pd.Timestamp):
        @classmethod
        def now(cls, tz=None):
            return pd.Timestamp("2026-05-21 17:11:00")

    monkeypatch.setattr(analyze_page.pd, "Timestamp", FakeTimestamp)
    st.session_state.clear()
    data = pd.DataFrame(
        {
            "open": [14.23],
            "high": [15.27],
            "low": [14.00],
            "close": [14.21],
            "volume": [206980000],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-05-20")]),
    )
    st.session_state.analyze_symbol = "600246"
    st.session_state.analyze_symbol_input = "600246"
    st.session_state.analyze_market = "CN"
    st.session_state.analyze_period = "1y"
    st.session_state.analyzed_symbol = "600246"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("600246", "CN", "1y")
    st.session_state.analyzed_data = _tag_analysis_data(data, "600246", "CN", "1y")

    assert _has_valid_analyzed_result() is False
    assert _has_stale_analyzed_result_for_current_input() is True


def test_analyze_page_syncs_stale_input_to_valid_cached_result():
    import streamlit as st
    from ui.analyze_page import _sync_analyze_input_to_cached_result, _tag_analysis_data

    st.session_state.clear()
    data = _tag_analysis_data(pd.DataFrame({"close": [7.1, 7.2]}), "600016", "CN", "1y")
    st.session_state.analyze_symbol = "000001"
    st.session_state.analyze_symbol_input = "000001"
    st.session_state.analyze_market = "CN"
    st.session_state.analyze_period = "1y"
    st.session_state.analyzed_symbol = "600016"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("600016", "CN", "1y")
    st.session_state.analyzed_data = data

    _sync_analyze_input_to_cached_result()

    assert st.session_state.analyze_symbol == "600016"
    assert st.session_state.analyze_symbol_input == "600016"
    assert st.session_state.analyze_market == "CN"
    assert st.session_state.analyze_period == "1y"


def test_analyze_page_restores_cached_result_after_page_switch():
    import streamlit as st
    from ui.analyze_page import _sync_analyze_input_to_cached_result, _tag_analysis_data

    st.session_state.clear()
    data = _tag_analysis_data(pd.DataFrame({"close": [7.1, 7.2]}), "600626", "CN", "1y")
    st.session_state.analyze_symbol = "600016"
    st.session_state.analyze_symbol_input = "600016"
    st.session_state.analyze_market = "CN"
    st.session_state.analyze_period = "1y"
    st.session_state.analyzed_symbol = "600626"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("600626", "CN", "1y")
    st.session_state.analyzed_data = data

    _sync_analyze_input_to_cached_result()

    assert st.session_state.analyze_symbol == "600626"
    assert st.session_state.analyze_symbol_input == "600626"
    assert st.session_state.analyze_market == "CN"
    assert st.session_state.analyze_period == "1y"


def test_analyze_page_enter_and_button_share_current_input_submit_handler():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _queue_analysis_for_current_input" in source
    search_body = source.split('key="analyze_symbol_input"', 1)[1].split("analyzed_target =", 1)[0]
    assert "on_change=_queue_analysis_for_current_input" in search_body
    assert "on_click=_queue_analysis_for_current_input" in search_body


def test_analyze_page_search_input_is_not_wrapped_in_form():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")
    search_body = source.split('key="analyze_symbol_input"', 1)[0].rsplit("#", 1)[-1]

    assert 'with st.form("search_form")' not in search_body
    assert "st.form_submit_button" not in source


def test_analyze_page_queue_analysis_uses_current_text_input_value():
    import streamlit as st
    from ui.analyze_page import _queue_analysis_for_current_input, _tag_analysis_data

    st.session_state.clear()
    data = _tag_analysis_data(pd.DataFrame({"close": [7.1, 7.2]}), "600016", "CN", "1y")
    st.session_state.analyze_symbol = "600016"
    st.session_state.analyze_symbol_input = "贵州茅台"
    st.session_state.analyzed_symbol = "600016"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("600016", "CN", "1y")
    st.session_state.analyzed_data = data

    _queue_analysis_for_current_input()

    assert st.session_state.analyze_symbol == "贵州茅台"
    assert st.session_state.trigger_analysis is True
    assert "analyzed_data" not in st.session_state


def test_analyze_page_queue_analysis_strips_concatenated_cn_codes():
    import streamlit as st
    from ui.analyze_page import _queue_analysis_for_current_input

    st.session_state.clear()
    st.session_state.analyze_symbol = "000001"
    st.session_state.analyze_symbol_input = "000001600626"
    st.session_state.analyze_market = "CN"

    _queue_analysis_for_current_input()

    assert st.session_state.analyze_symbol == "600626"
    assert st.session_state.analyze_symbol_input == "600626"
    assert st.session_state.trigger_analysis is True


def test_analyze_page_queue_analysis_can_skip_input_sync_after_widget_creation():
    import streamlit as st
    from ui.analyze_page import _queue_analysis_for_current_input

    st.session_state.clear()
    st.session_state.analyze_symbol = "000001"
    st.session_state.analyze_symbol_input = "000001600626"
    st.session_state.analyze_market = "CN"

    _queue_analysis_for_current_input(sync_input=False)

    assert st.session_state.analyze_symbol == "600626"
    assert st.session_state.analyze_symbol_input == "000001600626"
    assert st.session_state.trigger_analysis is True


def test_boll_price_line_uses_visible_dark_theme_color():
    from pathlib import Path

    source = Path("ui/charts.py").read_text(encoding="utf-8")
    boll_body = source.split("def plot_boll_chart", 1)[1].split("def plot_main_accumulation_chart", 1)[0]

    assert "name='价格', line=dict(color='#f8fafc'" in boll_body
    assert "name='价格', line=dict(color='black'" not in boll_body


def test_volume_header_matches_ths_hand_unit_and_turnover():
    import pandas as pd
    from ui.analyze_page import _latest_volume_values

    data = pd.DataFrame({"volume": [
        90414, 107126, 127865, 101912, 114174,
        93343, 78977, 88470, 106701, 126969,
    ]})
    profile = {"float_shares": 458859916.0}

    assert _latest_volume_values(data, profile) == [
        ("量", "12.70万"),
        ("MA5", "98892.00"),
        ("MA10", "10.36万"),
        ("换手", "2.77%"),
    ]


def test_volume_header_uses_realtime_volume_for_current_day_ma():
    import pandas as pd
    from ui.analyze_page import _latest_volume_values

    data = pd.DataFrame({"volume": [
        6192576, 8740527, 7439800, 6717828, 5904970,
        8149267, 6880449, 6956600, 4403998, 5788700,
    ]}, index=pd.date_range("2026-05-07", periods=10, freq="B"))
    data.attrs["volume_unit"] = "share"
    profile = {"float_shares": 662212199.0}
    quote = {"volume": 64735.54, "volume_unit": "hand", "quote_date": "2026-05-21"}

    assert _latest_volume_values(data, profile, quote) == [
        ("量", "64735.54"),
        ("MA5", "61006.60"),
        ("MA10", "67455.69"),
        ("换手", "0.98%"),
    ]


def test_volume_header_ignores_realtime_volume_without_quote_date():
    import pandas as pd
    from ui.analyze_page import _latest_volume_values

    data = pd.DataFrame({"volume": [
        6192576, 8740527, 7439800, 6717828, 5904970,
        8149267, 6880449, 6956600, 4403998, 5788700,
    ]}, index=pd.date_range("2026-05-07", periods=10, freq="B"))
    data.attrs["volume_unit"] = "share"
    profile = {"float_shares": 662212199.0}
    quote = {"volume": 64735.54, "volume_unit": "hand"}

    assert _latest_volume_values(data, profile, quote) == [
        ("量", "57887.00"),
        ("MA5", "64358.03"),
        ("MA10", "67174.71"),
        ("换手", "0.87%"),
    ]


def test_cached_daily_kline_fallback_infers_volume_unit(tmp_path, monkeypatch):
    import json
    from datetime import datetime

    from data_fetcher import StockDataFetcher
    from ui.analyze_page import _load_cached_daily_kline_fallback

    cache_file = tmp_path / "stock_cache.json"
    data = pd.DataFrame(
        {
            "open": [10.0, 10.2],
            "high": [10.5, 10.8],
            "low": [9.8, 10.0],
            "close": [10.3, 10.6],
            "volume": [6_000_000, 7_000_000],
        },
        index=pd.to_datetime(["2026-06-03", "2026-06-04"]),
    )
    payload = {
        StockDataFetcher._offline_cache_key("000001", "qfq"): {
            "timestamp": datetime.now().isoformat(),
            "data": data.to_json(orient="split", date_format="iso"),
        }
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(StockDataFetcher, "_offline_cache_file", str(cache_file))

    restored = _load_cached_daily_kline_fallback("000001", "CN")

    assert restored.attrs["volume_unit"] == "share"


def test_recommend_page_shows_multi_factor_diagnostics():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "def _render_multi_factor_diagnostics" in source
    assert "筛选诊断" in source
    assert "主要卡点" in source
    assert "核心因子命中" in source
    assert "深度数据可用性" in source
    assert 'st.session_state.rec_results.get("diagnostics")' in source


def test_recommend_page_uses_real_stage_progress():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "def _make_progress_callback" in source
    assert "def _format_progress_message" in source
    assert "阶段：" in source
    assert "股票池" in source
    assert "市值通过" in source
    assert "轻筛通过" in source
    assert "深度检查" in source
    assert "当前命中" in source
    assert '"result_count" not in metrics' in source
    assert "已深查" in source
    assert "progress_callback=progress_callback" in source
    assert 'with status_loading(f"\\u6b63\\u5728\\u5206\\u6790' not in source


def test_recommend_page_filters_removed_multi_factor_fields():
    from ui.recommend_page import _filter_removed_multi_factor_fields

    stock = {
        "strategy_checks": {
            "市值<300亿": True,
            "个股资金流入": False,
            "消息/公告/研报催化": False,
            "近7日涨停活跃": True,
            "连涨3日": True,
        },
        "strategy_details": {
            "个股资金流": "数据缺失/接口失败",
            "消息催化": "旧字段",
            "催化依据": "旧字段",
            "近7日涨停": "是",
            "主力净流入趋势": "3000 万",
        },
    }

    filtered = _filter_removed_multi_factor_fields(stock, "多因子稳健型")

    assert "个股资金流入" not in filtered["strategy_checks"]
    assert "消息/公告/研报催化" not in filtered["strategy_checks"]
    assert "近7日涨停活跃" not in filtered["strategy_checks"]
    assert "个股资金流" not in filtered["strategy_details"]
    assert "消息催化" not in filtered["strategy_details"]
    assert "催化依据" not in filtered["strategy_details"]
    assert "近7日涨停" not in filtered["strategy_details"]
    assert filtered["strategy_checks"]["连涨3日"] is True
    assert filtered["strategy_details"]["主力净流入趋势"] == "3000 万"


def test_recommend_page_uses_intelligent_stock_picking_title():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "智能选股推荐" in source


def test_recommend_page_isolates_running_state_and_request_key():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "rec_is_running" in source
    assert "rec_active_request_key" in source
    assert "current_request_key" in source
    assert "is_current_request_running" in source
    assert "is_other_request_running" in source
    assert "_format_request_key_label" in source
    assert "_result_matches_request" in source
    assert "本策略生成中" in source
    assert "其他计划生成中" in source
    assert "其他 T+1 计划正在生成" in source
    assert "完成前不会展示旧推荐或旧诊断" in source


def test_recommend_page_restores_progress_for_running_request():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "rec_progress_snapshots" in source
    assert "def _save_progress_snapshot" in source
    assert "def _render_saved_progress" in source
    assert "def _clear_progress_snapshot" in source
    assert "_make_progress_callback(progress_placeholder, strategy, sector, current_request_key)" in source
    assert "_render_saved_progress(progress_placeholder, current_request_key, strategy, sector)" in source


def test_recommend_page_displays_alpha_ranker_fields():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "Alpha评分" in source
    assert "rank_reason" in source
    assert "rank_penalty" in source


def test_recommend_page_shows_t1_cache_hit_without_rescanning():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "已读取 T+1 推荐计划缓存" in source
    assert "未重新扫描股票池" in source
    assert "只有点击“生成 T+1 推荐计划”才会重新运行策略" in source
    assert "龙头股推荐" not in source


def test_recommend_page_limits_sector_options_by_strategy():
    from ui.recommend_page import _sector_options_for_strategy

    assert _sector_options_for_strategy("激进突破型") == ["全部"]
    assert _sector_options_for_strategy("多因子稳健型") == ["全部"]
    assert _sector_options_for_strategy("短线") == ["全部", "苹果概念", "特斯拉概念", "电力", "算力租赁"]
    assert _sector_options_for_strategy("长线") == ["全部", "苹果概念", "特斯拉概念", "电力", "算力租赁"]


def test_recommend_page_hides_internal_t1_diagnostics():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "T+1 推荐计划：生成时间" in source
    assert "数据来源" not in source
    assert "生成方式" not in source
    assert "生成耗时" not in source
    assert "预热状态" not in source
    assert "not_requested" not in source
    assert 'trigger = metrics.get("trigger") or "--"' not in source


def test_recommend_page_groups_plan_review_buttons():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "def _render_strategy_review" in source
    assert "刷新最近交易日复盘" in source
    assert "复盘交易日" in source
    assert "latest_strategy_review" in source
    assert "明日进化建议" in source
    assert "历史计划" in source
    block = source.split('st.button("回看计划表现"', 1)[0].split("col1, col2, col3, col4, col5", 1)[-1]
    assert "with col3:" in block
    history_block = source.split('st.button("统计历史计划"', 1)[0].split('st.button("回看计划表现"', 1)[-1]
    assert "with col4:" in history_block
    strategy_block = source.split('st.button("刷新最近交易日复盘"', 1)[0].split('st.button("统计历史计划"', 1)[-1]
    assert "with col5:" in strategy_block


def test_report_history_page_groups_action_buttons():
    from pathlib import Path

    source = Path("ui/report_history_page.py").read_text(encoding="utf-8")

    assert "col_generate, col_refresh, _ = st.columns([1.1, 1, 4])" in source
    refresh_block = source.split('st.button("刷新列表"', 1)[-1]
    assert 'width="stretch"' in refresh_block.split("):", 1)[0]


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
    assert len(snapshot["agents"]) == 6
    for agent in snapshot["agents"]:
        assert {"name", "weight", "raw_score", "score_delta", "confidence", "evidence", "warnings"} <= set(agent)


def test_decision_snapshot_falls_back_to_kline_when_quote_price_is_zero():
    data = pd.DataFrame([{
        "close": 16.8,
        "boll_upper": 18.0,
        "boll_mid": 16.5,
        "boll_lower": 15.0,
        "ma20": 16.4,
    }])

    snapshot = build_decision_snapshot(
        data=data,
        signals={"recommendation": "偏多信号"},
        quote={"price": 0, "high": 0, "low": 0, "open": 0, "change": -100},
    )

    assert snapshot["key_levels"]["price"] == 16.8
    assert snapshot["entry_hint"] != "等待有效价格数据"


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


def test_trade_plan_card_builds_explicit_levels_from_real_indicators():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    data = pd.DataFrame({
        "high": [10.5 + i * 0.05 for i in range(20)],
        "low": [9.8 + i * 0.04 for i in range(20)],
        "close": [10 + i * 0.05 for i in range(20)],
        "ma60": [9.6 + i * 0.02 for i in range(20)],
    }, index=dates)
    snapshot = {
        "score": 72,
        "confidence": 76,
        "risk_level": "中",
        "action": "轻仓试探",
        "position": "1-2成",
        "key_levels": {
            "price": 10.95,
            "support": 9.8,
            "mid": 10.4,
            "resistance": 11.2,
            "ma20": 10.3,
        },
    }

    plan = build_trade_plan(snapshot, data)

    assert plan["current_action"] == "轻仓试探"
    assert "9.80" in plan["buy_zone"]
    assert "10.40" in plan["add_condition"]
    assert plan["stop_loss"] < 9.8
    assert plan["take_profit_1"] == 11.2
    assert plan["position"] == "1-2成"
    assert "未使用模拟" in plan["data_basis"]


def test_trade_plan_card_uses_shared_trade_plan_builder():
    from pathlib import Path

    source = Path("ui/decision_dashboard.py").read_text(encoding="utf-8")

    assert "from trade_plan import build_trade_plan_from_levels" in source
    assert "return build_trade_plan_from_levels(" in source


def test_defense_dashboard_uses_five_real_data_dimensions():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    data = pd.DataFrame({
        "close": [10 + i * 0.1 for i in range(70)],
        "volume": [1000000 + i * 10000 for i in range(70)],
        "ma60": [9 + i * 0.08 for i in range(70)],
        "rsi": [55 + (i % 5) for i in range(70)],
    }, index=dates)
    benchmark_data = pd.DataFrame({
        "close": [3000 + i * 2 for i in range(70)],
    }, index=dates)
    snapshot = {
        "score": 75,
        "risk_level": "低",
        "recommendation": "偏多信号",
        "confidence": 82,
        "key_levels": {"price": 16.9, "support": 15.8, "resistance": 17.8, "ma20": 16.5},
        "risk_alerts": [],
    }
    extended_info = {
        "financial": {"metrics": {"归母净利润": 10000000, "经营现金流量净额": 5000000}},
        "fund_flow": {
            "main_net_inflow": 1200000,
            "five_day_main_net_inflow": 3000000,
            "main_net_inflow_ratio": 2.2,
            "super_large_net_inflow": 800000,
            "large_net_inflow": 600000,
        },
        "research": {"eps_consensus": {"values": {"2025预测EPS": 0.8, "2026预测EPS": 1.0}}},
        "dividend": {"cash_dividend_per_share": 0.169, "source": "新浪财经历史分红"},
    }
    profile = {"pe_ttm": 18.0, "pb": 1.9, "turnover_rate": 3.2}

    defense = build_defense_dashboard(snapshot, data, benchmark_data, extended_info, profile)
    metrics = {item["name"]: item for item in defense["core_metrics"]}

    assert defense["overall"] >= 60
    assert [item["name"] for item in defense["dimensions"]] == ["估值", "成长", "趋势", "安全", "资金"]
    assert all(0 <= item["score"] <= 100 for item in defense["dimensions"])
    assert "公开真实数据源" in defense["data_basis"]
    assert defense["summary"]["state"] in {"趋势持有", "试探建仓", "压力减仓", "底部观察", "防御观望", "风险回避"}
    assert defense["summary"]["risk_label"] in {"低风险", "中等风险", "高风险"}
    assert [group["title"] for group in defense["reason_groups"]] == ["主要风险", "观察项", "支撑项"]
    assert all(group["items"] for group in defense["reason_groups"])
    assert defense["signal_state"]["name"] in {"趋势持有", "试探建仓", "压力减仓", "底部观察", "防御观望", "风险回避"}
    assert defense["signal_state"]["triggers"]
    assert set(metrics) >= {"PEG", "相对强弱", "Beta", "股息率", "主力成本"}
    assert metrics["Beta"]["value"] != "暂无"
    assert metrics["Beta"]["status"] == "ok"
    assert metrics["股息率"]["value"] == "1.00%"
    assert metrics["股息率"]["status"] == "derived"
    assert "按现价推导" in metrics["股息率"]["note"]
    assert any(item["note"].endswith("模型推断") or "模型推断" in item["note"] for item in defense["core_metrics"])
    assert len(defense["capital_trace"]) >= 6
    assert any(item["basis"] == "真实收盘价×成交量推导" for item in defense["capital_trace"])


def test_defense_dashboard_missing_data_uses_empty_labels_not_fake_values():
    snapshot = {
        "score": 48,
        "risk_level": "中",
        "recommendation": "观望",
        "confidence": 40,
        "key_levels": {},
        "risk_alerts": [],
    }

    defense = build_defense_dashboard(snapshot, data=None, benchmark_data=None, extended_info={}, profile={})
    metrics = {item["name"]: item for item in defense["core_metrics"]}
    visible_names = [item["name"] for item in defense["visible_core_metrics"]]
    gaps = {item["name"]: item for item in defense["data_gaps"]}

    assert metrics["PEG"]["value"] == "暂无"
    assert "不编造" in metrics["PEG"]["note"]
    assert metrics["PEG"]["status"] == "missing"
    assert metrics["Beta"]["value"] == "暂无"
    assert metrics["Beta"]["status"] == "missing"
    assert metrics["股息率"]["value"] == "暂无"
    assert metrics["股息率"]["status"] == "missing"
    assert metrics["主力成本"]["value"] == "暂无"
    assert "PEG" not in visible_names
    assert "股息率" not in visible_names
    assert "资金态度" not in visible_names
    assert "PEG" in gaps
    assert "股息率" in gaps
    assert all("模拟" not in str(item) for item in defense["core_metrics"])
    assert all("随机" not in str(item) for item in defense["core_metrics"])


def test_defense_dashboard_keeps_fund_attitude_when_real_flow_exists():
    snapshot = {
        "score": 62,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {},
        "risk_alerts": [],
    }
    extended_info = {"fund_flow": {"main_net_inflow_ratio": 0.71, "main_net_inflow": 987179}}

    defense = build_defense_dashboard(snapshot, data=None, benchmark_data=None, extended_info=extended_info, profile={})
    metrics = {item["name"]: item for item in defense["core_metrics"]}
    visible_names = [item["name"] for item in defense["visible_core_metrics"]]

    assert metrics["资金态度"]["value"] == "+0.71%"
    assert metrics["资金态度"]["status"] == "derived"
    assert "资金态度" in visible_names


def test_defense_dashboard_hides_failed_fund_attitude_but_keeps_gap_reason():
    snapshot = {
        "score": 62,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {},
        "risk_alerts": [],
    }
    extended_info = {
        "fund_flow": {
            "status": "source_failed",
            "source": "东方财富资金流",
            "reason": "远端连接中断",
        }
    }

    defense = build_defense_dashboard(snapshot, data=None, benchmark_data=None, extended_info=extended_info, profile={})
    metrics = {item["name"]: item for item in defense["core_metrics"]}
    visible_names = [item["name"] for item in defense["visible_core_metrics"]]
    gaps = {item["name"]: item for item in defense["data_gaps"]}

    assert metrics["资金态度"]["status"] == "source_failed"
    assert "远端连接中断" in metrics["资金态度"]["note"]
    assert "资金态度" not in visible_names
    assert "资金态度" in gaps


def test_defense_dashboard_distinguishes_source_failure_from_empty_data():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    data = pd.DataFrame({
        "close": [10 + i * 0.05 for i in range(40)],
        "volume": [1000000 for _ in range(40)],
    }, index=dates)
    snapshot = {
        "score": 55,
        "risk_level": "中",
        "recommendation": "观望",
        "confidence": 58,
        "key_levels": {"price": 12.0},
        "risk_alerts": [],
    }
    extended_info = {
        "research": {
            "eps_consensus": {
                "status": "source_empty",
                "source": "同花顺盈利预测",
                "reason": "接口可访问，但未返回可计算EPS字段",
            }
        },
        "dividend": {
            "status": "source_failed",
            "source": "巨潮/新浪分红",
            "reason": "巨潮失败:timeout",
        },
    }

    defense = build_defense_dashboard(snapshot, data, benchmark_data=None, extended_info=extended_info, profile={"pe_ttm": 18})
    metrics = {item["name"]: item for item in defense["core_metrics"]}

    assert metrics["PEG"]["status"] == "source_empty"
    assert "未返回可计算EPS字段" in metrics["PEG"]["note"]
    assert metrics["股息率"]["status"] == "source_failed"
    assert "巨潮/新浪分红失败" in metrics["股息率"]["note"]
    assert metrics["Beta"]["status"] == "source_failed"
    assert metrics["Beta"]["status_label"] == "接口失败"


def test_defense_dashboard_peg_falls_back_to_financial_growth():
    snapshot = {
        "score": 60,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {"price": 12.0},
        "risk_alerts": [],
    }
    extended_info = {
        "financial": {"metrics": {"净利润同比": 30}},
        "research": {"eps_consensus": {"status": "source_empty", "reason": "一致预期暂无"}},
    }
    defense = build_defense_dashboard(
        snapshot,
        data=None,
        benchmark_data=None,
        extended_info=extended_info,
        profile={"pe_ttm": 15},
    )
    metrics = {item["name"]: item for item in defense["core_metrics"]}

    assert metrics["PEG"]["value"] == "0.50"
    assert metrics["PEG"]["status"] == "derived"
    assert "财务摘要净利润同比" in metrics["PEG"]["note"]


def test_defense_dashboard_peg_uses_astock_peg_formula_first():
    snapshot = {
        "score": 60,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {"price": 12.0},
        "risk_alerts": [],
    }
    extended_info = {
        "research": {"eps_consensus": {"values": {"2025预测EPS": 0.8, "2026预测EPS": 1.0}}},
        "financial": {
            "history": [
                {"归母净利润": 100},
                {"归母净利润": 121},
                {"归母净利润": 144},
            ],
            "metrics": {"净利润同比": 30},
        },
    }

    defense = build_defense_dashboard(
        snapshot,
        data=None,
        benchmark_data=None,
        extended_info=extended_info,
        profile={"pe_ttm": 20},
    )
    metrics = {item["name"]: item for item in defense["core_metrics"]}

    assert metrics["PEG"]["value"] == "0.60"
    assert metrics["PEG"]["status"] == "derived"
    assert "前瞻PE=当前价/2026一致预期EPS" in metrics["PEG"]["note"]


def test_defense_dashboard_peg_uses_direct_profile_field_before_deriving():
    snapshot = {
        "score": 60,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {"price": 12.0},
        "risk_alerts": [],
    }

    defense = build_defense_dashboard(
        snapshot,
        data=None,
        benchmark_data=None,
        extended_info={"financial": {"metrics": {"净利润同比": 30}}},
        profile={"pe_ttm": 20, "peg": 0.72},
    )
    metrics = {item["name"]: item for item in defense["core_metrics"]}

    assert metrics["PEG"]["value"] == "0.72"
    assert metrics["PEG"]["status"] == "derived"
    assert "改用基础资料PEG字段" in metrics["PEG"]["note"]


def test_defense_dashboard_peg_uses_financial_growth_aliases_and_history():
    snapshot = {
        "score": 60,
        "risk_level": "中",
        "recommendation": "观察",
        "confidence": 60,
        "key_levels": {"price": 12.0},
        "risk_alerts": [],
    }
    alias_defense = build_defense_dashboard(
        snapshot,
        data=None,
        benchmark_data=None,
        extended_info={"financial": {"metrics": {"归母净利润增长率(%)": 25}}},
        profile={"pe_ttm": 20},
    )
    alias_metrics = {item["name"]: item for item in alias_defense["core_metrics"]}

    history_defense = build_defense_dashboard(
        snapshot,
        data=None,
        benchmark_data=None,
        extended_info={"financial": {"history": [{"归母净利润": 100}, {"归母净利润": 150}]}},
        profile={"pe_ttm": 20},
    )
    history_metrics = {item["name"]: item for item in history_defense["core_metrics"]}

    assert alias_metrics["PEG"]["value"] == "0.80"
    assert "归母净利润增长率" in alias_metrics["PEG"]["note"]
    assert history_metrics["PEG"]["value"] == "0.40"
    assert "近两期归母净利润增速" in history_metrics["PEG"]["note"]


def test_decision_dashboard_trade_plan_css_classes_exist():
    from pathlib import Path

    for class_name in [
        "trade-plan-action",
        "trade-plan-hero",
        "trade-plan-grid",
        "trade-plan-row",
        "risk-control-split",
        "defense-dashboard-layout",
        "defense-summary-card",
        "defense-summary-stats",
        "defense-reason-grid",
        "defense-reason-card",
        "defense-info",
        "capital-trace-empty",
        "defense-top-row",
        "defense-overall",
        "defense-dimension",
        "defense-bottom-grid",
        "signal-state-card",
        "defense-metric-grid",
        "defense-metric-head",
        "source_failed",
        "capital-trace-table",
        "风控防御看板",
        "执行风控 Agent",
    ]:
        if class_name.startswith("风控") or class_name.startswith("执行"):
            assert class_name in Path("ui/decision_dashboard.py").read_text(encoding="utf-8")
        else:
            assert class_name in CUSTOM_CSS


def test_trade_defense_layout_groups_plan_control_and_evidence():
    from pathlib import Path

    source = Path("ui/decision_dashboard.py").read_text(encoding="utf-8")
    section = source.split('st.markdown("#### 交易计划与风控防御")', 1)[1].split('with st.expander("A股决策委员会', 1)[0]

    assert "col_plan, col_control = st.columns([1, 1])" in section
    assert "col_bull, col_bear, col_risk = st.columns(3)" in section
    assert section.index("_render_trade_plan") < section.index("_render_risk_control")


def test_recommend_page_renders_trade_plan_from_recommendation_result():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert 'stock.get("trade_plan")' in source
    assert 'with st.expander("买卖点计划"' in source
    assert '"买入观察区"' in source
    assert '"止损线"' in source


def test_decision_dashboard_has_no_alphaseeker_name():
    from pathlib import Path

    assert "AlphaSeeker" not in Path("ui/decision_dashboard.py").read_text(encoding="utf-8")
    assert "AlphaSeeker" not in CUSTOM_CSS


def test_decision_scores_are_labeled_by_purpose():
    from pathlib import Path

    source = Path("ui/decision_dashboard.py").read_text(encoding="utf-8")

    assert "决策分" in source
    assert "风控分" in source


def test_decision_dashboard_renders_before_profile_sections():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")
    body = source.split("def _render_analysis_results", 1)[1]

    assert body.index("render_decision_dashboard(") < body.index("_render_stock_profile(profile)")


def test_benchmark_data_has_sina_fallback_for_beta():
    from pathlib import Path

    source = Path("ui/cached_data.py").read_text(encoding="utf-8")

    assert "ak.index_zh_a_hist" in source
    assert "ak.stock_zh_index_daily" in source


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
    assert 'extended_info = futures[\'extended_info\'].result(timeout=8.5)' in source
    assert "研报覆盖：" in source
    assert "一致预期：" in source


def test_cached_extended_info_fetches_deep_layers_for_metric_cards():
    from pathlib import Path

    source = Path("ui/cached_data.py").read_text(encoding="utf-8")

    assert "include_deep_layers=True" in source
    assert "timeout_seconds=8" in source


def test_analyze_page_uses_code_name_title_card():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "当前分析标的" in source
    assert "def _render_analysis_target_header" in source
    assert "display_name = stock_name if stock_name and stock_name != symbol else" in source
    assert "st.markdown(f\"**{symbol or '--'}{f' · {display_name}' if display_name else ''}**\")" in source


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


def _analysis_daily_kline_fixture():
    dates = pd.date_range("2026-04-01", periods=45, freq="B")
    closes = [10 + i * 0.03 for i in range(len(dates))]
    return pd.DataFrame(
        {
            "open": [price - 0.02 for price in closes],
            "high": [price + 0.08 for price in closes],
            "low": [price - 0.08 for price in closes],
            "close": closes,
            "volume": [1_000_000 + i * 10_000 for i in range(len(dates))],
        },
        index=dates,
    )


def test_run_stock_analysis_uses_online_daily_kline_before_local_fallback(monkeypatch):
    import ui.analyze_page as analyze_page

    online_data = _analysis_daily_kline_fixture()
    online_data.attrs["data_provider"] = "同花顺"
    online_data.attrs["volume_unit"] = "share"
    fallback_calls = []

    monkeypatch.setattr(analyze_page, "get_cached_stock_info", lambda *args: {"shortName": "测试股份", "symbol": "000001"})
    monkeypatch.setattr(analyze_page, "get_cached_stock_data", lambda *args: online_data.copy())
    monkeypatch.setattr(analyze_page, "get_cached_realtime_quote", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_intraday_data", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_stock_profile", lambda *args: {"name": "测试股份"})
    monkeypatch.setattr(analyze_page, "get_cached_stock_extended_info", lambda *args: {"research_reports": []})

    def fail_if_fallback_is_used(*args):
        fallback_calls.append(args)
        raise AssertionError("online daily kline should be tried before local fallback")

    monkeypatch.setattr(analyze_page, "_load_cached_daily_kline_fallback", fail_if_fallback_is_used)

    result = analyze_page._run_stock_analysis_task("000001", "CN", "1y")

    assert "error" not in result
    assert result["data"].attrs.get("data_provider") == "同花顺"
    assert "source_note" not in result["data"].attrs
    assert fallback_calls == []


def test_run_stock_analysis_falls_back_after_online_daily_kline_failure_and_keeps_auxiliary(monkeypatch):
    import ui.analyze_page as analyze_page

    fallback_data = _analysis_daily_kline_fixture()
    fallback_data.attrs["data_source"] = "本地真实K线缓存"
    fallback_data.attrs["volume_unit"] = "share"
    fallback_data.attrs["source_note"] = "在线日K源暂不可用，当前显示本地最近一次真实前复权日K缓存"
    fallback_calls = []

    def online_failure(*args):
        raise RuntimeError("online source unavailable")

    def fallback(*args):
        fallback_calls.append(args)
        return fallback_data.copy()

    monkeypatch.setattr(analyze_page, "get_cached_stock_info", lambda *args: {"shortName": "测试股份", "symbol": "000001"})
    monkeypatch.setattr(analyze_page, "get_cached_stock_data", online_failure)
    monkeypatch.setattr(analyze_page, "get_cached_realtime_quote", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_intraday_data", lambda *args: None)
    monkeypatch.setattr(analyze_page, "get_cached_stock_profile", lambda *args: {"industry": "测试行业"})
    monkeypatch.setattr(analyze_page, "get_cached_stock_extended_info", lambda *args: {"research_reports": [{"title": "测试研报"}]})
    monkeypatch.setattr(analyze_page, "_load_cached_daily_kline_fallback", fallback)

    result = analyze_page._run_stock_analysis_task("000001", "CN", "1y")

    assert "error" not in result
    assert fallback_calls == [("000001", "CN")]
    assert result["data"].attrs.get("data_source") == "本地真实K线缓存"
    assert result["data"].attrs.get("source_note")
    assert result["profile"] == {"industry": "测试行业"}
    assert result["extended_info"] == {"research_reports": [{"title": "测试研报"}]}


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


def test_analyze_page_uses_qfq_daily_kline_without_realtime_indicator_merge():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "get_cached_stock_data," in source
    assert "stock_data_cache_version(market)" in source
    assert "'qfq' if market == \"CN\" else \"\"" in source
    assert "pd.concat([data, realtime_row])" not in source
    assert "data.loc[idx, 'close'] = quote['price']" not in source
    assert "MA30" in source


def test_cn_stock_data_cache_version_refreshes_by_minute_during_trading(monkeypatch):
    import ui.cached_data as cached_data

    class FakeDateTime:
        @classmethod
        def now(cls):
            from datetime import datetime
            return datetime(2026, 5, 21, 14, 11)

    monkeypatch.setattr(cached_data, "datetime", FakeDateTime)

    assert cached_data.stock_data_cache_version("CN").endswith("202605211411")
    assert cached_data.stock_data_cache_version("US") == cached_data.STOCK_DATA_CACHE_VERSION


def test_cn_stock_data_cache_version_is_stable_for_same_trading_day_after_close(monkeypatch):
    import ui.cached_data as cached_data

    class FakeDateTime:
        current = None

        @classmethod
        def now(cls):
            return cls.current

    from datetime import datetime

    monkeypatch.setattr(cached_data, "datetime", FakeDateTime)

    versions = []
    for current in (
        datetime(2026, 5, 21, 15, 31),
        datetime(2026, 5, 21, 17, 11),
        datetime(2026, 5, 21, 21, 54),
        datetime(2026, 5, 21, 22, 1),
        datetime(2026, 5, 21, 23, 59),
    ):
        FakeDateTime.current = current
        versions.append(cached_data.stock_data_cache_version("CN"))

    assert len(set(versions)) == 1
    assert versions[0].endswith("20260521-closed")


def test_recommend_page_displays_profile_fields():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "def _render_recommendation_profile" in source
    assert "基础资料：" in source
    assert "市值" in source
    assert "PE" in source
    assert "PB" in source
    assert "换手率" in source
    assert "service.ensure_t1_plan_display_profiles(st.session_state.rec_results)" in source


def test_recommend_page_hides_internal_not_requested_status():
    from pathlib import Path

    source = Path("ui/recommend_page.py").read_text(encoding="utf-8")

    assert "not_requested" not in source
    assert 'trigger = metrics.get("trigger") or "--"' not in source
    assert "预热状态" not in source


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
    assert "st.session_state.pending_watchlist_analysis" in source
    assert 'st.session_state.pop("trigger_analysis", None)' in source
    assert 'st.session_state.pending_main_page = "个股分析"' in source
    assert "_open_watchlist_stock_in_main(symbol, market, name)" in source


def test_analyze_page_consumes_watchlist_analysis_once():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert 'pending_watchlist_analysis = st.session_state.pop("pending_watchlist_analysis", None)' in source
    assert 'st.session_state.trigger_analysis = True' in source
    assert 'st.session_state.scroll_to_results = True' in source
    assert 'st.session_state.analyze_market_select = st.session_state.analyze_market' in source
    assert '_clear_analyzed_result()' in source.split('pending_watchlist_analysis = st.session_state.pop("pending_watchlist_analysis", None)', 1)[1].split('pending_quick_match =', 1)[0]


def test_analyze_page_quick_match_has_button_expand_and_direct_selection():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert "def _queue_quick_match_search" in source
    assert "def _queue_quick_match_selection" in source
    assert "def _select_quick_match_target" in source
    assert '"匹配"' in source
    assert "quick_match_show_all" in source
    assert "展开候选" in source
    assert "收起候选" in source
    assert "on_click=_select_quick_match_target" in source
    assert 'args=(item["symbol"], item["name"])' in source
    quick_button_block = source.split('key=f"quick_match_{item[\'symbol\']}"', 1)[1].split("elif quick_query:", 1)[0]
    assert "_select_quick_match_target(item[\"symbol\"], item[\"name\"])" not in quick_button_block
    selection_body = source.split("def _queue_quick_match_selection", 1)[1].split("def _select_quick_match_target", 1)[0]
    assert "st.session_state.pending_quick_match" in selection_body
    assert "st.session_state.analyze_symbol_input = symbol" not in selection_body
    pending_body = source.split('pending_quick_match = st.session_state.pop("pending_quick_match", None)', 1)[1].split("if not pending_watchlist_analysis and not pending_quick_match:", 1)[0]
    assert 'st.session_state.analyze_symbol = pending_quick_match["symbol"]' in pending_body
    assert 'st.session_state.analyze_symbol_input = pending_quick_match["symbol"]' in pending_body
    assert "st.session_state.trigger_analysis = True" in source


def test_analyze_page_quick_match_selection_callback_submits_before_widgets():
    import streamlit as st
    from ui.analyze_page import _select_quick_match_target, _tag_analysis_data

    st.session_state.clear()
    st.session_state.analyze_symbol = "000001"
    st.session_state.analyze_symbol_input = "国发"
    st.session_state.analyze_market = "CN"
    st.session_state.analyze_market_select = "CN"
    st.session_state.quick_stock_query = "国发"
    st.session_state.quick_match_show_all = True
    st.session_state.analyzed_symbol = "000001"
    st.session_state.analyzed_market = "CN"
    st.session_state.analyzed_period = "1y"
    st.session_state.analyzed_target_key = ("000001", "CN", "1y")
    st.session_state.analyzed_data = _tag_analysis_data(pd.DataFrame({"close": [7.1, 7.2]}), "000001", "CN", "1y")

    _select_quick_match_target("600538", "国发股份")

    assert st.session_state.analyze_symbol == "600538"
    assert st.session_state.analyze_symbol_input == "600538"
    assert st.session_state.analyze_market_select == "CN"
    assert st.session_state.quick_stock_query == ""
    assert st.session_state.quick_match_show_all is False
    assert st.session_state.trigger_analysis is True
    assert st.session_state.scroll_to_results is True
    assert st.session_state.quick_match_caption == "已选择：国发股份 (600538)"
    assert "analyzed_data" not in st.session_state


def test_analyze_page_allows_daily_kline_fallback_chain_to_finish():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")
    task_body = source.split("def _run_stock_analysis_task", 1)[1].split("if data is None or data.empty:", 1)[0]

    assert "futures['data'].result(timeout=20)" in task_body
    assert "futures['data'].result(timeout=8)" not in task_body


def test_stock_search_can_return_full_shanghai_match_list():
    result = suggest_stock_inputs("上海", "CN", limit=50)

    assert len(result) > 8
    assert any(item["symbol"] == "002252" for item in result)
    assert any(item["symbol"] == "600009" for item in result)


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
    assert 'with st.form("backtest_form", clear_on_submit=False)' in source
    assert 'st.form_submit_button("开始回测"' in source
    assert "回测标的" in source
    assert "_render_backtest_target_header(symbol, stock_name, market" in source
    assert "BacktestAdapter().save_results(symbol, market, output)" in source


def test_backtest_page_keeps_input_and_result_state_separate():
    from pathlib import Path

    source = Path("backtest_ui.py").read_text(encoding="utf-8")

    assert 'key="bt_symbol_input"' in source
    assert 'value="000001"' not in source
    assert "def _backtest_target_matches_input" in source
    assert "_clear_backtest_result()" in source
    assert "status_loading" in source
    assert "ui.background_tasks" not in source
    assert "_backtest_target_matches_input(current_result, symbol_input, market, period, eval_window)" in source


def test_settings_page_removed_from_app_shell():
    from pathlib import Path

    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "settings_page" not in app_source
    assert "????" not in app_source
    assert not Path("ui/settings_page.py").exists()

def test_market_temperature_fetches_indices_concurrently():
    from pathlib import Path

    source = Path("ui/sidebar.py").read_text(encoding="utf-8")

    assert "ThreadPoolExecutor" in source
    assert "wait(futures, timeout=3)" in source
    assert "executor.shutdown(wait=False, cancel_futures=True)" in source
    assert "executor.submit(quote_service.get_index_realtime, code)" in source


def test_index_realtime_uses_sina_fast_source_first():
    from pathlib import Path

    source = Path("data_fetcher.py").read_text(encoding="utf-8")
    method = source.split("def get_index_realtime(self, symbol):", 1)[1].split("def _get_index_spot", 1)[0]

    assert "def _get_index_realtime_sina" in method
    assert "sina_result = self._get_index_realtime_sina(symbol, timeout=2)" in method
    assert method.index("_get_index_realtime_sina") < method.index("AKSHARE_AVAILABLE")


def test_ai_analysis_ui_is_optional_auxiliary():
    from pathlib import Path

    source = Path("ui/ai_analysis_ui.py").read_text(encoding="utf-8")

    assert "AI 辅助解读（可选）" in source
    assert "主结论以 A股决策委员会 为准" in source
    assert 'with st.expander("展开 AI 辅助解读", expanded=False)' in source


def test_intraday_auto_refresh_is_default_fragment_without_controls():
    from pathlib import Path

    source = Path("ui/analyze_page.py").read_text(encoding="utf-8")

    assert '_streamlit_fragment = getattr(st, "fragment"' in source
    assert '@_streamlit_fragment(run_every="60s")' in source
    assert "def _render_intraday_auto_refresh_fragment" in source
    assert "刷新分时" not in source
    assert "自动刷新" not in source
    assert "_render_intraday_auto_refresh_fragment(symbol, market, quote)" in source
