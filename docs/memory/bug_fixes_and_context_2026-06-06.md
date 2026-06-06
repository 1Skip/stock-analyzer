# Bug fixes & context 2026-06-06

## 个股决策盘后稳定性

- 修复 A 股个股分析日 K 缓存版本在盘后仍按分钟变化的问题。A 股日 K 缓存现在仅在交易时段 `09:15-15:30` 按分钟刷新；同一交易日盘后统一落到 `YYYYMMDD-closed`，盘前统一落到 `YYYYMMDD-preopen`。
- 修复目标是避免同一只 A 股在同一交易日盘后重复搜索时，因为日 K 缓存 key 分钟变化而重新拉取/重算，导致决策分、置信度和 Agent 结论出现不必要漂移。
- 新增 `tests/test_decision_stability.py` 决策稳定性回归包，覆盖：
  - 同一份决策输入重复运行时，分数、置信度、动作、仓位、关键位和 Agent 明细必须一致。
  - 同一交易日盘后多个时间点的 A 股日 K 缓存版本必须一致。
  - 交易时段内 A 股日 K 缓存仍按分钟刷新，保留盘中更新能力。
- 更新 `tests/test_ui_enhancements.py` 中原有 A 股日 K 缓存版本测试：明确区分交易时段分钟刷新与盘后同日稳定。

## 验证

- `.\.venv\Scripts\python.exe -m pytest tests\test_decision_stability.py tests\test_decision_committee.py tests\test_ui_enhancements.py -q` 通过，`103 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_json_cache_keys.py tests\test_system_status_page.py -q` 通过，`52 passed`。

## 边界

- 本次修复锁定的是 A 股日 K 缓存版本和确定性决策输入稳定性；若盘后重复搜索仍因扩展资料、资金流、实时行情接口返回不同或超时导致结论漂移，需要继续把扩展资料/资金流快照纳入盘后稳定缓存或在 UI 中展示数据完整度差异。
