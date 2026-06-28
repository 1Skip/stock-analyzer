# 2026-06-28 智能推荐实盘成交结果记录

## 手工实盘结果录入

- 智能推荐页新增“录入推荐股实际买卖结果”，输入股票代码或名称后可点击搜索或按 Enter 搜索。
- 搜索会先匹配当前 T+1 推荐计划和历史 T+1 推荐计划；如果股票可通过名称/代码识别但不在推荐历史中，也允许保存为“手工补录 / 手工录入”。
- 录入字段保留买入时间、买入价位、卖出时间、卖出价位，以及“还在持有，暂不填写卖出时间和卖出价”勾选项。
- 买入价和卖出价按两位小数保存；勾选继续持有时卖出时间和卖出价不参与校验，持有中记录不进入成功率分母。
- 手工成交记录保存到 `.cache/recommendation_manual_trade_records.json`，与 T+1 推荐计划历史分开。

## 成功率与删除

- 推荐页新增“手工成交成功率”区块，展示已记录、成功率、平均收益、已结/持有、按策略/板块汇总和最近记录明细。
- 成功率只统计已卖出的闭合记录；继续持有的记录只计入总记录和持有数。
- 页面新增“删除手工成交记录”入口，录错记录可以直接删除，不需要手动改缓存文件。
- 手工实盘样本达到总已结 `30` 条且当前策略/板块已结 `12` 条时，只提示可以评估接入实盘反馈学习层；默认阈值由 `MANUAL_TRADE_LEARNING_MIN_CLOSED` 和 `MANUAL_TRADE_LEARNING_MIN_STRATEGY_CLOSED` 控制。
- 该提醒不会自动改变股票池、过滤条件、评分、排序或推荐数量。

## 推荐页入口整理

- 页面移除“回看计划表现”“统计历史计划”“刷新最近交易日复盘”三个旧入口；旧按钮对应的后端只读评估能力仍保留，避免影响短线闭环学习链路。
- 推荐页操作按钮调整为同一行三列：“生成 T+1 推荐计划 / 检查当前是否适合入场 / 刷新K线缓存”，主按钮在左且保持 primary，辅助按钮依次靠后。
- 三列比例为 `[2.0, 1.7, 1.4]`，避免辅助按钮抢主流程，也避免右侧出现大块空白。

## 验证

- `.venv\Scripts\python.exe -m pytest tests\test_ui_enhancements.py tests\test_recommendation_service.py -q --basetemp=.tmp\pytest-remove-strategy-review` 通过，`144 passed`。
- `.venv\Scripts\python.exe -m pytest tests\test_ui_enhancements.py -q --basetemp=.tmp\pytest-button-gap` 通过，`106 passed`。
- `.venv\Scripts\python.exe -m compileall ui\recommend_page.py recommendation_service.py quality_monitor.py data\cache.py` 通过。
- `git diff --check` 通过，仅有 Windows 换行提示。
