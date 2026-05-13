# 股票分析系统

个人股票技术分析工具，支持 A股/港股/美股，提供 Web 界面和 CLI 两种使用方式。

## 功能特点

### 技术指标
- **K线图** — Plotly 交互式蜡烛图（Web），Matplotlib 静态图（CLI）
- **MACD** — 趋势判断和买卖时机，含金叉/死叉标注
- **RSI** — 6/12/24 三周期相对强弱指数
- **KDJ** — 随机指标，含金叉/死叉标注
- **BOLL** — 布林带，压力位/支撑位
- **MA** — 5/10/20/60 四条均线
- **分时图** — 当日价格走势 + 均价线 + 昨收参考线

### AI 智能解读
- 将技术指标快照交给 LLM 翻译为自然语言分析
- 自动检测 API Key 类型（OpenAI / Gemini / Claude / DeepSeek / 通义千问 等 10+ 模型）
- 可选开启/关闭

### 通知推送
- 企业微信机器人 Webhook
- 飞书机器人 Webhook
- 默认关闭，通过环境变量 `NOTIFY_CHANNELS` 开启（可选值：`wechat`, `feishu`）

### 市场支持
- **A股** — AKShare → 新浪财经 → Yahoo Finance 三级回退；中文名称搜索使用全量 A 股名称索引（5515+ 只，24h 本地缓存）
- **港股** — 新浪财经 → Yahoo Finance
- **美股** — 新浪财经 → Yahoo Finance
- **基础资料/估值** — A股接入分层数据服务，AKShare 个股资料 + 腾讯行情估值补充，展示行业、上市日期、市值、PE/PB、换手率

### 其他功能
- **热门股票** — 涨幅榜/跌幅榜/成交量榜 + 行业板块排行 + 概念板块排行，保留全市场热度观察
- **推荐股票** — 多因子技术分析评分（0-100），含短线/长线/板块推荐；A股推荐池仅包含沪深主板股票
- **股票对比** — 多只股票技术指标 + 走势决策仪表盘，含区间收益、最大回撤、波动率、上涨天数占比、MA 状态和相对强弱
- **回测引擎** — 信号→交易模拟，含止损/止盈/中性区间
- **大盘温度** — 上证/深证/沪深300/北证50 实时跟踪
- **自选股** — 持久化管理，支持 A股/港股/美股，侧边栏 mini 分析面板
- **每日决策仪表盘** — CLI/定时导出 Markdown 日报，汇总大盘、自选股、推荐股、研报、公告、龙虎榜、解禁、板块归因和操作检查清单
- **定时调度** — 收盘后自动分析+推送（默认关闭）
- **飞书机器人** — 对话式股票查询（默认关闭），支持 `/analysis 600519`、`分析贵州茅台`、`查 招商银行` 等代码/中文名称输入
- **三种配色** — A股传统（红涨绿跌）/ 国际惯例（绿涨红跌）/ 色盲友好（蓝涨橙跌）
- **离线缓存** — 所有在线源失败时使用 24h 缓存兜底

### 当前推荐与推送规则

- 热门板块页用于观察市场热度：行业板块排行、概念板块排行、个股涨幅榜/跌幅榜均保留全市场，不做主板过滤。
- 智能推荐和定时推荐股推送用于辅助决策：仅推荐沪深主板股票，创业板、科创板、北交所不进入推荐池。
- 定时推送顺序为：自选股摘要 → 四板块推荐 → 每日完整 Markdown 日报；四板块固定为算力租赁、电力、苹果概念、特斯拉概念。
- 四板块推荐默认每个板块短线 2 只 + 长线 1 只，可通过 `SECTOR_PUSH_SHORT_TOP_N` / `SECTOR_PUSH_LONG_TOP_N` 调整。

## 快速开始

### Windows 一键启动（推荐）

如果只是想直接使用 Web 页面：

