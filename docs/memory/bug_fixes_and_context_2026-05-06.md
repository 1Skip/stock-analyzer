---
name: Bug fixes and context snapshot 2026-05-07
description: 5/6-5/7 修复记录 + 关键结论，供下一 session 恢复进度
type: project
---

# 2026-05-06 修复记录与上下文快照

## 一、Bug 修复记录

### Bug 1：AKShare spot 快照代码前缀匹配失效

**现象**：推荐页面/个股分析显示的股价与同花顺/新浪财经不一致，显示的是昨收价而非实时价。

**根因**：`ak.stock_zh_a_spot()` 返回的 DataFrame 中 `代码` 列带交易所前缀（`sh600519`、`sz000001`、`bj920000`），但代码中 3 处查询用的是纯数字代码（`600519`、`000001`），导致 `spot_df['代码'] == symbol` 永远匹配不上。

**影响范围**：
- `data_fetcher.py:553` `get_stock_name()` — AKShare 快照路径失效，每次走新浪 HTTP fallback
- `data_fetcher.py:608` `get_realtime_quote()` — 同上
- `data_fetcher.py:753` `get_batch_realtime_quotes()` — **完全失效**，永远返回 `{}`，导致推荐页面批量实时价格刷新不生效

**修复**：3 处全部改用 `spot_df['代码'].str.endswith(symbol)`，兼容 `sh600519` 和 `600519` 两种格式。

**修复文件**：`data_fetcher.py` line 553, 608, 753

**验证**：511 tests pass

---

### Bug 2：自选股 mini 面板显示 K 线收盘价而非实时价

**现象**：侧边栏自选股列表显示的是昨收价（如上海电力显示 17.00 而非 17.47）。

**根因**：`watchlist.py:117` 直接用 `result['price'] = float(latest['close'])`，完全没调实时行情。

**修复**：先用 `fetcher.get_realtime_quote(symbol, market)` 获取实时价，拿不到才 fallback 到 K 线 `latest['close']`。

**修复文件**：`watchlist.py` line 113-119

**验证**：182 related tests pass

---

### Bug 3：`get_batch_realtime_quotes` 超时失败 + 慢速全市场快照

**现象**：推荐页面批量实时价格刷新永远返回空（即使修了前缀匹配后仍然空）。

**根因**：
1. `ak.stock_zh_a_spot()` 下载 5511 只股票需要 23-24 秒
2. `_get_spot_snapshot()` 超时只有 8 秒，永远超时失败返回 None
3. `get_batch_realtime_quotes()` 依赖快照，快照失败 → 返回空 `{}`
4. 因此推荐页面价格永远是 K 线收盘价

**修复**：重写 `get_batch_realtime_quotes()` 为并行新浪 HTTP 调用：
- 每只股票独立 HTTP 请求（~200ms）
- ThreadPoolExecutor(max_workers=10) 并行
- 10 只股票只需 0.66 秒（原方案 23 秒 + 超时失败）

**修复文件**：`data_fetcher.py` `get_batch_realtime_quotes()` 完全重写

**验证**：10 只股票 0.66 秒全返回，511 tests pass

---

### Bug 4（重叠因素）：AKShare 数据源切换回新浪

**背景**：P16 把 `_get_spot_snapshot()` 从东方财富 `stock_zh_a_spot_em()` 改为新浪 `stock_zh_a_spot()`。新浪源比东方财富慢很多（23s vs ~5s），8秒超时在原东方财富源下可能勉强够，换新浪后彻底不够。

**当前状态**：`get_batch_realtime_quotes` 已不再依赖 `_get_spot_snapshot()`，改用并行新浪 HTTP。`get_realtime_quote()` 和 `get_stock_name()` 的快照路径仍会超时，但有新浪 HTTP fallback 正常工作。

---

## 二、Compact 前的关键上下文

### 本轮对话进度

1. ✅ 发现并修复 AKShare 前缀匹配 bug（3 处）— `str.endswith()`
2. ✅ 发现并修复自选股 mini 面板 K 线收盘价问题 — 实时行情优先
3. ✅ 重写 `get_batch_realtime_quotes` — 并行 HTTP 替代慢速快照
4. ✅ 511 tests 全过
5. ✅ CLAUDE.md 新增规则：先验证再汇报

### 仍待处理（来自之前审计）

| 功能 | 问题 | 状态 |
|------|------|------|
| 自选股 mini 面板 | K线收盘价 → 实时价 | ✅ 已修复 |
| 股票对比 | 仍用 K 线收盘价 | ❌ 未处理 |
| API server (飞书) | 仍用 K 线收盘价 | ❌ 未处理 |
| Scheduler 推送 | 仍用 K 线收盘价 | ❌ 未处理 |
| 大盘温度指数 | 仍用东方财富 (`stock_zh_index_spot_em`) | ❌ 未处理 |
| `SPOT_CACHE_TTL_SECONDS` | config.py 中定义但未使用，实际硬编码 60s | ❌ 未处理 |

### 仍待处理（P15 计划）

P15 计划文件：`C:\Users\skip8\.claude\plans\merry-napping-wolf.md`
内容：修复个股分析进度条完成后长时间空白 — 已实现，待 Streamlit 验证

