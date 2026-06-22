# 2026-06-23 文档乱码修复与测试同步

## agent.md 乱码修复

- 修复了多处因编码问题导致的 ? 乱码块，恢复为正常中文
- 「模块与文件结构」表中 
otification.py 行从乱码恢复为「通知与报告文本」
- 「核心特性 / 运行方式」中「日报调度」「通知报告」从乱码恢复为正常中文
- 示例命令中「启动本地调度 + 日报 + T+1 预热」从乱码恢复
- 协作规则中「调度结论必须验证」从乱码恢复
- Codex Skill 相关说明从乱码恢复
- 便捷脚本安全说明从乱码恢复
- 5.14/5.16 当日协作记录中多条乱码恢复，T+1 板块从 4 改为 2

## T+1 板块缩减同步（config.py 已前置落地）

- config.py 默认 T1_PLAN_SECTORS 已在 2026-06-22 从前置改动中从 苹果概念,特斯拉概念,电力,算力租赁 缩减为 苹果概念,特斯拉概念
- 本次同步测试文件：
  - tests/test_config.py：默认值断言、环境变量覆盖测试均匹配新 2 板块
  - tests/test_scheduler.py：T+1 计划目标生成从 6 项缩减为 4 项，测试用例重命名为 configured_sectors
  - tests/test_recommendation_strategy_contracts.py：适配合约方法重命名，股票数据新增 short_term_sectors 字段
- agent.md 中 13.1 当日需求落地同步更新推荐边界描述
- README.md 已在早期改动中同步更新，无需额外修改

## 测试验证

- tests/test_config.py：43 passed
- tests/test_recommendation_strategy_contracts.py：3 passed
- tests/test_scheduler.py：11 passed, 1 error（临时目录权限问题，非代码问题）
- stock_recommendation.py 仅换行符差异（LF→CRLF），无实质改动，不纳入本次提交
