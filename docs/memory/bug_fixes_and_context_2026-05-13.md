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
