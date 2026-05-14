---
name: bug fixes and context 2026-05-13
description: 对比 daily_stock_analysis 后新增每日 Markdown 分析报告，更新 CLI、README、CLAUDE 与测试
type: project
---

# 2026-05-13 更新记录

## 背景

用户希望对比 `ZhuLinsen/daily_stock_analysis`，并询问“目标那块要怎么做”。结论是不照搬外部仓库完整架构，而是先把它最有价值的“每日分析报告 / 复盘输出”能力接入本项目现有分层服务。

## 本次落地

### 1. 新增每日 Markdown 报告模块

- 新增 `reports/daily_report_service.py`，通过 `DailyReportService` 汇总每日分析数据。
- 新增 `reports/exporter.py`，统一写出日期报告和 `latest.md`。
- 新增 `reports/__init__.py`，标记报告模块。
- 报告内容包含大盘温度、自选股摘要、今日推荐、财务 / 资金 / 新闻摘要、风险提示。

### 2. CLI 新增报告入口

- `main.py` 新增 `--daily-report`，用于生成每日 Markdown 报告。
- `main.py` 新增 `--report-dir`，允许指定报告输出目录，默认 `reports/history`。
- `main.py` 新增 `--no-report-recommendations`，用于跳过推荐股扫描，方便快速验证报告结构。

### 3. Git 忽略运行产物

- `.gitignore` 新增 `reports/history/`，避免把每日生成的本地报告历史提交到仓库。

### 4. 文档更新

- README 增加每日分析报告功能说明、CLI 使用示例、输出路径说明和项目结构说明。
- CLAUDE.md 增加 `reports/` 模块职责、架构约定和常用命令。
- docs memory 新增本记录，并更新 `docs/memory/MEMORY.md` 索引。

### 5. 定时推送接入

- `scheduler.py` 接入 `DailyReportService`，定时任务会生成每日 Markdown 报告。
- `DAILY_REPORT_ENABLED` 控制是否在定时任务中生成日报，默认 `true`。
- `DAILY_REPORT_PUSH_ENABLED` 控制是否把完整 Markdown 日报推送到通知渠道，默认 `true`。
- `DAILY_REPORT_INCLUDE_RECOMMENDATIONS` 控制日报是否扫描推荐股，默认 `false`，避免收盘后定时推送过慢。
- `DAILY_REPORT_DIR` 控制日报输出目录，默认 `reports/history`。
- 定时任务保留原有选股摘要推送，日报生成失败不会阻断原有推送。

### 6. 五项借鉴点继续落地

- 研报层：`AkShareInfoProvider` 新增东财个股研报列表/PDF 链接、同花顺一致预期 EPS。
- 风险事件层：新增龙虎榜统计、限售解禁、近 30 日个股公告。
- 板块归因层：新增行业/概念归属、板块涨跌幅和简单题材原因。
- 日报质量：报告标题升级为“每日股票决策仪表盘”，新增核心结论、决策评分、买卖点、风险警报、操作检查清单。
- GitHub Actions：`.github/workflows/daily_analysis.yml` 启用工作日北京时间 15:30 定时运行，并上传日报 Markdown 产物。

### 7. 测试覆盖

- 新增 `tests/test_daily_report.py`，覆盖 Markdown 渲染、报告导出、依赖注入和跳过推荐股扫描。
- 扩展 `tests/test_scheduler.py`，覆盖日报生成并推送、只生成不推送、关闭日报、日报失败不影响主推送。
- 扩展 `tests/test_data_services.py`，覆盖研报、风险事件、板块归因标准化，以及扩展信息 v2 缓存键。

## 使用方式

```bash
python main.py --daily-report
python main.py --daily-report --report-dir reports/history
python main.py --daily-report --no-report-recommendations
python main.py --schedule
```

生成结果：

- `reports/history/YYYY-MM-DD.md`
- `reports/history/latest.md`

## 注意事项

