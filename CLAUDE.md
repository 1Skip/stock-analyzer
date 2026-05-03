# CLAUDE.md

本文件用于项目协作，帮助快速理解项目结构和约定。

## 1. 项目概览

股票技术分析系统，支持 A股/港股/美股，提供 Streamlit Web 界面和 CLI 两种使用方式。

核心流程：获取数据 → 计算技术指标 → 生成交易信号 → 图表展示

**语言约定**：本项目为中文项目，所有输出（文字、注释、commit message、UI 文案）均使用中文。

## 2. 文件说明

| 文件 | 职责 | 备注 |
|------|------|------|
| `app.py` | Streamlit Web UI | ~1929行，K线图用 Plotly（go.Candlestick 三合图），指标图用 Plotly，分时图用 Plotly |
| `main.py` | CLI 入口 | 交互式菜单 + argparse 命令行 |
| `data_fetcher.py` | 数据获取 | A股: AKShare → 新浪 → yfinance；港股: yfinance K线 + 新浪实时；美股: 新浪 K线 → yfinance。带健康检查、离线缓存、超时保护 |
| `technical_indicators.py` | 技术指标计算 | MACD / RSI(6/12/24) / KDJ / BOLL / MA，纯 pandas 实现 |
| `ai_analysis.py` | AI 智能解读 | 提取指标快照 → LLM 翻译为自然语言，支持多Agent协作（技术+风险+决策） |
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
| `tests/` | 测试（18文件，478测试） | conftest.py 含完整 Streamlit mock（含 plotly_chart），pytest.ini 含 slow/network 标记 |
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
- **缓存策略**：Streamlit `@st.cache_data`，ttl 10-600 秒，从 `config.py` 常量读取
- **数据源优先级**：A股 AKShare > 新浪 > yfinance；港股 yfinance K线 + 新浪实时；美股 新浪 K线 > yfinance
- **数据源健康检查**：连续失败 3 次标记为不健康，`HEALTH_SKIP_PROBABILITY` 控制随机跳过
- **离线模式**：所有在线源失败时，使用 `.stock_cache.json` 24 小时内缓存
- **通知推送**：默认关闭，通过 `NOTIFY_CHANNELS` 环境变量开启（企业微信 webhook）
- **定时调度**：默认关闭，通过 `SCHEDULE_ENABLED=true` 开启，`SCHEDULE_TIME` 设定执行时间
- **飞书机器人**：默认关闭，通过 `FEISHU_BOT_ENABLED=true` 开启 FastAPI 回调服务

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

- `app.py` 较长（~1929行），可拆分为 `app_ui.py` + `app_charts.py`，但当前优先级低
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
- **绝对不要**将 token、密码、API key 提交到 git（参见[安全注意事项](#12-安全注意事项)）

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
- 如需推送脚本，确认 token 从安全的途径获取，不要硬编码
- 用户间共享这些脚本时，告知不要包含私有信息
