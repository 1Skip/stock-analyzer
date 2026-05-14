# CLAUDE.md

本文件用于项目协作，帮助快速理解项目结构和约定。

## 1. 项目概览

股票技术分析系统，支持 A股/港股/美股，提供 Streamlit Web 界面和 CLI 两种使用方式。

核心流程：获取数据 → 计算技术指标 → 生成交易信号 → 图表展示

**语言约定**：本项目为中文项目，所有输出（文字、注释、commit message、UI 文案）均使用中文。

## 2. 文件说明

| 文件 | 职责 | 备注 |
|------|------|------|
| `app.py` | Streamlit Web 入口 | ~100行，页面配置 + CSS注入（2行）+ 路由 + re-export（兼容测试） |
| `stock_names.py` | 股票名称静态映射表 | ~200只A股 + 热门美股列表，data_fetcher 导入使用 |
| `chart_utils.py` | 共享图表工具 | 配色解析、成交量/MACD着色、MA配置、classify_signal，供 Web 和 CLI 共用 |
| `ui/styles.py` | CSS 样式定义 | ~207行，Apple × Tesla 设计体系，app.py 导入注入 |
| `ui/cached_data.py` | 缓存数据层 | quote_service/fundamental_service 实例 + 股票数据/实时行情/分时/名称解析等 @st.cache_data 函数 |
| `ui/charts.py` | 图表函数 | K线/RSI/KDJ/BOLL/分时图，Plotly 实现 |
| `ui/ai_analysis_ui.py` | AI 辅助解读 UI | 默认折叠，可选启用；API 配置表单 + 单Agent/多Agent 解释补充 |
| `ui/sidebar.py` | 侧边栏组件 | 大盘温度、自选股列表、mini 分析面板、数据源选择 |
| `ui/committee_status.py` | 决策委员会状态卡片 | 侧边栏展示阶段 1-5、飞书、Actions、LLM 辩论开关 |
| `ui/analyze_page.py` | 个股分析页面 | 输入表单 + 股票名称搜索 + Enter键搜索 + 信号/指标卡片 + 图表渲染 |
| `ui/hot_stocks_page.py` | 热门板块页面 | 行业/概念排行 + 涨跌幅榜 |
| `ui/recommend_page.py` | 智能推荐页面 | 短线/长线龙头股推荐 |
| `ui/compare_page.py` | 股票对比页面 | 多股票指标对比 + 收益/回撤/波动/相对强弱走势仪表盘 |
| `main.py` | CLI 入口 | 交互式菜单 + argparse 命令行 |
| `data_fetcher.py` | 数据获取 | A股: AKShare → 新浪 → yfinance；港股: yfinance K线 + 新浪实时；美股: 新浪 K线 → yfinance。带健康检查、离线缓存、超时保护、全量A股名称索引 |
| `data/` | 分层数据服务 | providers/services/cache/health/models/runtime；已接入 A股基础资料/估值、行情服务接缝、财务摘要/资金流/新闻扩展信息 |
| `decision_committee.py` | A股决策委员会 | 借鉴 TradingAgents 多角色框架，阶段 1 最终版五层 Agent：技术分析、资金情绪、基本面、题材板块、风险事件；含权重、置信度、关键位和细分评分 |
| `ui/decision_dashboard.py` | 个股页决策仪表盘 | 阶段 2 最终版展示层：综合评分 Hero、仓位/买卖点、关键价位、催化因素、看多/看空/风险列表和五层 Agent 折叠明细 |
| `reports/` | 每日报告服务 | `DailyReportService` 汇总大盘、自选股、推荐股、研报、风险事件、板块归因、操作检查清单，`exporter.py` 导出 Markdown |
| `technical_indicators.py` | 技术指标计算 | MACD / RSI(6/12/24) / KDJ / BOLL / MA，纯 pandas 实现 |
| `ai_analysis.py` | AI 辅助解读 | 提取指标快照 → LLM 翻译为自然语言解释，支持技术/风险/决策协作和A股多空研究员+风控经理辩论层；主结论以 A股决策委员会 为准 |
| `chart_plotter.py` | Matplotlib 图表 | CLI 用，K线图 + 多指标子图 |
| `chart_utils.py` | 共享图表工具 | 配色解析、成交量/MACD着色、MA配置，供 Web 和 CLI 共用 |
| `stock_recommendation.py` | 热门股票 + 评分推荐 | 含板块定义，多因子评分(0-100)，支持 CN/US/HK |
| `notification.py` | 通知推送 | 企业微信 webhook，`build_analysis_report()` 格式化报告 |
| `config.py` | 集中配置 | 所有参数 + 三种配色 + 评分权重 + 信号阈值 + 调度/通知，环境变量覆盖 |
| `watchlist.py` | 自选股管理 | 持久化到 watchlist.json，session_state 做缓存，含侧边栏 mini 分析面板 |
| `scheduler.py` | 定时调度 | 收盘后自动分析+通知，通过 `SCHEDULE_ENABLED` 开启 |
| `backtest_engine.py` | 回测引擎 | 信号→交易模拟，含止损/止盈/中性区间 |
| `backtest_adapter.py` | 回测适配 | 连接信号体系与回测引擎 |
| `backtest_ui.py` | 回测 UI | Streamlit 回测页面 |
| `api_server.py` | FastAPI 服务 | 飞书机器人回调 + 股票查询 API（可选，`FEISHU_BOT_ENABLED` 控制） |
| `tests/` | 测试（18文件，567测试） | conftest.py 含完整 Streamlit mock（含 plotly_chart），pytest.ini 含 slow/network 标记 |
| `pytest.ini` | pytest 配置 | testpaths=tests, 注册 slow/network 标记, --tb=short |
| `requirements.txt` | 依赖 | streamlit / plotly / yfinance / pandas / numpy / requests / akshare / fastapi / uvicorn（飞书机器人可选） |
| `.devcontainer/devcontainer.json` | Dev Container | Python 3.11，自动安装依赖并启动 Streamlit |
| `.gitignore` | Git 忽略规则 | 缓存、虚拟环境、.env、token 文件、base64 文件 |