- 报告模块复用现有真实数据源，不引入模拟行情数据。
- 推荐股扫描依赖全市场数据，网络慢时可能耗时较长；快速验证时建议加 `--no-report-recommendations`。
- 定时日报默认不扫描推荐股，避免收盘后自动推送变慢；如确实需要可设置 `DAILY_REPORT_INCLUDE_RECOMMENDATIONS=true`。
- `reports/history/` 属于运行产物，不提交到 Git。

## 追加记录：UI、推荐推送与数据边界

### 1. Web UI 体验优化

- `app.py` 和 `ui/styles.py` 继续收敛 Apple × Tesla 风格，补充卡片、加载态、导航和页面视觉一致性。
- 新增 `ui/loading.py`，替换业务页面中的 `st.spinner`，统一为自定义加载条/状态卡，减少传统转圈等待感。
- `ui/hot_stocks_page.py` 改为点击后再获取数据，不再进入页面自动请求；并发获取行业、概念、个股涨跌幅榜，单个源失败不拖垮整页。
- `ui/recommend_page.py` 改为点击“生成推荐”后才分析，切换策略/板块/数量会清空旧结果，避免页面延迟显示旧数据。
- `ui/compare_page.py` 接入股票名称/代码解析，股票对比支持输入中文名称或代码。
- 新增 `ui/report_history_page.py`、`ui/settings_page.py`、`ui/stock_search.py`、`ui/decision_dashboard.py`，用于报告历史、设置页、统一搜索和决策仪表盘展示。

### 2. 个股分析与图表改进

- 个股分析页支持更友好的搜索等待态，输入后保留页面结构，不再长时间空白。
- 图表指标补充实时数值显示，MACD/RSI/KDJ/BOLL 折叠区和标识位置继续统一。
- AI 配置区域支持根据 API Key 自动识别模型厂商，减少手动选择下拉框依赖。
- 数据源选择说明改为“A股行情优先源”，强调研报、公告、风险事件等模块会自动调用各自数据源。

### 3. 推荐与推送规则定稿

- 定时推送顺序固定为：自选股摘要 → 四板块推荐 → 每日完整 Markdown 日报。
- 四板块固定为：算力租赁、电力、苹果概念、特斯拉概念。
- 每个板块默认推送短线 2 只 + 长线 1 只，可通过 `SECTOR_PUSH_SHORT_TOP_N` / `SECTOR_PUSH_LONG_TOP_N` 调整。
- 定时推送不再使用 A/HK/US 全市场推荐股作为补充内容。
- 智能推荐和推荐股推送仅包含沪深主板股票，创业板、科创板、北交所不进入推荐池。
- 热门板块页用于市场热度观察：行业板块排行、概念板块排行、个股涨幅榜/跌幅榜全部保留全市场，不做主板过滤。

### 4. 数据源与板块排行

- A股个股涨跌幅榜优先使用同花顺公开页，失败时回退新浪财经。
- 行业/概念板块排行继续使用同花顺公开页，并增加分页/limit 控制，避免无意义多页请求。
- A股基础资料和扩展信息继续通过分层数据服务非阻塞加载，失败时返回空结构，不影响 K 线和技术分析主流程。

### 5. 测试与验证

- 新增/扩展测试覆盖页面导航、加载 UI、热门板块首屏不自动请求、智能推荐主板过滤、热门涨跌幅榜全市场保留、定时推送四板块规则、通知格式顺序等。
- 已验证命令：
  - `py -m compileall stock_recommendation.py ui\hot_stocks_page.py tests\test_stock_recommendation.py`
  - `py -m pytest tests\test_stock_recommendation.py tests\test_hot_stocks_page.py tests\test_scheduler.py tests\test_notification.py -q`

## 追加记录：切换页面残留修复

