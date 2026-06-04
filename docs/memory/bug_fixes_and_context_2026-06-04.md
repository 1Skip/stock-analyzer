# Bug fixes & context 2026-06-04

## 个股分析与日报修复

- 个股分析页快速匹配候选改为点击即提交当前候选代码并触发分析，避免第一次点击仍使用旧输入、第二次点击才有数据的问题；候选列表支持展开/收起更多匹配项。
- 个股分析页 A 股日 K 在线源失败或当日源滞后时，会继续使用最后可用真实前复权日 K 或本地真实 K 线缓存兜底，并在数据质量提示中说明来源；不使用实时价拼接假日 K。
- 个股分析页刷新陈旧结果失败时，会保留上次同标的可用真实日 K 展示并给出警告，避免页面直接清空成“未能获取”。
- 历史日报和新生成日报去掉“推荐池”区块；历史页面读取旧 Markdown 时也会在预览和下载前剔除该区块，保留 T+1 计划回看。
- 智能推荐页读取 T+1 计划缓存时，只补展示用基础资料字段，不重新扫描股票池、不改变已缓存推荐列表。
- 新增项目根目录 `agent.md`，记录本项目 Codex 沟通、简洁修改、精确提交、安全红线和测试闭环偏好；后续本项目默认按该偏好执行。

## 涨跌排行页面调整

- 由于行业板块、概念板块和指数板块无法在当前公开链路下稳定复刻同花顺 App 热榜口径，页面不再展示这三类板块榜，避免用不一致数据误导使用。
- 原“热门板块”模块改名为四字“涨跌排行”，只保留 A 股/港股/美股个股涨幅榜和跌幅榜；A 股实测只请求 `gainers` / `losers`，各返回 10 条。
- 左侧菜单“系统状态”补充 `🛠️` 图标，保持菜单项前缀风格一致。

## 工程优化完成项

- `stock_recommendation.py` 继续拆分到 `recommendation_modules/`：热门榜、板块榜、策略股票池、辅助数据、策略缓存分别进入独立模块，主文件保留对外入口和策略编排。
- 拆分过程中保持智能推荐红线：短线、长线、激进突破型、多因子稳健型的股票池、过滤条件、评分、排序、推荐数量和 T+1 选股语义不改。
- `data_fetcher.py` 的数据源细节继续 provider 化，新增/拆出同花顺日 K、东方财富分时/实时/指数、腾讯实时、新浪实时/分时、Yahoo K线/报价等 provider；`data_fetcher.py` 保留统一入口、缓存、健康状态和 fallback 编排。
- `data_fetcher.py` 不再直接调用 `yf.Ticker`，Yahoo K线和报价细节下沉到 Yahoo provider，便于单独测试。
- 调度器新增 `.cache/scheduler_status.json` 状态输出，记录 15:30 日报、15:45 T+1 预热和常规调度的运行时间、状态、命中数、失败原因和耗时；智能推荐页与系统状态页可读取展示。
- 新增 `ui/system_status_page.py` 和 `scripts/inspect_cache_status.py`，用于查看调度状态和运行缓存状态，减少只靠日志排查“是否生成/是否命中旧缓存”的成本。

## 分时走势修复

- A 股分时数据改回新浪财经 5 分钟数据优先，东方财富 1 分钟数据备用；这符合用户要求“接口改回新浪”。
- 分时图展示改为同花顺式价格波浪线、均价线、昨收参考线和成交量分区；均价计算统一用成交额和成交量股数口径，并修正新浪成交额单位差异导致均价线偏移的问题。
- 个股分析页分时区块使用 Streamlit fragment `run_every="60s"` 单独自动刷新，分时缓存 TTL 为 60 秒；新浪源本身仍是 5 分钟粒度，不代表秒级实时。
- 页面不再保留单独“刷新分时”按钮；顶部刷新分析按钮仍会清理分时缓存并重新分析。

## 质量与可维护性

- GitHub Actions 增加窄范围 `ruff check . --select E9,F63,F7,F82`，先作为语法和高风险静态报警器，不做全量格式化。
- 新增 `.github/workflows/real-data-contracts.yml`，网络可用时可显式跑真实数据字段契约检查。
- 新增 `scripts/check_real_data_contracts.py`、`scripts/check_unsafe_html_usage.py`、`scripts/check_doc_encoding.py`，分别用于真实数据契约、`unsafe_allow_html` 数量、文档编码检查。
- UI 动态 HTML 渲染抽到 `ui/html_helpers.py`，大部分页面改用 `st.*` 原生组件或统一 helper；当前 `unsafe_allow_html=True` 保留 5 处，属于全局 CSS、个股页锚点/滚动脚本和决策仪表盘核心 HTML。
- 多个 provider、推荐模块、调度状态页、系统状态页和 HTML 安全脚本都有对应单元测试，降低后续改动误伤概率。

## 验证结果

- UI / 导航 / 加载 / 状态相关测试通过：`119 passed`。
- 推荐策略相关测试通过：`162 passed`。
- 数据/provider 相关测试通过：`100 passed`。
- `scripts/check_unsafe_html_usage.py ui app.py --max-count 5` 通过，当前保留 5 处。
- `scripts/check_real_data_contracts.py` 离线模式通过；未带 `--network`，因此本轮不声称外部实时接口在线可用。
- `scripts/check_doc_encoding.py README.md docs recommendation_modules` 通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

## 后续注意

- 以后继续改推荐相关代码时，仍必须把“工程拆分”与“策略语义修改”分开；没有用户明确要求时，不改股票池、过滤、评分、排序和 T+1 生成口径。
- 分时图自动刷新是页面展示刷新，不是秒级行情能力；如果新浪源延迟或接口空返回，页面应显示数据不可用或使用真实备用源，不能补假分时。
- 真实数据契约的网络检查需要显式运行 `python scripts/check_real_data_contracts.py --network`，且结果只代表当次接口状态。
