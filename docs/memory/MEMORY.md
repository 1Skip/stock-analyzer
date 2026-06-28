# 项目 Memory 索引


- [Bug fixes & context 2026-06-23](bug_fixes_and_context_2026-06-23.md) — agent.md 乱码修复，测试同步 T+1 板块从 4 → 2（config.py 已前置落地），测试合约适配新方法签名
- [Bug fixes & context 2026-06-28](bug_fixes_and_context_2026-06-28.md) — 智能推荐页新增手工实盘买卖结果录入、继续持有、成功率汇总、样本充足提醒和记录删除；移除旧复盘入口，保留后端只读历史复盘/短线学习链路；推荐页操作按钮按主流程重排。

- [Bug fixes & context 2026-06-21](bug_fixes_and_context_2026-06-21.md) — 热门板块改为同花顺热度榜优先，补齐概念/行业/指数板块和板块统计全部/行业/概念；板块统计按同花顺官方行业/概念名单过滤到 App 同层级；涨跌排行页新增对应展示，短线推荐内部热门板块改为概念与行业交错合并，避免热门概念被行业榜挤出；真实接口和定向测试已验证。
- [Bug fixes & context 2026-06-19](bug_fixes_and_context_2026-06-19.md) — 短线推荐增强为技术打底 + 基本面、财报、资金流、消息面、热门板块共同参与评分；推荐页展示新增短线策略命中依据；激进突破型、多因子稳健型和 T+1 买卖点生成逻辑未改。
- [Bug fixes & context 2026-06-17](bug_fixes_and_context_2026-06-17.md) — 清理长线策略入口、配置、底层推荐实现和本地 T+1 长线缓存/历史记录；新增短线闭环学习实验版，只读取短线 T+1 真实回看数据生成动态门槛和学习加权，科创板防误入，激进突破型/多因子稳健型不接入学习层；记录剩余三阶段：真实样本积累、动态评分验证、可信度复盘，并在数据足够时提醒是否进入下一阶段或评估项目评分依据调整。
- [Bug fixes & context 2026-06-16](bug_fixes_and_context_2026-06-16.md) — 智能推荐新增只读最近交易日复盘与归档，页面展示复盘概览、明日进化建议和历史计划；多因子稳健型轻筛补充 K 线核心因子兜底，避免明显不满足规则的候选进入深度检查。
- [Bug fixes & context 2026-06-08](bug_fixes_and_context_2026-06-08.md) — 修复 A 股决策委员会“看多依据”误混入负向证据的问题；扩展信息分层缓存支持财务/资金流部分命中，资金流短缓存过期时不再拖累财务长缓存；补充项目协作回复纪律；`tests/test_decision_committee.py`、`tests/test_data_services.py` 通过。
- [Bug fixes & context 2026-06-07](bug_fixes_and_context_2026-06-07.md) — 修复个股分析 A 股日 K 在线源被本地缓存抢先使用的问题；成交量图和量能指标忽略无日期实时量，离线缓存保留/推断 `volume_unit`；已用浏览器实点验证 `002541` 页面无“在线日K源暂不可用”、成交量图正常渲染，并通过 `277 passed` 回归。
- [Bug fixes & context 2026-06-05](bug_fixes_and_context_2026-06-05.md) — 合并 `CLAUDE.md` 到 `agent.md` 并删除旧文档；完成低风险工程优化、系统状态只读诊断、缓存日志、港股/美股涨跌排行真实数据兜底和结果型下拉框验证；非网络全量测试 `867 passed`。
- [Bug fixes & context 2026-06-04](bug_fixes_and_context_2026-06-04.md) — 完成工程优化收尾：智能推荐模块拆分、行情 provider 化、调度状态可观测、真实数据契约/文档/HTML 安全检查、分时改回新浪优先并按同花顺式波浪线展示；明确推荐策略红线未改。
- [Bug fixes & context 2026-06-03](bug_fixes_and_context_2026-06-03.md) — 风控防御看板重排主结论/风险/观察/支撑，指标说明改为内嵌展开；扩展信息深层数据链路修复，资金流/股息率等有值展示、无值降噪并在数据质量区说明；Streamlit `width="stretch"` 与 selectbox 状态警告清理。
- [Bug fixes & context 2026-05-21](bug_fixes_and_context_2026-05-21.md) — 个股分析日K/成交量/MA/KDJ/BOLL 与同花顺截图口径对齐；新增同花顺日K源、日K新鲜度回退、旧 session 日K失效、成交量真实单位换算、日K range slider 移除和中文名称兜底。
- [Bug fixes & context 2026-05-20](bug_fixes_and_context_2026-05-20.md) — 新增项目随附 Codex Skill，固化项目红线、真实链路验证规范和“更新推送”流程；明确 Skill 是执行 SOP，CLAUDE.md 仍是项目红线正式来源。
- [Bug fixes & context 2026-05-19](bug_fixes_and_context_2026-05-19.md) — A 股个股分析指标与同花顺口径重新对齐，智能推荐展示指标复用同一口径，T+1 买卖点与飞书推送接入，GitHub Actions 自选股 Secret 同步验证，个股分析切页错位修复。
- [Bug fixes & context 2026-05-17](bug_fixes_and_context_2026-05-17.md) — T+1 推荐计划缓存、收盘后预热入口、入场检查实时兜底、页面状态隔离、真实进度条、个股搜索残留修复、PEG 口径复用和资金流接口排查。
- [Bug fixes & context 2026-05-16](bug_fixes_and_context_2026-05-16.md) — 智能推荐策略定版、全市场策略池、缓存加速、真实阶段进度、周末 K 线过滤与需求严格执行约束。
- [Bug fixes & context 2026-05-14](bug_fixes_and_context_2026-05-14.md) — 决策委员会、飞书 Actions、自选股、中文名称识别、个股扩展信息、股票对比、页面切换、大盘温度、深色主题和推送卡片补齐。
- [Bug fixes & context 2026-05-13](bug_fixes_and_context_2026-05-13.md) — 对比 `daily_stock_analysis` / `a-stock-data` 后新增每日决策仪表盘，接入研报、风险事件、板块归因和 GitHub Actions 定时推送。
- [Bug fixes & context 2026-05-12](bug_fixes_and_context_2026-05-12.md) — 全量 A 股名称索引、搜索性能优化、运行缓存迁移、API 安全提示。
- [Project state 2026-05-10](project_state.md) — P0 代码质量修复完成，P1/P2 优化待做。
- [Optimization plan 2026-05-10](optimization_plan.md) — 测试隔离、缓存写坏、XSS、大文件拆分、评分合并、AI 线程安全、依赖 CI、配置块优化计划。
- [Screenshot folder](screenshot_folder.md) — 问题截图存放路径。
- [Bug fixes & context 2026-05-09](bug_fixes_and_context_2026-05-09.md) — 涨跌幅榜从新浪切换到同花顺，板块数据源改为东方财富 F10 API，涨跌幅榜放开非主板股票。
- [Bug fixes & context 2026-05-08](bug_fixes_and_context_2026-05-08.md) — 指标补全、RSI 精度、数值位数统一、推荐与分析实时行情合并。
- [Bug fixes & context 2026-05-07](bug_fixes_and_context_2026-05-06.md) — 前缀匹配、自选股实时价、东方财富 K 线源恢复、指标卡片和 MACD 标识清理。
- [Auto-save memory and push](auto_memory_on_change.md) — 每次代码改动后自动记录到 memory 并推送，无需用户提醒。
