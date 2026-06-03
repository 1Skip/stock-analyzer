# Bug fixes & context 2026-06-03

## 风控防御看板降噪与说明

- 个股分析页“风控防御看板”重排为“一屏主结论 + 主要风险 / 观察项 / 支撑项 + 五维评分 + 资金博弈溯源 + 指标卡片”的展示结构，让用户先看到当前状态、风险等级、仓位建议和确认位。
- 核心指标卡片增加内嵌展开说明，说明每个指标的作用、怎么看和当前解读；原悬浮提示不再使用，避免遮挡其它指标或内容。
- PEG、股息率、资金态度、Beta 等指标遵循“有真实值或可推导值才进入主指标区”的规则；当前股票本次接口未返回可用字段时，不再在主看板反复显示“暂无/缺失”。
- 缺失原因不丢弃：接口失败、源无数据、字段不足等信息保留到数据质量/风险提示区和 `data_gaps`，用于排查数据源状态，不抢主结论。
- 资金博弈溯源表只展示本次有可用数值的行；资金流接口本次没有返回可用数值时，显示轻量空状态，不再展示一排“暂无”。

## 扩展信息数据链路修复

- 个股扩展信息缓存层改为请求深层数据，并把页面等待时间从 `2.5s` 提高到 `8.5s`，缓存服务调用 provider 时传入 `timeout_seconds=8`，减少 EPS、分红、研报、资金流等明明能取却未及时展示的情况。
- `AkShareInfoProvider.get_stock_extended_info()` 改为按完成顺序收集并发结果，避免慢接口阻塞已完成的财务、资金或新闻层。
- 资金流规范化会过滤没有任何主力净流入、主力净占比、超大/大单或近 5 日主力净流入数值的空快照，避免把空壳数据当成可用资金流。
- 扩展信息缓存 schema 升到 `v6`；空的研报、分红、板块归因等可选层不再长期写入可选层缓存，避免后续真实数据被空结果污染。
- 数据质量摘要能区分资金流缺失、资金流接口失败和资金流源无数据；资金态度指标本身也能区分 `source_failed` / `source_empty`，而不是统一写“暂无”。

## 真实数据排查结论

- 多股票抽样验证：资金态度和主力净流入不是不可用指标，`002541`、`600519` 能返回主力净流入、主力净占比和近 5 日主力净流入；`000001`、`002609`、`300750` 在同轮抽样中出现资金源失败或快照空返回，属于外部源波动/个股源返回差异。
- 分红/股息率在抽样股票中可返回真实历史分红字段；股息率保留为有值展示、无值降噪，不做一刀切删除。
- 页面实测中资金流有值时，风控防御看板仍展示资金态度、资金博弈溯源和主力净流入；无值时隐藏主卡片并保留数据缺口说明。

## Streamlit 警告清理

- 全项目将 `use_container_width=True` 替换为当前 Streamlit 推荐的 `width="stretch"`，覆盖按钮、表格、Plotly 图表、下载按钮和回测提交按钮。
- 个股页市场、周期、配色 selectbox 改为先初始化对应 widget key，再由 `st.selectbox(key=...)` 承载当前值，不再同时传 `index=` 和写同一个 widget key，消除 `analyze_period_select` 类 session_state 警告。

## 验证结果

- `py -m pytest tests\test_data_services.py tests\test_ui_enhancements.py tests\test_quality_monitor.py -q` -> `157 passed`。
- `py -m pytest tests\test_ui_enhancements.py tests\test_app_navigation.py -q` -> `103 passed`。
- `py -m py_compile backtest_ui.py ui\sidebar.py ui\report_history_page.py ui\recommend_page.py ui\hot_stocks_page.py ui\compare_page.py ui\analyze_page.py tests\test_ui_enhancements.py` 通过。
- `py -m py_compile ui\decision_dashboard.py ui\styles.py data\providers\akshare_info_provider.py data\services\info_service.py ui\cached_data.py ui\analyze_page.py quality_monitor.py` 通过。
- `git diff --check` 通过。
- 本地 Streamlit `http://localhost:8502` 首屏和风控防御看板浏览器实测正常；终端未再出现 `use_container_width` 或 `analyze_period_select` 警告。测试后服务已停止，8502 端口仅剩 `TimeWait`。