1. 安装 Python 3.10+，安装时勾选 **Add Python to PATH**。
2. 双击项目根目录的 `start.bat`。
3. 首次运行会自动创建 `.venv` 并安装依赖，完成后自动打开浏览器。

常用脚本：

| 脚本 | 用途 |
|------|------|
| `start.bat` | 一键启动 Web 系统 |
| `创建桌面快捷方式.vbs` | 在桌面创建“股票分析系统”快捷方式 |
| `install_startup.bat` | 设置 Windows 登录后自动启动 |
| `uninstall_startup.bat` | 取消 Windows 开机自动启动 |

### 手动安装

```bash
cd stock_analyzer
pip install -r requirements.txt
```

### Web 界面

```bash
streamlit run app.py
```

个股分析页支持**股票代码/中文名称搜索**（如"平安银行"、"报喜鸟"、"茅台"），输入后按 **Enter 键**直接分析。A股名称索引会缓存到 `.cache/stock_name_index.json`，避免每次搜索都拉全市场行情。

### 下载后直接使用

别人下载本项目后，Windows 下最简单流程：

```text
解压项目 → 双击 start.bat → 等待依赖安装 → 浏览器自动打开
```

如果依赖安装慢或失败，可以先换 pip 镜像：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

macOS / Linux 用户：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### CLI 命令行

```bash
# 交互模式
python main.py -i

# 分析单只股票
python main.py -s 000001 -m CN -p 3mo    # A股平安银行
python main.py -s AAPL -m US              # 美股苹果
python main.py -s 0700 -m HK              # 港股腾讯

# 热门股票
python main.py --hot -m CN

# 推荐股票
python main.py --recommend

# 生成每日 Markdown 分析报告
python main.py --daily-report
python main.py --daily-report --report-dir reports/history
python main.py --daily-report --no-report-recommendations

# 启动定时分析和推送
python main.py --schedule
```

`--daily-report` 会生成 `reports/history/YYYY-MM-DD.md` 和 `reports/history/latest.md`。如果网络较慢或只想快速验证报告结构，可加 `--no-report-recommendations` 跳过推荐股扫描。

### 运行测试

```bash
pytest tests/ -v                    # 全部测试
pytest tests/ -v -m "not network"   # 跳过网络测试（离线环境）
pytest tests/test_technical_indicators.py -v  # 单文件
```

### 常用配置

- `RUNTIME_CACHE_DIR`：运行缓存目录，默认 `.cache/`，用于离线行情缓存和主板股票池缓存。
- `API_AUTH_KEY`：API 鉴权密钥；如果 API 服务不只监听本地地址，建议务必设置。
- `CACHE_TTL_FUNDAMENTALS`：A股基础资料/估值缓存时间，默认 3600 秒。
- `CACHE_TTL_WATCHLIST_SUMMARY` / `CACHE_TTL_WATCHLIST_MINI`：自选股侧边栏缓存时间，默认 300 秒。
- `STOCK_DATA_SOURCE`：A股数据源优先级，可选 `auto` / `akshare` / `sina` / `yfinance`。
- `SCHEDULE_TIME`：定时任务执行时间，默认 `15:30`。
- `NOTIFY_CHANNELS`：推送渠道，逗号分隔，可选 `wechat`, `feishu`。
- `SECTOR_PUSH_ENABLED`：定时推送是否包含固定四板块推荐，默认 `true`。
- `SECTOR_PUSH_SHORT_TOP_N` / `SECTOR_PUSH_LONG_TOP_N`：每个板块短线/长线推荐数量，默认 `2` / `1`。
- `DAILY_REPORT_ENABLED`：定时任务是否生成每日报告，默认 `true`。
- `DAILY_REPORT_PUSH_ENABLED`：定时任务是否推送完整 Markdown 日报，默认 `true`。
- `DAILY_REPORT_INCLUDE_RECOMMENDATIONS`：日报是否扫描推荐股，默认 `false`，避免定时推送过慢。
- `DAILY_REPORT_DIR`：日报输出目录，默认 `reports/history`。

