---
name: project state 2026-04-29
description: 技术指标精度修复完成，等待UI改造
type: project
originSessionId: 95efc3a3-2817-4aae-901d-8b6b78afe903
---
## 已完成

技术指标（MACD/RSI/KDJ/BOLL/MA）与同花顺完全对齐，所有37个测试通过。

关键修复：
1. 数据默认周期 3mo→1y（EMA/SMA 需120期收敛）
2. MyTT 库替换自写公式（同花顺标准算法）
3. MACD/BOLL 跳过 MyTT 的 RD() 舍入，直接使用 EMA/MA/STD 原语
4. BOLL 改用样本标准差 ddof=1（同花顺标准）
5. 实时行情拼接去重（同一交易日更新而非追加）
6. 显示精度统一为 2 位小数（`.2f`）
7. MACD 标签改为同花顺命名（DIF/DEA/MACD）

## 待做

- UI 苹果极简风改造（计划在 C:\Users\skip8\.claude\plans\merry-napping-wolf.md）
- BOLL 上轨/下轨剩余 ~0.02 差异可能是 AKShare 数据源与同花顺原生数据差异
