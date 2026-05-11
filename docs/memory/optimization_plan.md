---
name: optimization plan 2026-05-10
description: 项目优化全景：测试隔离+缓存写坏+XSS+大文件拆分+评分合并+AI线程安全+依赖CI，含两个配置小坑
type: project
originSessionId: 35a65abf-4e04-45e9-9335-f14881646c5d
---
## 最高优先级

### 1. ~~修测试隔离问题~~ ✅ 已完成 (commit 6c41cce)
- 现象：`pytest -q -m "not network"` → 494 passed / 20 failed，单跑 test_stock_recommendation.py 80 passed
- 根因：test_data_fetcher.py 做了 `importlib.reload(data_fetcher)`，导致 stock_recommendation.py 持有的 `StockDataFetcher` 是旧类引用，monkeypatch patch 的是新类
- 修复：移除 `importlib.reload`，改为直接 new instance 测试 env var
- 结果：514 passed, 0 failed

### 2. ~~修离线缓存写入~~ ✅ 已完成 (commit 6c41cce)
- 现象：`.stock_cache.json` 已是坏 JSON，解析报 `Extra data`
- 根因：data_fetcher.py 多线程下直接读写同一个文件，无锁保护
- 修复：加 `_cache_lock` + 原子写入 `os.replace` + JSONDecodeError 自动重建

### 3. 收敛 unsafe_allow_html
- app.py 955行、1794行、1890行有外部股票名/自选股名称进入 HTML 但未 escape
- 修复方案：小 helper 统一 `html.escape(str(x))`，常量样式和动态内容分开

## 下一批优化

### 4. 拆大文件
- app.py ~1862行、data_fetcher.py ~1168行、stock_recommendation.py ~980行
- 建议先拆 app.py：pages/analyze.py、pages/hot.py、pages/recommend.py、components/charts.py、styles.py
- 先移动不改逻辑，风险最低

### 5. 合并评分逻辑
- 评分在 stock_recommendation.py 三处重复（标准/短线/长线）
- config.py 的 RATING_THRESHOLDS 和 LONG_TERM_WEIGHTS 基本没被真正用起来
- 建议抽成 `score_indicators(strategy, df, signals, weights)`

### 6. AI 调用线程安全
- ai_analysis.py 80行和244行改 `os.environ["OPENAI_API_BASE"]`，多Agent并发有串线风险
- 改成每次调用传 base_url/api_base 参数

### 7. 统一依赖和 CI
- requirements.txt 固定老版本，实际环境 pandas 3.0.2 / numpy 2.4.4 / streamlit 1.57.0
- GitHub workflow 用 Python 3.11，本机 py 是 3.14
- 建议明确支持版本，加测试 workflow

## 两个配置小坑

1. **MARKET_INDEX_ENABLED**：注释写"默认关闭"，config.py 211行默认是 `"true"` — 注释和代码矛盾
2. **API_AUTH_KEY**：匿名路径允许 `/webhook`，实际飞书路由是 `/webhook/feishu`，设置 API_AUTH_KEY 后可能挡住飞书回调

**How to apply:** 先修 #1 测试隔离 + #2 缓存写坏，收益最大。其余按优先级依次推进。
