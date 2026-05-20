# Bug fixes & context 2026-05-20

## 项目随附 Codex Skill

- 新增项目级 Codex Skill：`.codex/skills/stock-analyzer/SKILL.md`，并提交到 GitHub，作为本仓库随附的 AI 执行 SOP。
- Skill 覆盖本项目常见高风险流程：项目红线、推荐/T+1 边界、飞书/GitHub Actions、缓存/调度检查、真实数据链路验证、memory/README 更新、commit/push 和用户说“更新推送”时的固定流程。
- Skill 不替代 `CLAUDE.md`：`CLAUDE.md` 仍是项目红线、架构约定和长期协作规则的正式来源；Skill 负责把这些规则转成 Codex 执行时的快速检查清单。
- 已把 Skill 从用户全局目录 `C:\Users\skip8\.codex\skills\stock-analyzer` 移到项目目录 `.codex/skills/stock-analyzer`，避免作为全局 Skill 误用于其他项目。
- 提交到 GitHub 前已把 Skill 头部的本机绝对路径改成仓库通用描述，避免项目规则写死到单台机器路径。

## 验证结果

- Skill 官方校验：`.venv\Scripts\python.exe C:\Users\skip8\.codex\skills\.system\skill-creator\scripts\quick_validate.py .codex\skills\stock-analyzer`，设置 `PYTHONUTF8=1` 后结果为 `Skill is valid!`。
- 本次为文档/Skill 元数据更新，不涉及应用代码、策略筛选、排序、推送逻辑或缓存生成逻辑。

## 同花顺「主力吸货」公式指标

- 新增同花顺公式版「主力吸货」指标，按用户提供公式实现 `main_accumulation`、`accumulation_risk`、`accumulation_trend` 三个字段；公式由真实日 K 的 high/low/close 推导，不读取同花顺插件私有数据，不使用模拟或随机行情。
- 个股分析页新增「主力吸货」数值卡片和折叠图，折叠图移除内部重复标题，避免与图例重叠；右上角 chip 展示最新吸货/风险/涨跌值。
- 推荐股、自选股摘要和共享指标快照均保留主力吸货三字段；飞书/企业微信自选股摘要、四板块推荐、T+1 推荐计划正文会追加「主力吸货: 吸货/风险/涨跌（同花顺公式，真实日K推导）」。
- 本轮未改变任何选股策略、评分、排序、T+1 缓存读取或入场检查语义，新增指标仅用于展示和推送说明。

## 今日推送排查

- 本地 `reports/history/latest.md` 最后更新时间为 2026-05-15 14:39:51，今天没有生成新的本地日报。
- 本地 `scheduler.out.log` / `scheduler.err.log` 最后更新时间为 2026-05-19 15:31-15:32，今天没有调度日志。
- `.cache/scheduler.instance.lock` 停在 2026-05-19 20:15:53，锁内 PID `34592` 当前无对应 Python 进程，判断为过期调度锁；本地调度器今天未运行，因此未触发本地飞书推送。
- 2026-05-19 日志还显示大量东财 K 线请求代理失败，以及日报生成因 `.cache/stock_research.json.lock` 超时失败；这些是昨日调度失败线索，不能解释今天触发缺失以外的云端 Actions 状态。
- 若依赖本地推送，需要清理过期锁并重新启动 `python main.py --schedule`；若依赖 GitHub Actions 15:30 云端推送，需要到 Actions 页面确认当天 workflow 是未触发、失败，还是 webhook/数据源失败。

## 今日推送修复结果

- 已清理本地过期 `.cache/scheduler.instance.lock` 和 `.cache/stock_research.json.lock`，解除本地调度器和日报生成被旧锁卡住的问题。
- 已修复 `data/cache.py` 的跨进程 JSON 缓存锁：锁文件写入 PID 和时间戳，遇到空锁、异常锁、已退出进程锁或超过阈值的旧锁时自动清理，避免 `stock_research.json.lock` 这类残留锁继续阻塞推送链路。
- 已执行 `.venv\Scripts\python.exe main.py --notify`，本地日报生成完成并写入 `reports/history/2026-05-20.md` 和 `reports/history/latest.md`。
- 已发送飞书连通性验证消息，`send_push(...)` 返回 `{'feishu': True}`，确认本地 webhook 推送通道可达。
- 已重新启动本地调度器，`.cache/scheduler.instance.lock` 当前锁内 PID 为 `30540`，时间戳为 `2026-05-20T20:33:12`；Windows 进程列表同时显示父/子进程，但实际调度锁持有者为 `30540`。
- GitHub Actions 手动运行 `26162812165` 仍为 `startup_failure` 且 `jobs: []`，失败发生在 GitHub runner 启动层，未进入项目代码执行；本次本地修复不能消除该云端 runner 层异常。

## 验证结果（同花顺指标与推送）

- `.venv\Scripts\python.exe -m pytest tests\test_notification.py tests\test_scheduler.py tests\test_t1_plan_push.py tests\test_technical_indicators.py tests\test_app_plotly.py -q` → `135 passed`，仅剩 MyTT 横盘样本 RSI/KDJ 既有 warning。
- `.venv\Scripts\python.exe -m pytest tests\test_app_plotly.py tests\test_notification.py -q` → `69 passed`。
- 真实 K 线验证：`000001` 以 `1y` 前复权日 K 成功生成 243 行指标，并输出 `main_accumulation` / `accumulation_risk` / `accumulation_trend` 最新值。
- `git diff --check` 通过；Windows 提示 LF 将被 CRLF 替换，不影响 diff check。

## 验证结果（飞书推送修复）

- `.venv\Scripts\python.exe -m pytest tests\test_data_services.py tests\test_notification.py tests\test_scheduler.py -q` → `114 passed`。
- `.venv\Scripts\python.exe main.py --notify` 已完成本地日报生成和正式通知流程；随后单独飞书验证推送返回 `{'feishu': True}`。
- `git diff --check` 通过。

## 定时推送分工调整

- 按用户确认后的新分工，15:30 只推自选股摘要 + 大盘/完整 Markdown 日报，旧的固定四板块聚合推荐推送已从 `scheduler.py`、`notification.py`、`config.py`、`RecommendationService` 和 `StockRecommender` 聚合入口中删除。
- 15:45 统一推 T+1 推荐计划：短线/长线覆盖苹果概念、特斯拉概念、电力、算力租赁四板块；多因子稳健型/激进突破型只生成全市场 `全部`，默认每组 5 只。该调整只改变调度与推送分工，不改变具体策略选股、评分、排序或 T+1 缓存语义。
- GitHub Actions `.github/workflows/daily_analysis.yml` 已拆成北京时间 15:30 与 15:45 两个定时点；15:30 运行 `python main.py --notify`，15:45 运行新增入口 `python main.py --t1-plan-preheat`。云端默认 `AI_MODEL` 同步改为 `deepseek/deepseek-v4-pro`，并移除旧的 `deepseek/deepseek-chat` 默认值。
- README、CLAUDE 和 `docs/FEISHU_GITHUB_ACTIONS.md` 已同步新的推送口径；旧的 `SECTOR_PUSH_*` 环境变量不再作为当前配置项记录。