- 问题现象：从配置推送等页面切换到股票对比时，旧页面内容会以淡化/蒙版形式残留在新页面下方。
- 原因定位：`app.py` 使用同一个 `st.empty()` 页面容器，切页时先写入“正在切换页面...”再在同轮渲染目标页面；Streamlit 前端可能在同一次 rerun 中保留旧块，造成新旧 DOM 短暂并存。
- 修复方式：
  - 移除主页面的 `st.empty()` 双阶段占位渲染。
  - 新增 `_sync_active_page(page)`，检测页面变化后先清理非当前页面的展示态，再调用 `st.rerun()` 并立即 `return`，确保下一轮只挂载目标页面。
  - 新增 `_clear_inactive_page_state(active_page)`，清理个股分析、热门板块、智能推荐等页面的结果缓存展示态，避免跨模块复用旧结果。
- 覆盖测试：
  - `tests/test_app_navigation.py` 新增切页清理、当前页状态保留、同页不 rerun、切页后主函数立即返回等用例。
- 已验证：
  - `py -m pytest tests\test_app_navigation.py tests\test_app_plotly.py tests\test_hot_stocks_page.py tests\test_ui_enhancements.py tests\test_loading_ui.py tests\test_main.py -q`
  - `py -m pytest -q` → 599 passed

## 追加记录：A股名称错序模糊匹配

- 问题现象：股票对比中输入“顺捷科技”提示无法识别，但用户实际想查 A 股“捷顺科技”(002609)。
- 原因定位：A股名称索引只支持精确、前缀、包含匹配；“顺捷科技”和“捷顺科技”属于相邻字顺序颠倒，不满足原有规则。
- 修复方式：
  - `data_fetcher.py` 新增 `_stock_name_similarity()`，对同字符错序的中文简称提高相似度，`resolve_stock_input()` 可返回 `002609 · 捷顺科技`。
  - `ui/stock_search.py` 快速匹配同样支持同字错序，并让这类候选优先于普通包含匹配。
  - `ui/compare_page.py` 对无法识别的名称给出更明确提示，提醒检查错字/顺序，也可直接输入 6 位代码。
- 已验证：
  - `StockDataFetcher().resolve_stock_input("顺捷科技", "CN") == ("002609", "捷顺科技")`
  - `suggest_stock_inputs("顺捷科技", "CN", 3)` 首位返回 `002609 · 捷顺科技`
  - `py -m pytest tests\test_data_fetcher.py tests\test_ui_enhancements.py tests\test_app_navigation.py -q` → 88 passed

## 追加记录：智能推荐切到股票对比仍残留旧页面
- 问题现象：从“智能推荐”切换到“股票对比”后，股票对比已显示在顶部，但页面底部仍能看到淡化后的智能推荐结果。
- 原因定位：这是 Streamlit rerun 期间的前端 stale DOM 占位现象，旧页面长列表在新脚本尚未完全结束时会被淡化保留；应用侧慢侧边栏刷新会拉长这个窗口，让残影更明显。
- 修复方式：
  - `app.py` 新增 `_render_main_page(page)`，用稳定的 `st.empty()` 主内容占位容器承载每个业务页面，切页时先替换主内容区域。
  - `_sync_active_page(page)` 在切页时写入 `_page_switch_pending` 标记；目标页首轮渲染完成后立即返回，跳过大盘温度、自选股摘要、数据源说明等较慢侧边栏刷新，避免旧 DOM 拖尾。
  - 保留原有 `_clear_inactive_page_state(active_page)`，继续清理个股分析、热门板块、智能推荐等页面结果态，避免旧业务数据跨页面复用。
- 覆盖测试：
  - `tests/test_app_navigation.py` 新增主页面稳定容器测试。
  - `tests/test_app_navigation.py` 新增切页后第二轮跳过慢侧边栏测试。
- 已验证：
  - `py -m compileall app.py tests\test_app_navigation.py`
  - `py -m pytest tests\test_app_navigation.py -q` → 10 passed
  - `py -m pytest tests\test_app_navigation.py tests\test_hot_stocks_page.py tests\test_ui_enhancements.py tests\test_loading_ui.py -q` → 23 passed

