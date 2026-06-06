# Bug fixes & context 2026-06-07

## 个股日K在线优先与成交量展示修复

- 修复个股分析页 A 股日 K 取数顺序问题：本地真实 K 线缓存存在时，旧逻辑会先使用本地缓存，导致在线同花顺/腾讯/新浪日 K 实际可用时，页面仍可能显示“在线日K源暂不可用”。现在统一先请求在线 `1y` 前复权日 K，只有在线结果异常或为空时才读取本地真实 K 线缓存兜底。
- 保留本地真实 K 线兜底能力；兜底时仍继续并行获取基础信息、实时行情、分时、基础资料和扩展资料，不把“财务 / 资金 / 新闻”直接降级为空占位。
- 修复成交量展示口径：实时行情没有 `quote_date/date` 时，不再用实时成交量覆盖最后一根日 K 成交量；成交量图和右上角量能指标都以日 K 数据为准，只有明确同日/更新日期的实时量才参与展示补偿。
- 离线行情缓存现在保存并恢复 DataFrame `attrs`，尤其是 `volume_unit`；旧缓存缺少单位时按成交量数量级推断 `share/hand`，避免本地缓存兜底后把股和手混用，导致成交量柱或均量显示异常。
- 本次未改变 A 股决策委员会评分、置信度、动作、仓位规则；研报/EPS 一致预期仍只作为辅助展示和催化提示，不参与核心分数。

## 浏览器实点验证

- 本地 Streamlit `http://localhost:8501` 实际搜索 `002541 · 鸿路钢构`：
  - 未出现“在线日K源暂不可用”。
  - 未出现“未能获取到数据”。
  - 页面成功显示决策仪表盘，决策分为 `21`。
  - 顶部成交量显示 `11.1万`。
  - 成交量图展开并实际渲染，图表头显示 `量 11.10万｜MA5 96660.55｜MA10 11.97万｜换手 2.24%`，图中可见 `量 / MA5 / MA10 / 万手`。
  - 浏览器控制台未发现 error/warn 日志。

## 回归测试

- `.\.venv\Scripts\python.exe -m pytest tests\test_data_fetcher.py tests\test_app_plotly.py tests\test_ui_enhancements.py tests\test_decision_stability.py tests\test_decision_committee.py tests\test_config.py tests\test_json_cache_keys.py -q` 通过，`277 passed`。

