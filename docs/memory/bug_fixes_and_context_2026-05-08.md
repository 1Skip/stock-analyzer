---
name: Bug fixes and context snapshot 2026-05-08
description: 5/8 修复记录 — 智能推荐指标补全+数据周期统一+小数位对齐+实时行情合并
type: project
---

# 2026-05-08 修复记录

## Bug 1：智能推荐指标数值不完整

**现象**：智能推荐列表中每只股票的技术指标显示不全：
- MACD 只有 DIF，缺少 DEA 和 MACD 柱
- RSI 只有一个值（RSI6），缺少 12 和 24
- KDJ 只有 K 和 D，缺少 J
- BOLL 缺少 MID

**根因**：三个分析函数的 `indicators` 字典只返回了部分字段：
- `analyze_stock`：有 `macd`/`macd_signal`/`boll_mid`，缺 `macd_hist`/`rsi_6`/`rsi_12`/`rsi_24`
- `_analyze_short_term` 和 `_analyze_long_term`：更严重，连 `boll_mid` 都没有

**修复**：三个函数的 `indicators` 字典统一补全 `macd_hist`/`rsi_6`/`rsi_12`/`rsi_24`/`boll_mid`；`display_recommendation_list()` 展示逻辑同步更新。

**修复文件**：`stock_recommendation.py`（三个分析函数）+ `app.py`（展示逻辑）

---

## Bug 2：RSI 12/24 数值偏离同花顺基准

**现象**：浪潮软件(600756) RSI 12=60.65(同花顺60.42)，RSI 24=54.50(同花顺52.70)，差异随周期增大。

**根因**：RSI 使用 SMA(ewm, alpha=1/N)，RSI 24 需要约 96 个交易日才能收敛。但 `analyze_stock` 只取 3 个月数据(55期)，`_analyze_short_term` 只取 1 个月(~22期)，数据量不足导致 SMA 初值偏差未消除。

**验证**：
| 数据量 | RSI 6 | RSI 12 | RSI 24 |
|--------|-------|--------|--------|
| 3mo(55行) | 77.60 | 60.65 (偏0.23) | 54.50 (偏1.80) |
| 1y(243行) | 77.60 | 60.42 (对齐) | 52.69 (对齐, 差0.01) |

KDJ(9期)、BOLL(20期) 收敛快，不受影响。

**修复**：三个分析函数 + 个股分析页 K 线数据获取统一改为 `period='1y'`；个股分析页图表按用户选择的周期裁剪展示（指标基于完整数据计算）。

**修复文件**：`stock_recommendation.py` + `app.py`

---

## Bug 3：个股分析指标小数位不统一

**现象**：技术指标数值卡片中 RSI/KDJ 保留 1 位小数，MACD 保留 3 位小数，BOLL 保留 2 位。

**修复**：全部统一为 2 位小数。

**修复文件**：`app.py` `_display_indicator_values()`

---

## Bug 4：智能推荐与个股分析指标数值不一致

**现象**：同一只股票在智能推荐页和个股分析页显示的指标数值不同。

**根因**：个股分析页计算指标前会用 Sina 实时行情更新最后一根 K 线的收盘价（`get_realtime_quote` → merge），智能推荐的三个分析函数直接使用原始 K 线数据，实时价与 K 线收盘价不同时所有指标值偏移。

**修复**：`analyze_stock`/`_analyze_short_term`/`_analyze_long_term` 三个函数在计算指标前统一加入实时行情合并步骤（Sina HTTP ~200ms，失败时降级到原始 K 线）。

**修复文件**：`stock_recommendation.py`

---

## macOS 显示标签对齐同花顺

- `display_recommendation_list()` 中 MACD 标签顺序改为：**柱**{hist} DIF{dif} DEA{dea}（同花顺约定 MACD = 柱）
- 所有指标值统一 2 位小数

**修复文件**：`app.py`

## 更新后的仍待处理

| 功能 | 问题 | 状态 |
|------|------|------|
| 自选股 mini 面板 | K线收盘价 → 实时价 | ✅ 已修复 (5/6) |
| 实时股价 | 前缀匹配 + batch重写 | ✅ 已修复 (5/6) |
| K线数据源 | 东方财富优先 | ✅ 已修复 (5/7) |
| 指标数值显示 | flexbox遮挡 | ✅ 已修复 (5/7) |
| MACD 图表标识 | 去掉重叠标题 | ✅ 已修复 (5/7) |
| 智能推荐指标补全 | MACD/RSI/KDJ/BOLL 全字段 | ✅ 已修复 (5/8) |
| RSI 精度对齐 | 数据周期统一1y | ✅ 已修复 (5/8) |
| 个股分析小数位 | 统一2位 | ✅ 已修复 (5/8) |
| 推荐vs分析数值一致 | 实时行情合并 | ✅ 已修复 (5/8) |
| 股票对比 | 仍用 K 线收盘价 | ❌ 未处理 |
| API server (飞书) | 仍用 K 线收盘价 | ❌ 未处理 |
| Scheduler 推送 | 仍用 K 线收盘价 | ❌ 未处理 |
| 大盘温度指数 | 仍用东方财富 | ❌ 未处理 |
| `SPOT_CACHE_TTL_SECONDS` | 未使用 | ❌ 未处理 |

## 关键结论

- **技术指标计算必须用 >=1y 数据**：RSI 24 SMA 收敛需 ~96 期，BOLL 20、KDJ 9 不受影响。所有分析流程的数据获取统一为 1y。
- **实时行情合并是数据一致性的前提**：任何分析路径在计算指标前必须尝试合并实时行情，否则与个股分析页数值不一致。
- **与同花顺对齐已验证**：1y 数据 + MyTT 公式 → MACD/RSI/KDJ/BOLL 全部对齐（RSI 24 差 0.01 为四舍五入）。