## 追加记录：股票对比价格走势信息增强
- 问题现象：股票对比页的“价格走势对比”只有标准化价格线，能看出谁涨跌更多，但缺少回撤、波动、胜率、趋势和相对强弱等决策信息。
- 修复方式：
  - `ui/compare_page.py` 新增 `build_trend_metrics()`，计算近 20/60/120 日/1 年收益、最大回撤、年化波动率、上涨天数占比、近 20 日趋势斜率和 MA20/MA60 状态。
  - 新增 `build_compare_insights()`，输出“近20日最强、趋势斜率最强、波动最低、回撤最小”等结论卡片。
  - 新增 `build_trend_dashboard_figure()`，把图表升级为三层：标准化价格、区间回撤、相对第一只股票的强弱差。
  - README 和 CLAUDE 同步更新股票对比功能说明。
- 覆盖测试：
  - `tests/test_ui_enhancements.py` 新增走势指标、结论卡片和三层图表结构测试。
- 已验证：
  - `py -m compileall ui\compare_page.py tests\test_ui_enhancements.py`
  - `py -m pytest tests\test_ui_enhancements.py tests\test_app_navigation.py -q` → 21 passed

## 追加记录：Windows 一键启动与开机自启
- 目标：用户希望自己打开电脑就能直接使用；别人下载项目后也能尽量双击启动。
- 落地方式：
  - `start.bat` 作为英文/ASCII 主入口，避免 Windows cmd 编码导致中文批处理内容被误解析。
  - `启动.bat` 和 `股票分析系统.bat` 保留为中文入口，但只转发到 `start.bat`。
  - `start.bat` 自动检测 `py -3` / `python`，自动创建 `.venv`，自动安装 `requirements.txt`，启动 Streamlit 并打开 `http://localhost:8501`。
  - `创建桌面快捷方式.vbs` 改为使用脚本所在目录，不再硬编码本机路径。
  - 新增 `install_startup.bat` / `uninstall_startup.bat`，通过 Windows 启动文件夹快捷方式启用/取消登录后自动启动。
  - 新增 `docs/WINDOWS_QUICK_START.md`，说明自用开机即用、别人下载即用、依赖安装慢、端口占用等常见问题。
- 注意：
  - 脚本不写入 token、webhook、API key。
  - 开机自启只是本机 Windows 登录后启动 Web 服务；若要电脑关机也能定时推送，应使用 GitHub Actions/服务器方案。
- 已验证：
  - 检查脚本无项目绝对路径硬编码。
  - `py -m pytest tests\test_ui_enhancements.py tests\test_app_navigation.py tests\test_loading_ui.py -q` → 23 passed

## 追加记录：飞书对话机器人中文股票名称识别
- 目标：为后续飞书实时对话 Agent 补强股票名称识别，避免只能输入股票代码。
- 落地方式：
  - `api_server.py` 新增 `_parse_analysis_command()`，支持 `/analysis 贵州茅台`、`分析贵州茅台`、`查询 招商银行`、`查 招商银行` 等自然语言格式。
  - `api_server.py` 新增 `_resolve_analysis_target()`，复用 `StockDataFetcher.resolve_stock_input()` 的 A 股全量名称索引和错序/模糊匹配能力。
  - A 股中文名称解析失败时不再直接请求行情接口，避免把“帮帮我”等普通文本误当股票代码查询。
  - 飞书回复会在分析正文前补充“已识别：名称(代码)”。
  - README 和 CLAUDE 同步更新飞书机器人支持中文名称输入说明。
- 覆盖测试：
  - `tests/test_api_server.py` 新增 `/analysis <中文名>`、`分析<中文名>`、`查 <中文名>` 用例。
- 已验证：
  - `py -m compileall api_server.py tests\test_api_server.py`
  - `py -m pytest tests\test_api_server.py -q` → 16 passed
  - `py -m pytest tests\test_data_fetcher.py::TestGetStockName tests\test_ui_enhancements.py -q` → 14 passed