## 项目结构

| 文件 | 职责 |
|------|------|
| `app.py` | Streamlit Web 入口 + CSS + 路由 + re-export（~267行） |
| `main.py` | CLI 入口 |
| `ui/analyze_page.py` | 个股分析页面（股票名称搜索 + Enter 键搜索 + 指标图表） |
| `ui/hot_stocks_page.py` | 热门板块页面（行业/概念排行 + 涨跌幅榜） |
| `ui/recommend_page.py` | 智能推荐页面（短线/长线龙头股推荐） |
| `ui/compare_page.py` | 股票对比页面（多股票指标横向对比 + 走势决策仪表盘） |
| `ui/sidebar.py` | 侧边栏组件（大盘温度 + 自选股 + mini 面板） |
| `ui/ai_analysis_ui.py` | AI 分析 UI（API 配置 + 单/多Agent 结果渲染） |
| `ui/charts.py` | Plotly 图表（K线/RSI/KDJ/BOLL/分时图） |
| `ui/cached_data.py` | 缓存数据层（fetcher 实例 + @st.cache_data 函数） |
| `data_fetcher.py` | 多源数据获取 + 健康检查 + 离线缓存 + 全量A股名称索引 |
| `data/` | 新分层数据服务（providers/services/cache/health/models），逐步承接行情、基础资料、研报、信号、新闻、公告等接口 |
| `reports/` | 每日 Markdown 决策仪表盘（大盘温度、自选股、推荐股、研报、风险事件、板块归因、操作检查清单） |
| `technical_indicators.py` | 技术指标计算 |
| `ai_analysis.py` | AI 智能解读（多Agent：技术+风险+决策） |
| `chart_plotter.py` | Matplotlib 图表（CLI） |
| `chart_utils.py` | 共享图表工具 |
| `stock_recommendation.py` | 热门排行 + 板块排行 + 评分推荐 |
| `backtest_engine.py` | 回测引擎 |
| `backtest_adapter.py` | 回测信号适配 |
| `backtest_ui.py` | 回测 Web UI |
| `notification.py` | 通知推送（企业微信/飞书/Telegram/Bark） |
| `api_server.py` | FastAPI 服务（飞书机器人回调 + 股票查询 API） |
| `scheduler.py` | 定时调度 |
| `config.py` | 集中配置 |
| `watchlist.py` | 自选股管理 |
| `tests/` | 测试（18 文件，567 测试） |

### 分层数据服务

项目已开始按 `a-stock-data` 的接口分层思路拆分数据层，但不会直接照搬外部仓库实现：

- `data/providers/`：外部数据源适配器，目前包含 AKShare 个股基础资料、财务摘要/资金流/新闻、腾讯行情估值补充，以及旧行情获取器适配层 `LegacyQuoteProvider`。
- `data/services/`：业务接口层，目前提供 `FundamentalDataService.get_stock_profile()`、`QuoteDataService` 和 `StockInfoService`。
- `data/cache.py`：统一 JSON 文件缓存，默认落到 `.cache/`。
- `data/health.py`：数据源健康状态登记，后续用于多源 fallback。
- `data/models.py`：标准数据模型，当前包含 `StockProfile`。
- `data/runtime.py`：统一第三方接口超时包装和非关键数据源安全调用。

当前 Web 个股分析页会并行请求基础资料，不阻塞 K 线主数据渲染。行情相关入口（K线、实时行情、分时、批量报价、大盘指数、数据源选择）已先收敛到 `QuoteDataService`，后续可以继续把新浪、腾讯、AKShare 等源拆成独立 provider。
个股页还会以非阻塞方式加载“财务 / 资金 / 新闻”折叠区；这些扩展信息失败时不会影响 K 线和技术分析主流程。

### 每日分析报告

