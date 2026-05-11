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

### 3. ~~收敛 unsafe_allow_html~~ ✅ 已完成 (commit b344c2f)
- 修复4处：分析标题、watchlist卡片、mini面板、大盘温度指数名
- 全部动态字段统一 `html.escape()`

## 下一批优化

### 4. 拆大文件
- app.py ~1862行、data_fetcher.py ~1168行、stock_recommendation.py ~980行
- 建议先拆 app.py：pages/analyze.py、pages/hot.py、pages/recommend.py、components/charts.py、styles.py
- 先移动不改逻辑，风险最低

### 5. ~~合并评分逻辑~~ ✅ 已完成 (commit c62877b)
- 新增 _STANDARD_WEIGHTS / _SHORT_TERM_WEIGHTS / _LONG_TERM_WEIGHTS 三组权重配置
- 新增 _score_from_signals() 通用评分函数 + _score_rating() 统一评级
- 净减115行，三个分析方法从~60行评分代码缩减为1行调用

### 6. ~~AI 调用线程安全~~ ✅ 已完成 (commit bcf7470)
- 移除 os.environ["OPENAI_API_BASE"] 全局修改
- 改为 litellm.completion(api_base=base_url) 参数传递

### 7. 统一依赖和 CI
- requirements.txt 固定老版本，实际环境 pandas 3.0.2 / numpy 2.4.4 / streamlit 1.57.0
- GitHub workflow 用 Python 3.11，本机 py 是 3.14
- 建议明确支持版本，加测试 workflow

## 两个配置小坑

1. **MARKET_INDEX_ENABLED**：注释写"默认关闭"，config.py 211行默认是 `"true"` — 注释和代码矛盾
2. **API_AUTH_KEY**：匿名路径允许 `/webhook`，实际飞书路由是 `/webhook/feishu`，设置 API_AUTH_KEY 后可能挡住飞书回调

**How to apply:** 先修 #1 测试隔离 + #2 缓存写坏，收益最大。其余按优先级依次推进。
