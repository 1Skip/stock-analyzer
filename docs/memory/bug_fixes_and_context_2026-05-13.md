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

### 6. 测试覆盖

- 新增 `tests/test_daily_report.py`，覆盖 Markdown 渲染、报告导出、依赖注入和跳过推荐股扫描。
- 扩展 `tests/test_scheduler.py`，覆盖日报生成并推送、只生成不推送、关闭日报、日报失败不影响主推送。

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