## 3. 架构约定

- **Web K线图** → Plotly `go.Candlestick` + `go.Bar` + `go.Scatter`，三合图（价格+成交量+MACD），通过 `st.plotly_chart` 渲染
- **Web 分时图** → Plotly（仅A股），价格折线+均价线+昨收线+成交量柱
- **Web 指标图** → Plotly（RSI/KDJ/BOLL 子图），交互式可缩放
- **CLI 图表** → Matplotlib（在 `chart_plotter.py` 中），静态图片
- **超时保护**：所有数据获取调用通过 `concurrent.futures.ThreadPoolExecutor` 包装超时（stock_info 5s / K线数据 20s / 实时行情 3s / 全市场快照 8s），超时后降级到已获取数据继续渲染
- **A股名称搜索**：优先使用 AKShare `stock_info_a_code_name()` 构建全量 A 股名称索引（5515+ 只），持久化到 `.cache/stock_name_index.json`，24h 内复用；同时提交 `data/static/stock_name_index.json` 作为 GitHub Actions/离线兜底，不再靠“报一个补一个”
- **A股基础资料兜底**：`FundamentalDataService` 会构建并缓存全量基础资料索引，组合东方财富全量快照、上交所主板/科创板、深交所 A 股、北交所列表；当个股基础接口只返回 `-`、`----` 或北交所“已切换”旧代码时，按代码/股票名称补齐行业、上市日期、股本、市值和 PB
- **缓存策略**：Streamlit `@st.cache_data`，ttl 10-600 秒，从 `config.py` 常量读取
- **数据源优先级**：A股 AKShare > 新浪 > yfinance；港股 yfinance K线 + 新浪实时；美股 新浪 K线 > yfinance
- **分层数据服务**：新增 `data/providers/`、`data/services/`、`data/cache.py`、`data/health.py`、`data/models.py`、`data/runtime.py`，参考 `a-stock-data` 的接口分层思路，但按本项目渐进迁移；当前 `FundamentalDataService.get_stock_profile()` 返回标准 `StockProfile` dict，`QuoteDataService` 统一承接 K线、实时行情、分时、批量报价、大盘指数和数据源切换，`StockInfoService` 承接财务摘要/资金流/新闻/市场资讯；个股新闻兼容 AKShare + pandas/pyarrow 字符串存储差异
- **基础资料/估值**：A股个股分析页并行调用 `get_cached_stock_profile()`，AKShare 获取股票简称/行业/上市日期/股本/市值，腾讯行情补 PE/PB/换手率，辅助数据最多短暂等待，不阻塞 K线主流程
- **扩展信息非阻塞**：个股页“财务 / 资金 / 新闻”和“市场快讯 / 催化消息”走 `get_cached_stock_extended_info()`，Web 首屏拉取财务、资金流、东方财富个股新闻和财新数据通市场资讯核心层，最多短暂等待；失败返回加载提示，不影响主图表和技术指标
- **每日报告**：`reports/DailyReportService` 复用分层服务生成 Markdown 决策仪表盘，CLI 通过 `python main.py --daily-report` 触发，默认输出 `reports/history/YYYY-MM-DD.md` 和 `latest.md`；推荐股扫描可用 `--no-report-recommendations` 关闭以便快速验证
- **研报/风险/板块扩展**：`AkShareInfoProvider` 已扩展东财研报/PDF、同花顺一致预期 EPS、龙虎榜、限售解禁、个股公告、行业/概念归因、财新数据通市场资讯；全部作为非关键数据源，失败返回空结构，不阻塞 K 线、Web 页面或日报生成
- **A股决策委员会**：`decision_committee.py` 作为 TradingAgents Lite 阶段 1 最终版，使用五层 Agent 产出评分、置信度、仓位、买卖点、风险警报和催化因素；技术层加入 MA/BOLL 关键位，资金层加入主力/5日/超大单/换手/龙虎榜，基本面层加入利润/现金流/EPS/PE/PB/市值，题材层加入行业与概念强度，风险层加入 ST/退市标识、解禁、风险公告和偏空信号；个股页 `ui/decision_dashboard.py` 已完成阶段 2 最终版产品化展示；日报 `DailyReportService` 已完成阶段 3 最终版决策仪表盘输出；`ai_analysis.py` 已完成阶段 4 最终版可选 LLM 多空辩论/风控经理层，未配置 `AI_API_KEY` 时自动跳过
- **网页端状态可见性**：`ui/committee_status.py` 在侧边栏固定展示阶段 1-5 接入状态、飞书 Webhook、GitHub Actions 和 LLM 辩论开关，不依赖行情请求，避免拖慢切页。
- **日报定时推送**：`scheduler.py` 默认按“自选股摘要 → 固定四板块推荐 → 每日完整 Markdown 日报”执行；四板块为算力租赁、电力、苹果概念、特斯拉概念，默认每板块短线 2 只 + 长线 1 只；智能推荐和推荐股推送仅包含沪深主板股票，创业板、科创板、北交所不进入推荐池；热门板块页的行业板块、概念板块、个股涨跌幅榜保留全市场观察，不做主板过滤；定时推送不再用全市场推荐股补充内容，`DAILY_REPORT_INCLUDE_RECOMMENDATIONS` 默认 `false` 以避免收盘后定时推送被推荐股全市场扫描拖慢
- **GitHub Actions 飞书定时推送**：`.github/workflows/daily_analysis.yml` 工作日北京时间 15:30 运行 `python main.py --notify`，默认 `NOTIFY_CHANNELS=feishu`；配置 `FEISHU_WEBHOOK_URL` Secret 后可云端自动推送日报，配置 `STOCK_LIST`（逗号分隔，支持 A 股代码/中文名）或高级 `WATCHLIST_JSON` Secret 后云端日报会包含自选股；阶段 5 最终版支持通过 Variables `AI_DEBATE_ENABLED=true` + Secret `AI_API_KEY` 在云端启用 LLM 多空辩论；中文名解析失败会直接报错，不再误用中文名查询行情
- **数据源健康检查**：连续失败 3 次标记为不健康，`HEALTH_SKIP_PROBABILITY` 控制随机跳过
- **离线模式**：所有在线源失败时，使用 `.cache/stock_cache.json` 24 小时内缓存，并兼容读取旧根目录 `.stock_cache.json`
- **通知推送**：默认关闭，通过 `NOTIFY_CHANNELS` 环境变量开启（企业微信 webhook）
- **定时调度**：默认关闭，通过 `SCHEDULE_ENABLED=true` 开启，`SCHEDULE_TIME` 设定执行时间
- **飞书机器人**：默认关闭，通过 `FEISHU_BOT_ENABLED=true` 开启 FastAPI 回调服务；命令解析支持 `/analysis 600519`、`/analysis 贵州茅台`、`分析贵州茅台`、`查 招商银行` 等代码/中文名称输入

