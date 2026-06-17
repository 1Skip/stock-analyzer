# 智能推荐拆分护栏

这个目录用于后续把 `stock_recommendation.py` 按职责逐步拆开。

当前红线：

- 不改变短线、激进突破型、多因子稳健型的股票池、过滤条件、评分、排序和推荐数量语义。
- 不把实时行情引入原始选股、评分或排序。
- 不改变 T+1 计划缓存 key、读取边界或 `trade_plan` 追加边界。
- 每次搬迁只允许做机械移动和导入改写，并用现有推荐测试验证结果不变。

建议拆分顺序：

1. `market_rankings.py`：热门榜、涨跌幅榜、行业/概念板块排行。
2. `strategy_cache.py`：策略 K 线缓存、刷新、交易日 key。
3. `strategy_pool.py`：股票池和板块池辅助函数。
4. `breakout_strategy.py`：激进突破型内部实现。
5. `multi_factor_strategy.py`：多因子稳健型内部实现。

正式拆分前，先补同一 mock 数据下的改前/改后推荐结果对比测试。
## Refactor Gate

当前已增加 `tests/test_recommendation_strategy_contracts.py` 作为拆分前护栏：

- 短线：锁定股票池入口、分析调用、按 `score` 降序输出和返回字段形状。
- 激进突破型：锁定策略池入口、诊断字段和 `_run_aggressive_breakout_pool` 调用边界。
- 多因子稳健型：锁定策略池、轻筛 shortlist、深度检查池和诊断字段边界。

正式移动 `stock_recommendation.py` 代码前，必须先跑：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_recommendation_strategy_contracts.py tests\test_stock_recommendation.py tests\test_recommendation_service.py -q
```

拆分后同一命令必须保持通过；如果输出股票、排序、评分或诊断边界变化，应视为误伤策略，而不是普通重构差异。
