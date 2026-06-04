import json


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_scheduler_status_handles_missing_file(tmp_path):
    from ui.scheduler_status import load_scheduler_status

    assert load_scheduler_status(tmp_path / "missing.json") == {}


def test_load_scheduler_status_reads_json(tmp_path):
    from ui.scheduler_status import load_scheduler_status

    path = tmp_path / "scheduler_status.json"
    path.write_text(json.dumps({"t1_preheat": {"status": "success"}}), encoding="utf-8")

    assert load_scheduler_status(path)["t1_preheat"]["status"] == "success"


def test_render_scheduler_status_is_read_only(monkeypatch):
    from ui import scheduler_status

    calls = {"caption": [], "dataframe": []}
    monkeypatch.setattr(scheduler_status.st, "expander", lambda *args, **kwargs: _Context(), raising=False)
    monkeypatch.setattr(scheduler_status.st, "caption", lambda text: calls["caption"].append(text), raising=False)
    monkeypatch.setattr(
        scheduler_status.st,
        "dataframe",
        lambda rows, **kwargs: calls["dataframe"].append((rows, kwargs)),
        raising=False,
    )

    scheduler_status.render_scheduler_status({
        "t1_preheat": {
            "status": "success",
            "started_at": "2026-06-04T15:45:00",
            "finished_at": "2026-06-04T15:45:12",
            "success_count": 1,
            "failed_count": 0,
            "targets": {
                "短线:全部": {
                    "status": "success",
                    "recommended_count": 2,
                    "elapsed_seconds": 1.2,
                    "cache_key": "t1:short:all:5",
                }
            },
        }
    })

    assert any("T+1 最近状态" in text for text in calls["caption"])
    assert calls["dataframe"][0][0][0]["目标"] == "短线:全部"
    assert calls["dataframe"][0][0][0]["命中数"] == 2