## 追加记录：GitHub Actions + 飞书 Webhook 云端推送
- 目标：电脑关机后仍能在工作日收盘后自动推送飞书日报。
- 落地方式：
  - `.github/workflows/daily_analysis.yml` 改为飞书每日股票分析推送工作流，工作日北京时间 15:30 自动运行，仍支持手动 `workflow_dispatch`。
  - workflow 默认设置 `NOTIFY_CHANNELS=feishu`，仓库只需要配置 `FEISHU_WEBHOOK_URL` Secret，减少误配。
  - 新增 Secret 自检步骤，未配置 `FEISHU_WEBHOOK_URL` 时在 Actions 日志中明确报错。
  - 新增 `docs/FEISHU_GITHUB_ACTIONS.md`，说明飞书机器人 Webhook、GitHub Secrets、手动测试、推送内容和常见问题。
  - README 和 CLAUDE 同步更新云端飞书推送说明。
- 推送内容：
  - 自选股摘要 → 四板块推荐（算力租赁、电力、苹果概念、特斯拉概念）→ 每日完整 Markdown 决策日报。
- 注意：
  - 这是主动推送方案，不是飞书实时对话；实时对话仍需要事件订阅和公网回调服务。

## 追加记录：GitHub Actions 支持 WATCHLIST_JSON 自选股 Secret
- 问题现象：云端飞书日报中“自选股决策面板、研报/风险/板块归因”显示暂无，因为 GitHub Actions 不能读取用户本地未提交的 `watchlist.json`。
- 落地方式：
  - `.github/workflows/daily_analysis.yml` 新增“写入自选股 Secret”步骤。
  - 如果配置 `WATCHLIST_JSON`，Actions 会校验 JSON 数组格式，标准化 `symbol/name/market` 字段，并在运行时写入 `watchlist.json`。
  - 如果未配置 `WATCHLIST_JSON`，Actions 会写入空数组并提示“本次日报自选股为空”。
  - `docs/FEISHU_GITHUB_ACTIONS.md` 新增 `WATCHLIST_JSON` 示例和说明。
  - README/CLAUDE 同步注明云端自选股需要 `WATCHLIST_JSON`。
- 推荐格式：
  - `[{"symbol":"600519","name":"贵州茅台","market":"CN"},{"symbol":"600036","name":"招商银行","market":"CN"}]`

## 追加记录：GitHub Actions 兼容 STOCK_LIST 简单自选股配置
- 背景：用户提到 `daily_stock_analysis` 使用 `STOCK_LIST=600519,hk00700,AAPL` 更简单，本项目不应强制用户写复杂 JSON。
- 落地方式：
  - `.github/workflows/daily_analysis.yml` 的“写入自选股 Secret”步骤新增 `STOCK_LIST` 支持。
  - 优先级：`WATCHLIST_JSON` > `STOCK_LIST` > 空自选股。
  - `STOCK_LIST` 支持逗号/中文逗号/换行分隔。
  - A 股支持代码或中文名称，例如 `600519,贵州茅台,招商银行`，运行时复用 `StockDataFetcher.resolve_stock_input()` 自动补全代码和名称。
  - 支持市场前缀：`CN:平安银行`、`HK:00700`、`US:AAPL`，也兼容 `HK00700`、`USAAPL`。
  - `docs/FEISHU_GITHUB_ACTIONS.md`、README、CLAUDE 同步改为推荐 `STOCK_LIST`，`WATCHLIST_JSON` 保留为高级格式。

