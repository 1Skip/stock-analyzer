# 2026-06-19 更新记录

## 短线推荐增强

- 按用户确认，将智能推荐「短线」策略从纯技术评分增强为技术打底 + 基本面、财报、资金流、消息面、热门板块共同参与评分。
- 原短线技术项仍保留：MACD、RSI、KDJ、BOLL、MA5/MA10 和适中波动率；新增上下文项会以加减分方式进入最终 `score`。
- 新增短线上下文评分字段：`基本面/估值可用`、`财报/盈利确认`、`资金流确认`、`消息面催化`、`热门板块`、`风险公告过滤` 和 `适中波动`，写入 `strategy_checks` / `strategy_details` 供页面解释。
- 推荐页「策略命中」展示补齐上述短线增强依据，用户重新生成短线推荐后可看到“为什么这只短线被推荐”。
- 激进突破型、多因子稳健型、T+1 买卖点生成逻辑未改；已跑策略边界测试确认未破坏既有策略合约。

## 验证

- `py -m pytest tests\test_stock_recommendation.py::TestAnalyzeShortTerm -q` -> `6 passed`
- `py -m pytest tests\test_recommendation_service.py -q` -> `30 passed`
- `py -m pytest tests\test_recommendation_strategy_contracts.py tests\test_trade_plan.py -q` -> `6 passed`
- `py -m pytest tests\test_ui_enhancements.py::test_recommend_page_displays_enhanced_short_term_factors tests\test_ui_enhancements.py::test_recommend_page_renders_trade_plan_from_recommendation_result -q` -> `2 passed`
