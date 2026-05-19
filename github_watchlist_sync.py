"""Sync local watchlist to GitHub Actions secrets."""
import json
import os
import subprocess
from datetime import datetime
from typing import Any

from config import (
    GITHUB_WATCHLIST_SYNC_ENABLED,
    GITHUB_WATCHLIST_SYNC_REPO,
    GITHUB_WATCHLIST_SYNC_SECRET,
    GITHUB_WATCHLIST_SYNC_TIMEOUT,
)


def sync_watchlist_secret(watchlist: list[dict[str, Any]]) -> dict[str, Any]:
    """Overwrite the GitHub Actions WATCHLIST_JSON secret with the local list."""
    if not GITHUB_WATCHLIST_SYNC_ENABLED:
        return _result("disabled", "GitHub watchlist sync is disabled")

    repo = str(GITHUB_WATCHLIST_SYNC_REPO or "").strip()
    if not repo:
        return _result("missing_repo", "GITHUB_WATCHLIST_SYNC_REPO is not configured")

    secret_name = str(GITHUB_WATCHLIST_SYNC_SECRET or "WATCHLIST_JSON").strip() or "WATCHLIST_JSON"
    payload = json.dumps(_normalize_watchlist(watchlist), ensure_ascii=False, indent=2)
    gh_cmd = os.getenv("GITHUB_CLI_PATH", "gh")
    env = os.environ.copy()
    if env.get("GITHUB_TOKEN") and not env.get("GH_TOKEN"):
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]

    try:
        completed = subprocess.run(
            [gh_cmd, "secret", "set", secret_name, "--repo", repo],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(float(GITHUB_WATCHLIST_SYNC_TIMEOUT), 1.0),
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return _result("failed", "GitHub CLI not found")
    except subprocess.TimeoutExpired:
        return _result("failed", "GitHub secret update timed out")
    except Exception as exc:
        return _result("failed", str(exc)[:200])

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        return _result("failed", message[:300] or f"gh exited with {completed.returncode}")

    return {
        "status": "ok",
        "message": f"{secret_name} updated",
        "repo": repo,
        "secret": secret_name,
        "count": len(_normalize_watchlist(watchlist)),
        "synced_at": datetime.now().isoformat(timespec="seconds"),
    }


def _normalize_watchlist(watchlist: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in watchlist or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        market = str(item.get("market") or "CN").strip().upper() or "CN"
        normalized.append({
            "symbol": symbol,
            "name": str(item.get("name") or symbol).strip(),
            "market": market,
        })
    return normalized


def _result(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
    }
