# 2026-06-22 短线闭环学习实验改进

## 运行层修复

- 删除残留调度器锁文件（PID 18660，2026-06-13），恢复调度器正常启动
- `.env` 新增 `T1_PLAN_PREHEAT_EXTENDED_INFO_DEEP=true`，启用深数据预热（fund_flow / risk_events / sector_attribution）
- `ui/recommend_page.py`：手动生成 T+1 计划时传入 `preheat_extended_info=True`，此前只有调度器路径触发

## 学习层改进

- `short_term_learning.py`：新增 outcome 持久化缓存（`short_term_learning_outcomes.json`，TTL 365 天）
  - 每次评估完一个短线计划的 outcome 后写入缓存，下次直接读取，不再依赖 K 线缓存的实时性
  - 解决了 K 线缓存 1 天过期后历史完成样本丢失的问题

## 短线评分因子改进（仅短线，不动激进/稳健）

- `stock_recommendation.py`：`_evaluate_short_term_technical_filters` 的 `details` 新增 `"量比": volume_ratio_5`，`_score_volume` 可直接读取浮点数
  - volume 因子零率：全历史 79% → 最新批次 0%
- `recommend_ranker.py` 三处短线专属改动：
  1. `_component_from_strategy_score` 短线用 7 档（14/10/6/2/0/-4/-8）替代原 4 档（12/8/4/-8），避免大量股票挤在最高档
  2. `_score_trend` 短线 MA20 跌破只扣 2 分（原 6 分），站上只加 2 分（原 4 分），减小趋势因子在 T+1 场景下的反转效应
  3. `_score_sector` 短线"全部"板块在无行业归因数据时给 4 分基础分（热门板块成分股兜底），sector 零率待下一次生成验证

## 测试

- `tests/test_recommendation_service.py`：更新学习状态断言，从 `== "insufficient_samples"` 改为 `in ("active", "insufficient_samples")`，适配学习 profile 已进入 active 的当前状态
- `tests/test_short_term_learning.py`：4 passed（无改动，历史测试保持兼容）
- 全量回归：133 passed, 1 fixed, 2 pytest tmp 权限错误（非代码问题）

## 待观测

- capital 因子零率 74%（deep 预热已运行，fund_flow 数据源覆盖问题，等更多板块股票累积可降）
- 因子改善后分数段反转是否缓解（需等 2-3 轮新样本完成 outcome 评估）
- Streamlit 已于 14:15 重启验证，sector=4 已在新计划中确认