## 追加记录：GitHub Actions STOCK_LIST 中文名离线兜底
- 问题现象：Actions 中配置 `STOCK_LIST=捷顺科技,瑞鹄模具,上海电力` 后，日志显示“未找到股票 捷顺科技 的数据”。
- 原因定位：云端运行时中文名称解析依赖现场 AKShare 名称索引刷新；当接口连接中断或超时时，`STOCK_LIST` 解析 fallback 会把中文名称原样写入 `watchlist.json`，后续行情查询就拿 `捷顺科技` 当 symbol 请求。
- 修复方式：
  - 新增 `data/static/stock_name_index.json`，随仓库提交 5515 只 A 股名称索引，作为 GitHub Actions/离线环境兜底。
  - `data_fetcher.py` 在运行缓存和 AKShare 刷新失败后读取内置索引，再退回精简静态表。
  - `.github/workflows/daily_analysis.yml` 对未识别的 A 股中文名称直接 `::error::` 失败，提示改用 6 位代码，避免继续误查。
  - README、CLAUDE、飞书 Actions 文档同步说明 `STOCK_LIST` 支持中文名但代码最稳。
- 已验证：
  - `StockDataFetcher().resolve_stock_input("捷顺科技", "CN") == ("002609", "捷顺科技")`
  - `StockDataFetcher().resolve_stock_input("瑞鹄模具", "CN") == ("002997", "瑞鹄模具")`
  - `StockDataFetcher().resolve_stock_input("上海电力", "CN") == ("600021", "上海电力")`
  - `py -m pytest tests\test_data_fetcher.py::TestResolveStockInput -q` → 4 passed

## ?????TradingAgents ?????? 1 ? A??????
- ????? TradingAgents ?????????????? A ?????????????? LLM ?????? GitHub Actions/???????
- ?????
  - ?? `decision_committee.py`????? A ?????????????????????????????????????????????
  - ?? Agent ???????? Agent????? Agent???? Agent????? Agent????? Agent?
  - `ui/decision_dashboard.py` ???? Agent ???????????????Agent ???????
  - `reports/daily_report_service.py` ???????????????/????????????????????????? Agent ???
- ??????? 1 ????? LLM???????????????????? 4 ????????????????? Agent?
- ?????
  - `tests/test_decision_committee.py` ???? Agent ??????????
  - `tests/test_daily_report.py` ????? A?????????

## ?????A???????? 1 ?????
- ?????? 1 ? Lite ???????????????? Agent ???????????????????????? A ????????
- ?????
  - `decision_committee.py` ?? `AGENT_WEIGHTS`??? Agent ???? 100??? 30??? 20???? 20??? 15??? 15?
  - ?? Agent ?? `raw_score`?`score_delta`?`confidence`?`evidence`?`warnings`????????? `confidence` ? `key_levels`?
  - ?????? MA20/MA60?BOLL ??/?????
  - ??????????????????5???????????????????
  - ???????????????????EPS?PE?PB??????????????
  - ??????????????????????
  - ?????? ST/????????????????????????????
  - ????????????????? Agent ????????????
  - ??????????????????????????? Agent ???
- ????
  - `py -m pytest tests\test_decision_committee.py -q` ? 2 passed
  - `py -m pytest tests\test_daily_report.py tests\test_ui_enhancements.py tests\test_scheduler.py tests\test_notification.py -q` ? 62 passed

## 追加记录：TradingAgents 借鉴阶段 2 - 个股页决策仪表盘最终版
- 目标：把阶段 1 的五层 Agent 结论从“简单卡片”升级为个股页可直接使用的决策仪表盘，降低用户看结果时的信息跳跃感。
- 修改内容：
  - `ui/decision_dashboard.py` 重构为综合评分 Hero + 买卖点/仓位 + 关键价位 + 催化因素 + 看多/看空/风险三栏 + 五层 Agent 折叠明细。
  - Agent 明细展示 `stance`、`score_delta`、`raw_score`、`weight`、`confidence`、`evidence`、`warnings`，方便追溯每一层为何加分或扣分。
  - `ui/styles.py` 新增 `decision-hero`、`decision-score-ring`、`decision-panel`、`decision-chip`、`decision-level-row`、`agent-card-grid`、`agent-score-pill` 等样式，统一 Apple/Tesla 卡片风格并避免内容重叠。
  - `tests/test_ui_enhancements.py` 补充阶段 2 字段和 CSS 类保护，确保后续改 UI 不丢关键展示结构。
  - README 和 CLAUDE 同步记录阶段 2 最终版状态。
