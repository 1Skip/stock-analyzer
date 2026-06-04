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


def test_render_system_status_page_is_read_only(monkeypatch):
    from ui import system_status_page

    calls = {"markdown": [], "caption": [], "dataframe": [], "warning": []}
    monkeypatch.setattr(system_status_page, "load_scheduler_status", lambda: {"daily_report": {"error": "失败"}})
    monkeypatch.setattr(system_status_page, "render_scheduler_status", lambda status: None)
    monkeypatch.setattr(system_status_page, "build_cache_status_rows", lambda: [{"path": ".cache/a.json", "status": "ok"}])
    monkeypatch.setattr(system_status_page.st, "markdown", lambda text, **kwargs: calls["markdown"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "caption", lambda text: calls["caption"].append(text), raising=False)
    monkeypatch.setattr(system_status_page.st, "dataframe", lambda rows, **kwargs: calls["dataframe"].append(rows), raising=False)
    monkeypatch.setattr(system_status_page.st, "warning", lambda text: calls["warning"].append(text), raising=False)

    system_status_page.render_system_status_page()

    assert any("系统状态" in text for text in calls["markdown"])
    assert any("只读诊断页" in text for text in calls["caption"])
    assert any("失败" in text for text in calls["warning"])
    assert calls["dataframe"] == [[{"path": ".cache/a.json", "status": "ok"}]]
