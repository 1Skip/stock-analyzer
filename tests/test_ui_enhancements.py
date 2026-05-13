"""UI workspace enhancement tests."""

from ui.decision_dashboard import build_decision_snapshot
from ui.compare_page import resolve_compare_inputs
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