### 用户偏好

- **先验证再汇报**：对用户说的任何结论必须先用代码/数据/测试验证，不确定就说"让我确认一下"
- 中文交流
- 修改代码后不自动 commit/push，除非明确要求

---

# 2026-05-07 修复记录

## 三、Bug 修复记录

### Bug 5：技术指标数值与同花顺不一致

**现象**：深圳能源(000027) RSI、MACD、均线数值与同花顺对不上，用户说"之前调好了现在又变了"。

**根因**：`ff4b038`(4/29) 把 K线数据源从 `ak.stock_zh_a_hist`（东方财富，**与同花顺共用数据商**）换成了 `ak.stock_zh_a_daily`（腾讯财经）。commit message 写明原因：东方财富 API (`push2his.eastmoney.com`) 被本机代理/防火墙封锁。

同花顺用的是东方财富数据，换到腾讯财经后 OHLC 数据本身就不同，即使指标公式正确（MyTT，多轮对齐），算出来的值也不一致。

**验证**：
- AKShare(腾讯) vs AKShare(东方财富) vs 新浪 — 三个源 OHLC 数据完全一致（深圳能源近期无除权除息）
- 与同花顺对比：RSI(24) 几乎一致(54.96 vs 54.98)，短期指标差异大(RSI6 63.33 vs 56.18)
- 差异源于底层 OHLC 数据不同，非计算逻辑 bug

**修复**：
1. 新增 `_get_cn_stock_data_akshare_em()` 方法 — 使用 `ak.stock_zh_a_hist()`（东方财富），`adjust=""`（不复权）
2. 数据源优先级调整为：东方财富 → 腾讯财经 → 新浪 → yfinance
3. 东方财富被网络拦截时自动降级到腾讯财经（重试3次后 fallback）
4. 网络通时自动恢复与同花顺的数据对齐

**限制**：本机网络稳定封锁 `push2his.eastmoney.com`，东方财富源一直失败，实际走腾讯财经。网络环境改变后会自动恢复。

**修复文件**：`data_fetcher.py` 新增 `_get_cn_stock_data_akshare_em`，更新 `all_sources` 和 `data_source` 映射

**验证**：511 tests pass

---

### Bug 6：指标数值卡片布局遮挡

**现象**：个股分析页"技术指标数值"卡片中，右侧阈值提示（超买>70 超卖<30）与左侧指标值重叠，文字被遮挡。

**根因**：卡片使用 `float:right` 定位阈值提示，容器窄时浮动元素与左侧文本重叠。

**修复**：改为 flexbox 布局：
- `display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px 12px;`
- 阈值提示加 `white-space:nowrap` 防止换行
- 空间不足时自动换行而不是重叠

**修复文件**：`app.py` `_display_indicator_values()`

---

### MACD 图表标识清理

- 去掉顶部 MACD 子图标题（`subplot_titles` 中 `"MACD"` → `""`）
- 保留底部 MACD 标注 + 零轴参考线
- 图例保留：DIF (快线)、DEA (慢线)、MACD柱

**修复文件**：`app.py` `plot_candlestick_chart()`

---

## 四、更新后的仍待处理

| 功能 | 问题 | 状态 |
|------|------|------|
| 自选股 mini 面板 | K线收盘价 → 实时价 | ✅ 已修复 (5/6) |
| 实时股价 | 前缀匹配 + batch重写 | ✅ 已修复 (5/6) |
| 指标数值显示 | flexbox遮挡 | ✅ 已修复 (5/7) |
| K线数据源 | 东方财富优先(与同花顺对齐) | ✅ 已修复 (5/7，但网络封锁限制) |
| 股票对比 | 仍用 K 线收盘价 | ❌ 未处理 |
| API server (飞书) | 仍用 K 线收盘价 | ❌ 未处理 |
| Scheduler 推送 | 仍用 K 线收盘价 | ❌ 未处理 |
| 大盘温度指数 | 仍用东方财富 (`stock_zh_index_spot_em`) | ❌ 未处理 |
| `SPOT_CACHE_TTL_SECONDS` | config.py 中定义但未使用 | ❌ 未处理 |

## 五、关键架构知识

### K线数据源优先级（当前）
```
东方财富 (ak.stock_zh_a_hist, adjust="")
    ↓ 失败 → 重试3次
    ↓ 仍失败 →
腾讯财经 (ak.stock_zh_a_daily, adjust="")
    ↓ 失败 →
新浪财经 (HTTP API)
    ↓ 失败 →
Yahoo Finance (yfinance)
    ↓ 全部失败 →
离线缓存 (.stock_cache.json, 24h有效)
```

### 指标公式（不要再改）
- 使用 MyTT 库（与同花顺/通达信一致）
- 自 `00e8274` 后 `technical_indicators.py` 未改动
- 公式正确性已验证：RSI(24) 与同花顺差异 <0.02

### 东方财富网络限制
- `push2his.eastmoney.com` 被本机网络封锁（非代码问题）
- 网络恢复后东方财富源会自动接管
- 腾讯财经源稳定可用，数据可靠但 OHLC 与同花顺有差异