## 4. 技术指标细节

- **RSI**：6/12/24 三个周期，`rsi` 字段默认指向 `rsi_6`
- **KDJ**：标准递推公式，前 n-1 天 K=D=50，第 n 天 K=D=RSV
- **BOLL**：20 日中轨，2 倍标准差
- **MACD**：12/26/9 标准参数
- **MA**：5/10/20/60 四条均线
- **信号判断**：`TechnicalIndicators.get_signals()` 综合四个指标给出偏多信号/偏空信号/观望

## 5. 数据字段规范

历史数据 DataFrame 列名已统一为小写：`open`, `high`, `low`, `close`, `volume`

指标列名：
- `rsi_6`, `rsi_12`, `rsi_24`, `rsi`
- `macd`, `macd_signal`, `macd_hist`
- `kdj_k`, `kdj_d`, `kdj_j`
- `boll_upper`, `boll_mid`, `boll_lower`, `boll_width`, `boll_percent`
- `ma5`, `ma10`, `ma20`, `ma60`

## 6. 已知问题（修改时注意）

- ~~`app.py` 较长（~1929行）~~ → 已拆分为 `ui/` 目录下 8 个模块，app.py 精简到 ~267 行
- `main.py` 尚未集成 `--schedule` / `--notify` 参数

## 7. 常见错误与解决方案

