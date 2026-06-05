# Bug fixes & context 2026-06-05

## 文档与协作规则

- 已将原 `CLAUDE.md` 内容合并到 `agent.md`，并删除 `CLAUDE.md`；`agent.md` 作为项目红线、架构约定和长期协作规则的正式来源。
- 已同步更新 `.codex/skills/stock-analyzer/SKILL.md`、`README.md` 和 `scripts/check_doc_encoding.py` 中对项目规则文档的引用，Codex Skill 只作为执行 SOP，不替代 `agent.md`。

## 低风险工程优化

- `requirements.txt` 新增 `ruff>=0.8`，用于窄范围语法/高风险静态检查，不引入全量格式化。
- `README.md` 与 `agent.md` 补充快速红线回归命令和验证边界；测试数量文档更新到本轮实际非网络全量结果。
- `ui/system_status_page.py` 新增只读诊断信息，展示调度、T+1 和缓存状态，不触发推荐生成或行情刷新；对应测试已补充。
- `data/cache.py` 增加非行为改变的缓存日志，便于排查缓存命中、写入和过期，不改变缓存语义。
- `agent.md` 明确大型核心文件拆分暂缓，除非有明确 bug 和完整验证支撑。

## 涨跌排行真实数据修复

- 修复港股/美股涨跌排行在 `yfinance` 被限流时返回空的问题。
- 美股排行仍保持 `yfinance` 优先；当 `yfinance` 返回空或限流时，使用新浪财经真实实时行情兜底，不生成模拟数据。
- 港股排行优先读取东方财富港股人气榜确定热门名单；当东方财富批量行情接口不可用时，使用新浪财经真实行情补充价格、涨跌幅、成交量；若东财人气榜不可用，再回退到 `yfinance` 和新浪兜底。
- 实测港股 `hot` 返回 20 条，来源为 `东方财富港股人气榜+新浪行情`；港股涨幅榜/跌幅榜正负号和排序校验通过。
- 实测美股 `hot` 返回 20 条，`gainers` 返回 10 条，`losers` 返回 5 条，来源为新浪财经兜底；涨幅榜/跌幅榜正负号和排序校验通过。

## UI 下拉框结果型验证

- 已用 Playwright 逐页验证可见下拉框能切换，并补充后端结果校验：A 股涨跌排行字段、排序和样本数正确；智能推荐策略与板块选项符合红线；A 股回测不同周期返回不同评估样本和不同统计。
- 港股/美股排行最初结果为空，已按上方真实数据链路修复并复测通过。
- 本轮未点击会触发全市场重算或外部重任务的按钮作为 UI 自动化主流程，例如生成 T+1 推荐计划、开始回测和刷新策略 K 线缓存；相关后端函数和页面入口已做聚焦验证。

## 验证结果

- `.venv\Scripts\python.exe -m pytest tests/ -v -m "not network" --tb=short` 通过：`867 passed, 20 warnings`。
- `.venv\Scripts\python.exe -m pytest tests\test_hot_stocks.py tests\test_hot_stocks_page.py tests\test_stock_recommendation.py::TestGetHotStocksHK tests\test_stock_recommendation.py::TestGetTopGainersLosersHK tests\test_stock_recommendation.py::TestGetHotStocksUS tests\test_stock_recommendation.py::TestGetTopGainersLosersUS -q` 通过：`22 passed`。
- `.venv\Scripts\python.exe -m pytest tests\test_ui_enhancements.py tests\test_app_navigation.py tests\test_quality_monitor.py -q` 通过：`115 passed`。
- `.venv\Scripts\python.exe -m ruff check . --select E9,F63,F7,F82` 通过。
- `.venv\Scripts\python.exe scripts\check_doc_encoding.py` 通过。
- `.venv\Scripts\python.exe scripts\check_unsafe_html_usage.py --max-count 5` 通过，当前保留 5 处已知静态 `unsafe_allow_html` 用法。
- `.venv\Scripts\python.exe scripts\check_real_data_contracts.py` 未带 `--network`，按规则跳过真实联网契约检查；本轮不声称所有外部接口长期在线。
