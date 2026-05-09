---
name: Bug fixes 2026-05-09
description: 5/9修复：涨跌幅榜同花顺→新浪JSON API+板块数据源改为东方财富F10 API+行业板块HTML抓取替代AKShare+概念板块排行(客户端排序)+Web端vs手机APP数据源差异
type: project
---

## 已完成修复

1. **涨跌幅榜数据源：新浪 JSON API（最终方案）**
   - 第一轮：新浪 → 同花顺 `/rank/xstp/`（实际是短线突破，非涨跌幅榜）
   - 第二轮：改为 `/market/zdfph/`（涨跌幅排行，但仅沪深不含北交所）
   - **第三轮（最终）**：改为新浪 `vip.stock.finance.sina.com.cn` JSON API `node=hs_a`
   - 覆盖沪深京全市场（含北交所 92xxxx），JSON 格式易解析，无 HTML 反爬
   - 涨幅榜 #1 天铭科技(920270) #2 戈碧迦(920438)，与同花顺客户端一致
   - 跌幅榜 #1 振宏股份(920200) #2 *ST益通(300430)，与同花顺客户端一致
   - 移除 BeautifulSoup 依赖

4. **UI 苹果极简风 P0 — 色板统一**
   - CSS 变量：主色 `#1a73e8`→`#0071e3`，涨跌 `#e53935`/`#2e7d32`→`#ff3b30`/`#34c759`，中性 `#757575`→`#8e8e93`
   - 图表配色 config.py 同步更新
   - 卡片透明度 0.04→0.03，hover 0.08→0.06
   - 统一圆角 12px，添加微阴影 `0 1px 3px rgba(0,0,0,0.04)`
   - 主按钮色改为 CSS 变量，暗色主题自动适配
   - app.py 全局硬编码色值替换（~25处）

2. **板块/行业提取从新浪 HTML 改为东方财富 F10 API**
   - 新浪 HTML GBK 编码解析不稳定，替换为 `emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax`
   - 读取 `jbzl.sshy` 字段获取行业名称（如"银行"、"酿酒行业"）
   - 带缓存（`_sector_cache`），~0.2s/只
   - 回退策略：北交所(8/9开头)→北交所，68开头→科创板，30开头→创业板，6开头→沪市主板，其余→深市主板

3. **涨跌幅榜放开非主板股票**
   - `_get_market_ranking()` 移除 `_is_main_board` 过滤
   - 创业板/科创板/北交所全部显示在涨跌幅榜中
   - 智能推荐仍限制主板（`_is_main_board` 保留）

5. **涨跌幅榜仅创业板/科创板/ST**（已回退）
   - ~~新增 `_is_cyb_kcb_st()` 过滤~~ → 已删除，用户要求热门板块不做限制
   - 最终方案：热门板块涨跌幅榜全市场显示，智能推荐仅主板

6. **热门板块全市场 + 智能推荐仅主板**（最终方案）
   - `_get_market_ranking()` 不做任何过滤，全市场排行
   - 智能推荐所有 `_is_main_board()` 保留不变（7处）

7. **行业板块排行AKShare失败 → HTML直接抓取**
   - `ak.stock_board_industry_summary_ths()` 返回 "No tables found" → 改用直接抓取 `https://q.10jqka.com.cn/thshy/`
   - 2页共90个行业板块，HTML table解析（无需v cookie），与同花顺一致
   - 移除 `akshare` 依赖（`stock_recommendation.py` 不再使用）

8. **新增概念板块排行**
   - 数据源：`https://data.10jqka.com.cn/funds/gnzjl/order/desc/page/N/`（同花顺概念资金流向）
   - 8页约387个概念板块，取前30展示
   - **客户端排序**：该页面默认按主力资金净流入排序，字段参数(`field=3`/`field=zdf`/`field=199112`)均无法切换为涨跌幅排序，故抓取全部8页后Python端按涨跌幅降序排列
   - 注意：同花顺web版 `/gn/` 是概念大事记(timeline)而非排行，概念排行数据在资金流向页面
   - 概念板块字段：板块、涨跌幅、领涨股、领涨股价格、领涨股涨幅、净流入(亿)
   - **Web端 vs 手机APP差异**：用户指出手机APP显示概念为"商业航天、存储芯片、人形机器人"，行业为"半导体、电力、军工装备"，与Web端排名完全不同。确认手机APP使用独立的私有API，本项目使用Web端公开数据作为数据源

**Why:** AKShare 行业板块函数失效 + 用户需要概念板块排行，同花顺 ajax 概念排行需 v cookie 认证但非ajax排名页可直接抓取。

**How to apply:** 行业/概念板块改动在 `stock_recommendation.py` 的 `get_hot_sectors_cn()` 和 `get_hot_concepts_cn()`，展示在 `app.py` 的 `hot_stocks_page()`。