以下是本项目开发过程中实际遇到的问题及已验证的解决方法。遇到类似问题先查此表，避免重复踩坑。

### 7.1 环境与编码

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| `python` 命令返回 exit code 49（Windows） | Windows App Store Python Alias 拦截了 `python` 命令，指向假 Python | 使用完整路径：`/c/Users/skip8/AppData/Local/Programs/Python/Python314/python.exe`，或在设置中禁用 App Execution Alias |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0x88` | Windows 默认编码为 GBK，`open(file)` 未指定编码 | 所有 `open()` 调用显式指定 `encoding='utf-8'` |
| matplotlib 中文显示为方块 | 未配置中文字体 | 设置 `plt.rcParams['font.sans-serif'] = ['SimHei', ...]` 和 `plt.rcParams['axes.unicode_minus'] = False` |

### 7.2 数据计算边界

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| RSI 返回 NaN（停牌/一字板） | `avg_gain == 0 and avg_loss == 0` 导致 `0/0 → NaN` | 除零保护：`rsi_val[(avg_gain == 0) & (avg_loss == 0)] = 50` |
| KDJ 返回 NaN（涨停/跌停） | `high == low` 导致 `price_range == 0`，除零 | 用 `price_range.replace(0, np.nan)` 将零替换为 NaN，再用 `rsv.fillna(50)` 填充 |
| `df['rsi']` 列不存在（自定义 RSI 周期时） | `calculate_rsi` 中 `df['rsi'] = df['rsi_6']` 硬编码了 `rsi_6` | 改为动态引用第一个周期：`df['rsi'] = df[f'rsi_{periods[0]}']` |

### 7.3 DataFrame 序列化

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| 离线缓存加载后索引变成普通列 | `pd.DataFrame.to_dict()` 丢失 DatetimeIndex | 使用 `df.to_json(orient='split', date_format='iso')` 保存，`pd.read_json(raw, orient='split')` 加载，并向后兼容旧 dict 格式 |
| 缓存 DataFrame 无法 `.iloc` 按日期索引 | 同上，索引丢失 | 加载后用 `pd.to_datetime()` 重建 DatetimeIndex |

### 7.4 Streamlit 状态管理

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| 页面首次加载空白，需手动点按钮 | Streamlit 全量重跑，数据未自动加载 | 使用 `st.session_state.xxx_loaded` 标志位，首次进入自动触发数据加载 |
| 侧边栏操作后页面状态丢失 | 每次交互全量重跑，局部变量全部重置 | 所有跨交互状态存入 `st.session_state`，使用 `key` + `on_change` 回调同步 |
| 缓存装饰器 TTL 与 config 不一致 | 装饰器参数硬编码数字，config 导入后未使用 | 统一使用 `@st.cache_data(ttl=CONFIG_CONSTANT)` |

### 7.5 字符串匹配与信号语言

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| 信号匹配逻辑失效（如推荐列表关键信号为空） | 修改 `technical_indicators.py` 的信号字符串后，其他文件中用 `"买入" in signal` 等旧字符串匹配不到 | 修改信号文本后，**所有文件**中 grep 旧字符串并同步更新。特别注意 `main.py`（CLI）容易遗漏 |
| Edit 工具报 "String to replace not found" | 缩进/空格/全角半角与原文不完全一致 | 先用 Read 读取精确内容，复制粘贴整行（包括前后空格）到 old_string |

### 7.6 CSS 与配色

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| 暗色主题下卡片背景变白、文本不可读 | CSS 使用硬编码 `#ffffff`、`#f0f2f6` 等亮色值 | 改用半透明色 `rgba(128, 128, 128, 0.08)` 等，自动适配亮/暗背景 |
| 图表标记（金叉/死叉）颜色与配色方案不一致 | 标记色值硬编码 `#e53935`/`#2e7d32` | 从 `get_chart_colors()` 读取动态色值 |
| Web 图表配色改了但 CLI 图表没变 | `chart_plotter.py` 硬编码独立色值 | `chart_plotter.py` 从 `config.py` 导入配色方案，通过 `color_scheme` 参数选择 |

