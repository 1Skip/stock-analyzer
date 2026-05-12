---
name: project state 2026-05-11
description: 优化计划7/7全完成，app.py拆分为8模块，514测试通过
type: project
originSessionId: 35a65abf-4e04-45e9-9335-f14881646c5d
---
## 最新状态（2026-05-11）

优化计划全部 7 项完成，app.py 从 2173 行拆分为 267 行 + 8 个模块。514 测试全部通过。

### 新增功能（5/11）
- **股票名称搜索**：data_fetcher.py 新增 `resolve_stock_input()`，支持中文名称输入（精确/前缀/包含匹配），静态 dict 快查 + AKShare 全量快照 fallback
- **Enter 键搜索**：个股分析页使用 `st.form` 包装搜索框，按回车直接触发分析
- **搜索区域 UI 改版**：主搜索框提升到第一行（视觉焦点），市场/周期/配色/刷新缓存合并到第二行 4 列紧凑布局，placeholder 替代 label，表单去边框，输入框 focus 发光

## 已完成里程碑

- P0 测试补齐：478 tests pass
- P1 调度+通知：scheduler.py + notification.py
- P2 回测引擎：backtest_engine.py + backtest_adapter.py + backtest_ui.py
- P3 多Agent AI：技术+风险+决策三Agent协作
- P4 代码瘦身
- P5 大盘温度
- P6 回测中文国际化
- P7 测试补齐第二轮：478→514 tests
- P8 自选股增强+飞书机器人
- P9 自选股状态分离+mini面板
- P11 K线图迁移Plotly
- UI 苹果极简风 P0 色板统一
- 涨跌幅榜改用新浪JSON API（沪深京全市场含北交所）
- 行业板块排行改用同花顺HTML抓取（替代失效的AKShare）
- 新增概念板块排行（同花顺概念资金流向，客户端排序）
- P0 代码质量修复：提取公共方法消除6处重复代码 + 修信号分类bug
- 优化计划 #1-#7 全部完成（测试隔离/缓存线程安全/XSS/评分合并/AI线程安全/配置坑/依赖CI/拆大文件）

## 当前项目结构

```
app.py              267行  入口+CSS+路由+re-export
ui/cached_data.py    43行  fetcher + 缓存函数
ui/charts.py        285行  K线/RSI/KDJ/BOLL/分时图
ui/ai_analysis_ui.py 237行  AI分析UI
ui/sidebar.py       299行  侧边栏组件
ui/analyze_page.py  553行  个股分析页面
ui/hot_stocks_page.py 186行  热门板块页面
ui/recommend_page.py 156行  智能推荐页面
ui/compare_page.py  134行  股票对比页面
```

### 代码质量改进（5/11）
- P0: README 通知渠道修正（移除未实现的 Telegram/Bark，实际只支持 wechat+feishu）
- P1: `_classify_signal()` 去重 — 从 analyze_page.py + sidebar.py 提取到 chart_utils.py
- P1: 硬编码值统一到 config.py（data_fetcher 的 max_retries/retry_delay/OFFLINE_CACHE_MAX_ENTRIES，cached_data 的 CACHE_TTL_INTRADAY）
- P1: UI 模块添加测试 — tests/test_ui_utils.py（17 tests，classify_signal + _validate_symbol + _format_val）
- P2: 静态股票名称字典 → stock_names.py（~100行数据独立文件）
- P2: 内联 CSS → ui/styles.py（~200行独立样式文件）
- P2: .gitignore 已覆盖缓存文件，无需修改

## 当前项目结构

```
app.py                ~100行  入口 + CSS注入（2行）+ 路由 + re-export
stock_names.py         105行  股票名称静态映射表 + 热门美股列表
chart_utils.py          45行  共享图表工具 + classify_signal
ui/styles.py           207行  CSS样式定义（Apple × Tesla 设计体系）
ui/cached_data.py       44行  fetcher + 缓存函数
ui/charts.py           285行  K线/RSI/KDJ/BOLL/分时图
ui/ai_analysis_ui.py   237行  AI分析UI
ui/sidebar.py           289行  侧边栏组件
ui/analyze_page.py     585行  个股分析页面
ui/hot_stocks_page.py  186行  热门板块页面
ui/recommend_page.py   156行  智能推荐页面
ui/compare_page.py     134行  股票对比页面
tests/test_ui_utils.py   90行  UI工具函数测试（17 tests）
```

## 待做

- 无紧急优化项，项目状态健康
