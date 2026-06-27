---
name: stock-analyzer
description: "Use for work in this stock_analyzer repository: project red lines, recommendation/T+1 boundaries, Feishu/GitHub Actions workflows, cache/scheduler checks, real-data validation, memory/README updates, commits, and push requests such as 更新推送."
---

# Stock Analyzer

Use this skill whenever working in this `stock_analyzer` repository.

## First Steps

1. Read `agent.md` before non-trivial code or process changes.
2. Read `docs/memory/MEMORY.md` and the relevant latest memory file when the request refers to prior decisions, red lines, bugs, recommendation behavior, scheduler, Feishu, GitHub Actions, or "更新推送".
3. Prefer `rg` for searching and inspect the actual code path before answering "why", "is it enabled", "has it cached", "has it pushed", or "is it fixed".
4. Answer and commit messages in Chinese for this project.

## Project Red Lines

- Do not use simulated, random, or hand-written fake stock prices, quotes, volumes, turnover, rankings, financials, or recommendation data. Missing real data must be shown as missing, failed, or unavailable.
- Do not change strategy stock pools, filters, scoring, ranking, or selection semantics unless the user explicitly asks for that exact strategy change.
- User-specified strategy conditions, fields, wording, and board lists must be followed literally. Do not add extra conditions such as close-limit, broken-board, message catalyst, or fund inflow unless requested.
- Buy/sell points for recommendation plans are appended after recommendation/T+1 generation as `trade_plan`; they must not participate in stock selection, scoring, ranking, adding, or removing recommendations.
- Recommendation buy/sell points use post-close daily K data, BOLL, MA, support/resistance, ATR/buffer, and risk fields. Do not introduce intraday real-time chase, support-break, or pause-entry recalculation unless the user changes the red line.
- A-share individual analysis indicators, K line, and volume chart must use `1y` qfq daily K data. Real-time quote may be used only for latest-price display, minute chart, or execution check, not merged into daily K indicators.
- Recommendation-page displayed MACD/KDJ/BOLL/MA must reuse the same daily-K indicator口径 as individual analysis; do not special-case one stock.
- For current recommendation UI: short strategy can show `全部, 苹果概念, 特斯拉概念`; aggressive breakthrough and multi-factor steady only show/use `全部` for T+1 plan generation.
- Never commit `.env`, `watchlist.json`, webhook URLs, tokens, API keys, GitHub secrets, or local credentials.

## Verification Discipline

- Do not claim "修好了", "已开启", "已经生效", or "原因是..." from code reading alone. Verify with the relevant command, config, cache, log, process, real data chain, test, or external action first.
- For UI bugs, unit tests alone are not browser-click verification. State clearly whether browser/real-click verification was completed.
- For suspicious results such as zero recommendations, missing push, duplicate scheduler, stale UI state, or cache mismatch, treat as a fault first. Check data sources, cache keys, scheduler/processes, logs, UI session state, and recent diffs before explaining it as normal.
- For scheduler, Feishu, GitHub Actions, or automation work, verify the whole chain: config/env, running process or workflow, cache/log update, and actual push/sync when safe and authorized.
- Say clearly when verification failed, timed out, was skipped, or used fallback/cache because external data sources failed.

## Recommended Checks

Use the project virtual environment when available:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest tests\test_ui_enhancements.py -q
```

Useful focused checks:

- Recommendation/T+1: `tests\test_recommendation_service.py`, `tests\test_t1_plan_push.py`, `tests\test_trade_plan.py`, `tests\test_scheduler.py`
- UI state/navigation: `tests\test_ui_enhancements.py`, `tests\test_app_navigation.py`
- Watchlist/GitHub sync: `tests\test_github_watchlist_sync.py`, `tests\test_json_cache_keys.py`
- Before committing: `git diff --check`, `git status --short`, and inspect staged files.

## Update Push Workflow

When the user says "更新推送", treat it as an explicit request to:

1. Sync this round's completed and verified changes to `docs/memory/`.
2. Update `README.md` for corresponding verified behavior, rules, configuration, or fixes.
3. Ensure secrets and ignored runtime files are not staged.
4. Run appropriate tests or state why they were not run.
5. Stage intended files only.
6. Commit with a concise Chinese message.
7. Push to GitHub `main`.
8. Final response must include commit hash, push result, tests run, and any verification limits.

Do not record suggestions, guesses, unverified ideas, or merely discussed方案 as completed requirements in memory/README.

## Current Project Facts To Preserve

- Core positioning: post-close/pre-open stock selection plus planned execution checks; not intraday full-market real-time selection or high-frequency trading.
- T+1 plan cache is keyed by strategy, sector, and recommendation count. Reading a T+1 cache must not rescan the stock pool.
- "刷新K线缓存" means refreshing recommendation strategy daily-K cache; it is not reading or generating T+1 recommendation plans.
- GitHub Actions cloud watchlist should prefer `WATCHLIST_JSON`; local web watchlist can be synced through `github_watchlist_sync.py` when configured.
- Feishu push testing must avoid PowerShell inline Chinese encoding problems; successful webhook connectivity is not the same as a formal stock-analysis push.
- Windows process lists may show parent/child for `pythonw.exe`; for scheduler duplication, check the actual scheduler lock holder before claiming duplicate or single instance.

## Change Scope

- Keep edits tightly scoped to the user request.
- Do not broadly reformat files, rewrite encoding, or refactor unrelated modules.
- If touching shared UI state, cache keys, strategy logic, notification format, or scheduler, search for related code paths and tests so the same bug is not left elsewhere.
- Work with existing user changes in the tree; do not revert unrelated changes unless explicitly asked.