### 7.7 测试编写

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| 信号测试结果不稳定（同一 fixture 有时通过有时失败） | 测试 fixture 使用 `np.random` 生成 OHLC，随机性导致信号不确定 | 趋势类测试必须用确定性 OHLC（明确设定 open < close 或 open > close），仅非关键数据用随机值 |
| 新增指标后测试断言失败 | 测试中硬编码列名列表，新列未加入 | 测试应验证关键列存在即可，避免穷举列名 |

### 7.8 代码质量

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| `except:` 裸异常吞掉 KeyboardInterrupt | 使用裸 `except:` 而非 `except Exception:` | 始终使用 `except Exception:`，除非确实需要捕获所有异常（极其罕见） |
| 未使用的 import 堆积 | 多次修改后遗留 | 定期检查并移除未使用的 import |

### 7.9 数据获取

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| A股数据获取全部失败 | AKShare 网络超时或其他数据源不可用 | 检查三级回退链：AKShare → 新浪 → yfinance。全部失败则启用 `.stock_cache.json` 离线缓存（24h 有效） |
| 换手率显示 None | AKShare 全市场接口返回空或字段缺失 | 在 `stock_recommendation.py` 中从 `StockDataFetcher._get_spot_snapshot()` 获取，失败则返回 None（绝不使用随机模拟数据） |
| 全市场快照每次查询都下载 5000+ 行 | 未缓存快照结果 | 使用类级别 `_spot_cache` + 60 秒 TTL 缓存 |
| 股票代码能查但中文名称查不到 | 名称搜索依赖不完整静态映射表，代码查询无需名称库 | 使用 `stock_info_a_code_name()` 构建全量 A 股名称索引，缓存到 `.cache/stock_name_index.json`；名称匹配前做 NFKC/去空格规范化 |
| 实时行情调用阻塞页面加载 | `ak.stock_zh_a_spot_em()` 无超时参数，下载全市场数据可能耗时 5-15 秒 | 用 `ThreadPoolExecutor` 包装，`future.result(timeout=N)` 限制等待时间，超时降级到 K 线 fallback |
| 分时图在非交易日显示空白 | `_fetch_intraday_akshare` 未做当日过滤，返回上周数据；`plot_intraday_chart` 的 X 轴硬编码 `pd.Timestamp.now().date()` 导致数据点落在不可见区间 | 1) AKShare 源也加 `df['time'].dt.date == today` 过滤；2) X 轴刻度用数据实际日期而非当天日期；3) 数据为空时显示提示 |

### 7.10 测试 Mock 与依赖

| 错误现象 | 原因 | 解决方法 |
|---------|------|---------|
| `AttributeError: module 'streamlit' has no attribute 'plotly_chart'` | conftest.py 的 Streamlit mock 缺少 `plotly_chart` 属性 | 在 `_mock_st` 上添加 `_mock_st.plotly_chart = lambda fig, **kw: None` |
| `pd.date_range(end=dt.now(), periods=N, freq='B')` 生成 N-1 个日期 | `end` 落在周末时，pandas `freq='B'` 的 `periods` 参数会少生成 | 检查 `end_date.weekday() >= 5`，将 end_date 前移到周五 |
| 测试读到了项目的真实 `.stock_cache.json` | `StockDataFetcher` 类级别 `_offline_cache_file` 指向项目根目录 | 测试中使用 `tmp_path` fixture，将 `_offline_cache_file` 设为临时路径 |

## 8. 常用命令

