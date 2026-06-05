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


def test_render_system_status_page_is_read_only(monkeypatch):
    from ui import system_status_page

    calls = {"markdown": [], "caption": [], "dataframe": [], "warning": [], "info": []}
    monkeypatch.setattr(system_status_page, "load_scheduler_status", lambda: {"daily_report": {"error": "失败"}})
    monkeypatch.setattr(system_status_page, "render_scheduler_status", lambda status: None)
    monkeypatch.setattr(system_status_page, "build_cache_status_rows", lambda: [{"path": ".cache/a.json", "status": "ok"}])
    monkeypatch.setattr(system_status_page.st, "markdown", lambda text, **kwargs: calls["markdown"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "caption", lambda text: calls["caption"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "dataframe", lambda rows, **kwargs: calls["dataframe"].append(rows), raising=False)
    monkeypatch.setattr(system_status_page.st, "warning", lambda text: calls["warning"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "info", lambda text: calls["info"].append(text), raising=False)

    system_status_page.render_system_status_page()

    assert any("系统状态" in text for text in calls["markdown"])
    assert any("只读诊断页" in text for text in calls["caption"])
    assert any("诊断结论" in text for text in calls["info"])
    assert any("失败" in text for text in calls["warning"])
    assert calls["dataframe"] == [[{"path": ".cache/a.json", "status": "ok"}]]
