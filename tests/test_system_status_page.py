from pathlib import Path


def test_build_cache_status_rows_formats_files(tmp_path):
    from ui.system_status_page import build_cache_status_rows

    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "sample.json").write_text("{}", encoding="utf-8")

    rows = build_cache_status_rows([cache_dir])

    assert rows[0]["path"].endswith("sample.json")
    assert rows[0]["status"] == "ok"
    assert rows[0]["size"] in {"2 B", "3 B"}
    assert rows[0]["age_minutes"] is not None


def test_build_cache_status_rows_reports_missing_dir(tmp_path):
    from ui.system_status_page import build_cache_status_rows

    rows = build_cache_status_rows([tmp_path / "missing"])

    assert rows == [{
        "path": str(tmp_path / "missing"),
        "status": "missing",
        "size": "--",
        "age_minutes": None,
        "freshness": "missing",
        "diagnosis": "目录不存在：当前未生成该类缓存。",
    }]


def test_summarize_scheduler_failures_collects_sections_and_targets():
    from ui.system_status_page import summarize_scheduler_failures

    failures = summarize_scheduler_failures({
        "daily_report": {"status": "failed", "error": "日报失败"},
        "t1_preheat": {
            "targets": {
                "短线:全部": {"status": "failed", "reason": "接口空"},
                "长线:全部": {"status": "success"},
            }
        },
    })

    assert "daily_report: 日报失败" in failures
    assert "t1_preheat/短线:全部: 接口空" in failures


def test_cache_status_rows_include_human_diagnosis(tmp_path):
    from ui.system_status_page import build_cache_status_rows

    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "scheduler_status.json").write_text("{}", encoding="utf-8")

    rows = build_cache_status_rows([cache_dir])

    assert rows[0]["diagnosis"] == "调度状态缓存：用于判断最近日报/T+1 预热是否运行。"


def test_build_status_diagnostics_reports_missing_and_stale():
    from ui.system_status_page import build_status_diagnostics

    diagnostics = build_status_diagnostics(
        {},
        [
            {"path": ".cache/a.json", "freshness": "stale", "status": "ok"},
            {"path": "reports/history", "status": "missing"},
        ],
    )

    assert any("暂无调度状态文件" in item for item in diagnostics)
    assert any("较旧缓存" in item for item in diagnostics)
    assert any("缓存目录缺失" in item for item in diagnostics)


def test_build_status_diagnostics_reports_t1_failure():
    from ui.system_status_page import build_status_diagnostics

    diagnostics = build_status_diagnostics(
        {"t1_preheat": {"status": "partial_failed", "error": "接口超时"}},
        [],
    )

    assert any("t1_preheat" in item and "接口超时" in item for item in diagnostics)


def test_build_data_source_health_rows_formats_check_result():
    from ui.system_status_page import build_data_source_health_rows

    rows = build_data_source_health_rows({
        "checks": [
            {"name": "历史K线", "status": "ok", "elapsed_ms": 120, "message": "可用"},
            {"name": "实时行情", "status": "empty", "elapsed_ms": 80, "message": "返回为空"},
        ]
    })

    assert rows == [
        {"检测项": "历史K线", "状态": "可用", "耗时(ms)": 120, "说明": "可用"},
        {"检测项": "实时行情", "状态": "返回为空", "耗时(ms)": 80, "说明": "返回为空"},
    ]


def test_render_data_source_health_status_runs_only_after_click(monkeypatch):
    from ui import system_status_page

    result = {
        "status": "ok",
        "checked_at": "2026-07-10T16:30:00",
        "ok_count": 1,
        "total": 1,
        "checks": [{"name": "历史K线", "status": "ok", "elapsed_ms": 100, "message": "可用"}],
    }
    calls = {"runs": 0, "success": [], "dataframe": []}
    system_status_page.st.session_state.pop(system_status_page.DATA_SOURCE_HEALTH_SESSION_KEY, None)
    monkeypatch.setattr(system_status_page.st, "button", lambda *args, **kwargs: True, raising=False)
    monkeypatch.setattr(system_status_page.st, "caption", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(
        system_status_page,
        "run_system_data_source_health_check",
        lambda: calls.update(runs=calls["runs"] + 1) or result,
    )
    monkeypatch.setattr(system_status_page.st, "success", lambda text: calls["success"].append(text), raising=False)
    monkeypatch.setattr(
        system_status_page.st,
        "dataframe",
        lambda rows, **kwargs: calls["dataframe"].append(rows),
        raising=False,
    )

    system_status_page.render_data_source_health_status()

    assert calls["runs"] == 1
    assert calls["success"] == ["数据源检测通过：1/1 项可用"]
    assert calls["dataframe"][0][0]["检测项"] == "历史K线"


def test_render_system_status_page_does_not_run_health_check_without_click(monkeypatch):
    from ui import system_status_page

    calls = {"markdown": [], "caption": [], "dataframe": [], "warning": [], "info": []}
    system_status_page.st.session_state.pop(system_status_page.DATA_SOURCE_HEALTH_SESSION_KEY, None)
    monkeypatch.setattr(system_status_page, "load_scheduler_status", lambda: {"daily_report": {"error": "失败"}})
    monkeypatch.setattr(system_status_page, "render_scheduler_status", lambda status: None)
    monkeypatch.setattr(system_status_page, "build_cache_status_rows", lambda: [{"path": ".cache/a.json", "status": "ok"}])
    monkeypatch.setattr(system_status_page.st, "button", lambda *args, **kwargs: False, raising=False)
    monkeypatch.setattr(system_status_page.st, "markdown", lambda text, **kwargs: calls["markdown"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "caption", lambda text: calls["caption"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "dataframe", lambda rows, **kwargs: calls["dataframe"].append(rows), raising=False)
    monkeypatch.setattr(system_status_page.st, "warning", lambda text: calls["warning"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "info", lambda text: calls["info"].append(text), raising=False)

    system_status_page.render_system_status_page()

    assert any("系统状态" in text for text in calls["markdown"])
    assert any("数据源检测仅在点击按钮后运行" in text for text in calls["caption"])
    assert any("诊断结论" in text for text in calls["info"])
    assert any("失败" in text for text in calls["warning"])
    assert calls["dataframe"] == [[{"path": ".cache/a.json", "status": "ok"}]]


def test_real_data_contract_workflow_has_weekday_schedule():
    source = Path(".github/workflows/real-data-contracts.yml").read_text(encoding="utf-8")

    assert 'cron: "30 8 * * 1-5"' in source
    assert "workflow_dispatch:" in source