```bash
# CLI 交互模式
python main.py -i

# 分析单只股票
python main.py -s 000001 -m CN -p 3mo

# 热门股票
python main.py --hot -m CN

# 推荐股票
python main.py --recommend

# 生成每日 Markdown 分析报告
python main.py --daily-report

# 快速验证日报结构（跳过推荐股扫描）
python main.py --daily-report --no-report-recommendations --report-dir reports/history

# 启动定时分析 + 摘要推送 + 每日 Markdown 日报推送
python main.py --schedule

# 启动 Web
streamlit run app.py

# 安装依赖
pip install -r requirements.txt

# 运行全部测试
pytest tests/ -v

# 跳过网络相关测试（离线环境）
pytest tests/ -v -m "not network"

# 只运行快速测试（跳过慢速网络测试）
pytest tests/ -v -m "not slow"

# 运行单个测试文件
pytest tests/test_technical_indicators.py -v

# 检查依赖安全漏洞
pip-audit
```

## 9. 修改规则

- 不自动执行 `git commit` / `git push`，除非用户明确要求
- 修改 `requirements.txt` 前确认版本兼容性
- 涉及数据源变更时，要同时更新 health check 和 fallback 链
- 新增 Streamlit 页面时，在侧边栏导航中注册
- 图表修改：Plotly 和 Matplotlib 版本行为不同，建议改完后在 Web 和 CLI 都验证
- 修改技术指标计算逻辑后，必须用真实数据验证输出值范围（如 RSI 0-100、BOLL 上轨≥中轨≥下轨）
- **所有网络调用必须加超时保护**：调用 AKShare / yfinance / 新浪等外部数据源时，用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=N)` 包装，超时后降级而非卡死。已在 `get_cached_stock_info`(5s) / `get_cached_stock_data`(20s) / `get_cached_realtime_quote`(3s) / `_get_spot_snapshot`(8s) 统一实现
- **绝对禁止使用模拟/随机/假数据**作为股票行情、价格、成交量、换手率等任何交易数据。所有数据必须从真实数据源获取（AKShare/新浪/yfinance）。`np.random`、`random` 等仅限用于网络退避抖动、测试夹具生成等非业务场景
- 新增依赖需同时更新 `requirements.txt` 和 `.devcontainer/devcontainer.json`（如有硬编码依赖）
- **所有对用户的汇报必须基于验证后的结论**：对用户说"X 是原因"之前，必须用代码/数据/测试实际验证过。不确定时就说不确定，然后去验证。禁止未经证实的猜测当作结论汇报
- **禁止假设性回答**：用户验证后发现不对才说"没解决"，说明之前的结论是猜的。提交修复前必须自己做完整数据流验证（用真实数据调核心函数），确认所有路径都通，再汇报。宁可说"我还没找到根因，正在排查"也不要说"应该修复了"
- **用户报bug时必须一次性修完，禁止反复修复**：
  1. 先完整追踪调用链（从 UI → 业务逻辑 → 数据源，每层都查），找到所有相关代码路径
  2. 必要时调用相关 skill（finance-ai-expert / python-data-expert / frontend-expert / architect-expert 等）协助分析
  3. 把所有问题一次性列出、一次性修复，而不是修一个→等用户验证→不行再修下一个
  4. 修完后自己跑一遍完整数据流验证（用真实数据调核心函数），确认所有路径都通，再汇报"已修复"
  5. 如果用户再次验证后仍然不对，说明分析不彻底，需要更深入排查而非表面修复
- **绝对不要**将 token、密码、API key 提交到 git（参见[安全注意事项](#12-安全注意事项)）
- **Memory 持久化规则**：
  1. 每次需求改动或 bug 修复完成后，必须将变更记录写入 memory（`~/.claude/projects/.../memory/`），并同步到仓库 `docs/memory/`
  2. 当对话上下文额度即将用尽时，必须将当前工作状态（已完成项、进行中项、待做项、关键代码变更）及时写入 memory
  3. 清空上下文后的新会话，首先从 memory 读取上次对话的最后记录，恢复工作状态后继续执行，完成后推送到 GitHub

## 10. 项目路线图

- **P0**（测试补齐）：✅ 完成，478 tests pass
- **P1**（调度+通知）：✅ 完成 — scheduler.py + notification.py 已实现
- **P2**（回测引擎）：✅ 完成 — backtest_engine.py + backtest_adapter.py + backtest_ui.py
- **P3**（多Agent AI）：✅ 完成 — 技术+风险+决策三Agent协作
- **P4**（质量优化）：✅ 完成 — 代码瘦身、死代码清理
- **P5**（大盘温度）：✅ 完成 — 沪深300+北证50+上证+深证
- **P6**（回测中文国际化）：✅ 完成
- **P7**（测试补齐第二轮）：✅ 完成 — 445→478 tests
- **P8**（自选股增强+飞书机器人）：✅ 完成 — watchlist mini面板 + api_server.py
- **P9**（自选股状态分离+mini面板+锚点滚动）：✅ 完成
- **P11**（K线图迁移Plotly）：✅ 完成 — lightweight-charts → Plotly

原则：保持 <8000 行（当前 ~6848 行业务代码 + ~6234 行测试），零数据库依赖，先 CLI 后 Web，新功能默认关闭。

## 11. Agent Skills 使用指南

本项目配置了 10 个项目级 Skill，按任务类型选择：

| 任务场景 | 使用 Skill | 典型任务 |
|---------|-----------|---------|
| 金融量化分析、策略设计、风控、回测 | `finance-ai-expert` | 因子分析、回测设计、风控建模、技术指标语义解读 |
| pandas/numpy 数据处理、数据获取、缓存 | `python-data-expert` | DataFrame 清洗、多源回退、缓存策略、性能优化 |
| Streamlit 界面开发、图表调整、布局 | `frontend-expert` | 页面布局、Plotly 图表、session_state 管理 |
| 技术指标计算、信号逻辑修改 | `finance-ai-expert` 或直接改 `technical_indicators.py` | 新增指标、调整参数、信号规则 |
| 数据源变更、回退链调整 | `python-data-expert` | 添加数据源、调整健康检查、切换优先级 |
| 系统架构、模块拆分、技术选型 | `architect-expert` | 模块重构、服务拆分、技术栈评估 |
| 后端 API、数据库、性能优化 | `backend-expert` | 数据库设计、API 开发、查询优化 |
| 测试编写、测试策略、质量保障 | `testing-expert` | 单元测试、DataFrame 断言、Mock 数据源 |
| UI/UX 设计、配色、布局优化 | `ui-ux-expert` | K线图配色、布局设计、金融图表 UX |
| 安全审计、漏洞修复、合规 | `security-expert` | 代码审计、依赖扫描、密钥管理 |
| CI/CD、部署、Docker、监控 | `devops-expert` | Docker 化、CI 流水线、自动化部署 |
| 产品规划、需求分析、功能优先级 | `pm-expert` | 功能 ROI 评估、路线图规划、需求文档 |

**选择原则**：
- 任务跨领域时优先选最核心的 skill，一次只用一个
- 简单修改（修 typo、改个变量名、加个日志）不需要 skill，直接改
- `python-data-expert` 和 `finance-ai-expert` 有部分重叠：数据处理走前者，金融语义走后者

**Skill 文件位置**：`.claude/skills/<skill-name>/SKILL.md`

## 12. 安全注意事项

### 敏感文件

| 文件 | 状态 | 处理 |
|------|------|------|
| `.github_token` | 已 gitignore，未跟踪 | 本地存在但不上传。**切勿移除 .gitignore 中的排除规则** |
| `.env` | 已 gitignore | 如有，存放 API key、数据库密码等，绝不提交 |
| `*.token` | 已 gitignore | 统配排除所有 token 文件 |

### 修改代码时的安全红线

- 绝对不要在代码中硬编码 token、密码、API key
- 环境变量用 `os.getenv()` 读取，在 `.env` 中配置，确认 `.env` 在 `.gitignore` 中
- `requirements.txt` 中的依赖保持版本锁定（或至少主版本），避免供应链攻击
- 新增文件前确认不是敏感文件（如不小心 `git add` 了 `.github_token`）

### Windows 便捷脚本安全

根目录的 `.bat` / `.vbs` / `.ps1` 脚本是给 Windows 小白用户的一键启动方案。注意：
- 这些脚本只封装 `python main.py` 或 `streamlit run`，不包含敏感操作
- `start.bat` 必须使用 `%~dp0` 相对项目目录，不允许硬编码本机路径
- 一键启动脚本会自动创建 `.venv` 并安装 `requirements.txt`，供别人下载后直接双击使用
- `install_startup.bat` 只创建 Windows 启动文件夹快捷方式；`uninstall_startup.bat` 只删除该快捷方式
- 如需推送脚本，确认 token 从安全的途径获取，不要硬编码
- 用户间共享这些脚本时，告知不要包含私有信息
