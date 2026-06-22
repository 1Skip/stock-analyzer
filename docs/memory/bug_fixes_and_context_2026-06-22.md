# 2026-06-22 更新记录

## 数据源扩展
- kshare_info_provider.py — 新增新浪财经资金流数据源（直连新浪 ip.stock.finance.sina.com.cn），作为资金流查询链首选源。新增 _fetch_fund_flow_sina() 和 _normalize_fund_flow_sina()，解析新浪的 netamount/ratioamount/r0_net 等字段。
- 财务数据解析增加新浪新格式适配（列名为"报告日"时走新逻辑，老格式 fallback）。

## 推荐质量优化
- market_rankings.py — THS 排行结果增加主板占比校验：主板票 ≥ limit/5 才采用，否则降级到新浪排行。
- stock_recommendation.py — 热榜板块遍历加熔断（连续 3 个板块无票则 break）、兜底候选池收紧（非 hot_board 源只补到 limit/5）、同花顺热榜接口改用 equests.get 直连、成分股获取优先走 THS 接口。

## 板块定义清理
- stock_names.py — 删除"电力"和"算力租赁"两个板块的硬编码龙头股定义（各 8 只），SECTOR_STOCKS 仅保留苹果概念和特斯拉概念。

## 动态板块成分股
- stock_recommendation.py — 新增 SHORT_TERM_SECTOR_THS_CODES 常量，映射"苹果概念"→THS 代码 300309、"特斯拉概念"→THS 代码 301121。
- _get_short_term_sector_recommendations 调用链改为：先传 THS 板块代码走 _get_board_constituent_stocks 动态拉成分股（直连同花顺详情页），失败再 fallback 到 EM（东方财富），最后才用 _get_strategy_sector_stocks 的写死列表兜底。
- 板块成分股不再局限于硬编码 16 只，全部/苹果/特斯拉三个选项均为动态获取。

## 验证
- pytest tests/test_stock_recommendation.py::TestSectorStocks tests/test_recommendation_service.py -q -> 34 passed
- 测试 	est_four_sectors_exist 同步更名为 	est_sectors_exist，移除电力/算力租赁断言。
- 其余 152 个 ERROR 均为 pytest-of-skip8 temp dir PermissionError，系本机环境问题，非代码改动导致。