- 验证：
  - `py -m compileall ui\decision_dashboard.py ui\styles.py tests\test_ui_enhancements.py`
  - `py -m pytest tests\test_ui_enhancements.py tests\test_decision_committee.py -q` → 15 passed

## 追加记录：TradingAgents 借鉴阶段 3/4/5 最终版
- 阶段 3（日报/飞书决策仪表盘）：
  - `reports/daily_report_service.py` 在 `build_report_data()` 阶段生成并复用 `decisions`，日报自选股区升级为“决策仪表盘”结构。
  - 自选股日报输出评分、行动、仓位、风险、置信度、价格状态、买卖点、关键价位、催化因素、看多依据和风险警报。
- 阶段 4（外部 LLM 多空辩论）：
  - `ai_analysis.py` 新增 `build_debate_snapshot()` 和 `run_debate_analysis()`。
  - 三角色为多头研究员、空头研究员、风控经理；输入复用五层 Agent 结论、扩展信息、资金/研报/风险/板块数据。
  - `AI_DEBATE_ENABLED=false` 或未配置 `AI_API_KEY` 时自动跳过，不影响本地、飞书和 GitHub Actions。
- 阶段 5（GitHub Actions 云端闭环）：
  - `.github/workflows/daily_analysis.yml` 增加 `AI_MODEL`、`AI_BASE_URL`、`AI_DEBATE_ENABLED`、`AI_DEBATE_MAX_SYMBOLS` 云端配置。
  - `notification.py` 新增飞书 Markdown 长文本拆分，降低完整日报卡片过长导致推送失败概率。
  - README、CLAUDE、`docs/FEISHU_GITHUB_ACTIONS.md` 同步说明 LLM 辩论配置和最终推送内容。
- 验证：
  - `py -m pytest tests\test_ai_analysis.py tests\test_daily_report.py tests\test_notification.py -q` → 82 passed

## 追加记录：网页端展示阶段 1-5 状态卡片
- 背景：阶段 3-5 主要影响日报、飞书和 GitHub Actions，用户在网页端不容易看出变化。
- 修改内容：
  - 新增 `ui/committee_status.py`，构建轻量状态数据并渲染侧边栏“ A股决策委员会 ”状态卡片。
  - `app.py` 在功能菜单下固定展示该卡片，所有页面都能看到阶段 1-5、飞书、Actions 和 LLM 辩论开关状态。
  - `ui/styles.py` 新增 `committee-status-card`、`committee-stage-row` 等样式，保持 Apple/Tesla 卡片风格。
  - README、CLAUDE 同步说明该状态卡片。
- 验证：
  - `tests/test_app_navigation.py` 覆盖状态卡片接入、五阶段数量和 CSS 类。



## 追加记录：个股页新闻时间与 AI 辅助解读定位
- 背景：个股页“财务 / 资金 / 新闻”只展示财务报告期和资金流日期，新闻区域没有清晰的最新时间；同时决策委员会上线后，原“AI 智能解读”容易被误解为主决策入口。
- 修改内容：
  - `ui/analyze_page.py` 新增 `_latest_news_date()`，新闻有数据时显示“新闻最新：时间”，无新闻时显示“新闻最新：暂无（当前数据源未返回该股相关新闻）”。
  - `ui/ai_analysis_ui.py` 将“AI 智能解读”改为“AI 辅助解读（可选）”，默认折叠，并明确“主结论以 A股决策委员会 为准，AI 仅用于解释和补充”。
  - README、CLAUDE 同步说明财务/资金/新闻状态与 AI 辅助解读定位。
- 验证：
  - `tests/test_ui_enhancements.py` 新增新闻最新时间和 AI 可选辅助定位的源码保护测试。
