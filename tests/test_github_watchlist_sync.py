"""GitHub Actions watchlist sync tests."""
import json

import streamlit as st


def test_save_records_disabled_sync_status(tmp_path, monkeypatch):
    temp_file = tmp_path / "watchlist.json"
    monkeypatch.setattr("watchlist._WATCHLIST_FILE", str(temp_file))
    monkeypatch.setattr("config.GITHUB_WATCHLIST_SYNC_ENABLED", False)
    st.session_state.clear()

    from watchlist import add_to_watchlist

    add_to_watchlist("000001", "平安银行", "CN")

    assert st.session_state.watchlist_github_sync["status"] == "disabled"


def test_save_does_not_fail_when_sync_raises(tmp_path, monkeypatch):
    temp_file = tmp_path / "watchlist.json"
    monkeypatch.setattr("watchlist._WATCHLIST_FILE", str(temp_file))
    st.session_state.clear()

    def fail_sync(items):
        raise RuntimeError("boom")

    monkeypatch.setattr("github_watchlist_sync.sync_watchlist_secret", fail_sync)

    from watchlist import add_to_watchlist

    success, _ = add_to_watchlist("000001", "平安银行", "CN")

    saved = json.loads(temp_file.read_text(encoding="utf-8"))
    assert success is True
    assert saved[0]["symbol"] == "000001"
    assert st.session_state.watchlist_github_sync["status"] == "failed"


def test_sync_secret_uses_gh_cli(monkeypatch):
    calls = {}

    monkeypatch.setattr("config.GITHUB_WATCHLIST_SYNC_ENABLED", True)
    monkeypatch.setattr("config.GITHUB_WATCHLIST_SYNC_REPO", "owner/repo")
    monkeypatch.setattr("config.GITHUB_WATCHLIST_SYNC_SECRET", "WATCHLIST_JSON")
    monkeypatch.setattr("config.GITHUB_WATCHLIST_SYNC_TIMEOUT", 15)
    monkeypatch.setattr("github_watchlist_sync.GITHUB_WATCHLIST_SYNC_ENABLED", True)
    monkeypatch.setattr("github_watchlist_sync.GITHUB_WATCHLIST_SYNC_REPO", "owner/repo")
    monkeypatch.setattr("github_watchlist_sync.GITHUB_WATCHLIST_SYNC_SECRET", "WATCHLIST_JSON")
    monkeypatch.setattr("github_watchlist_sync.GITHUB_WATCHLIST_SYNC_TIMEOUT", 15)

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["payload"] = kwargs["input"]
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    from github_watchlist_sync import sync_watchlist_secret

    result = sync_watchlist_secret([
        {"symbol": "600021", "name": "上海电力", "market": "CN"},
    ])

    assert result["status"] == "ok"
    assert calls["cmd"] == ["gh", "secret", "set", "WATCHLIST_JSON", "--repo", "owner/repo"]
    assert "600021" in calls["payload"]