`reports/DailyReportService` 复用现有 `QuoteDataService`、`StockInfoService` 和 `StockRecommender`，按 `daily_stock_analysis` 项目的“每日 Markdown 复盘/决策仪表盘”思路补齐本项目目标能力，但保持无数据库、无额外服务依赖：

- 大盘温度：读取上证、深证、沪深300、北证50 实时摘要。
- 自选股摘要：复用 `watchlist.json` 和现有自选股汇总逻辑。
- 今日推荐：默认取短线推荐前 5，只在 CLI 生成报告时执行。
- 研报层：对自选股中的 A 股补充东财个股研报、PDF 链接和同花顺一致预期 EPS。
- 风险事件层：补充龙虎榜、限售解禁和近 30 日个股公告，风险公告会进入风险警报。
- 板块归因层：补充行业/概念归属、板块涨跌幅和简单题材原因。
- 决策面板：输出决策评分、买卖点、风险警报、催化因素和操作检查清单。
- 导出结果：写入 `reports/history/YYYY-MM-DD.md`，并同步覆盖 `reports/history/latest.md`。

定时推送复用 `scheduler.py`：配置 `NOTIFY_CHANNELS` 和对应 webhook 后运行 `python main.py --schedule`，每天 `SCHEDULE_TIME` 会按“自选股摘要 → 四板块推荐 → 每日完整 Markdown 日报”的顺序执行。四板块固定为算力租赁、电力、苹果概念、特斯拉概念，默认每个板块推送短线 2 只 + 长线 1 只；推荐股推送仅包含沪深主板股票，创业板、科创板、北交所不进入推荐池；热门板块页的行业板块、概念板块、个股涨跌幅榜保留全市场，不做主板过滤；不再用全市场推荐股作为补充推送内容。若只想保存日报不推送正文，可设置 `DAILY_REPORT_PUSH_ENABLED=false`。

GitHub Actions 已启用工作日北京时间 `15:30` 定时运行 `.github/workflows/daily_analysis.yml`。配置仓库 Secrets（`NOTIFY_CHANNELS`、`WECHAT_WEBHOOK_URL` 或 `FEISHU_WEBHOOK_URL`）后，不需要本地电脑常开。

## 指标说明

### 新股/短历史数据

如果股票上市时间较短（例如新股/次新股），数据源只能返回上市后的交易日数据。此时页面会显示说明性提示，而不是错误告警：

- 长周期指标（如 `MA20` / `MA60` / `RSI24` / `BOLL`）可能暂不完整。
- 建议优先参考分时图、价格走势和短线指标。
- 等交易日数据积累后，长周期指标会自动恢复完整计算。

### MACD
- **金叉**：MACD 线上穿信号线，买入信号
- **死叉**：MACD 线下穿信号线，卖出信号
- **柱状图**：MACD 与信号线的差值，反映动量

### RSI（6/12/24 三周期）
- **>70**：超买区域，可能回调
- **<30**：超卖区域，可能反弹
- **30-70**：正常区间

### KDJ
- **K 线**（快线）反映近期价格变动
- **D 线**（慢线）反映价格趋势
- **J 线** = 3K - 2D，波动最大
- **金叉**：K 上穿 D，买入信号
- **死叉**：K 下穿 D，卖出信号

### 布林带
- **上轨**：压力位
- **中轨**：20 日均线，支撑/压力位
- **下轨**：支撑位
- **带宽扩大**：波动加剧
- **带宽收窄**：可能变盘

## 评分系统

推荐股票的评分基于以下因子（总分 0-100）：

- **80-100**：偏多信号（强）
- **65-79**：偏多信号
- **50-64**：观望
- **35-49**：偏空信号
- **0-34**：偏空信号（强）

## 注意事项

1. **数据来源**：A股 AKShare/新浪财经，港美股 新浪财经/Yahoo Finance
2. **网络连接**：程序需要联网获取实时数据
3. **风险提示**：技术分析仅供参考，不构成投资建议
4. **数据延迟**：免费数据可能有 15-30 分钟延迟
