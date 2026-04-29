# CLAUDE.md

本文件用于项目协作，帮助快速理解项目结构和约定。

## 1. 项目概览

股票技术分析系统，支持 A股/港股/美股，提供 Streamlit Web 界面和 CLI 两种使用方式。

核心流程：获取数据 → 计算技术指标 → 生成交易信号 → 图表展示

**语言约定**：本项目为中文项目，所有输出（文字、注释、commit message、UI 文案）均使用中文。

## 2. 文件说明

| 文件 | 职责 | 备注 |
|------|------|------|
| `app.py` | Streamlit Web UI | ~1000行，包含 Plotly 图表函数和全部页面 |
| `main.py` | CLI 入口 | 交互式菜单 + argparse 命令行 |
| `data_fetcher.py` | 数据获取 | A股: AKShare → 新浪 → yfinance 三级回退，带健康检查和离线缓存 |
| `technical_indicators.py` | 技术指标计算 | MACD / RSI(6/12/24) / KDJ / BOLL / MA，纯 pandas 实现 |
| `chart_plotter.py` | Matplotlib 图表 | CLI 用，K线图 + 多指标子图 |
| `stock_recommendation.py` | 热门股票 + 评分推荐 | 含板块定义(苹果概念/特斯拉/电力/算力租赁)，多因子评分(0-100) |
| `watchlist.py` | 自选股管理 | 仅存 Streamlit session state，未持久化 |
| `debug_recommendation.py` | 调试脚本 | 引用的 `get_short_term_recommendations` 等方法可能不存在 |
| `sector_recommend.py` | 板块推荐入口 | 独立脚本，依赖 `holdings.json` 和 `sectors_config.json` |
| `requirements.txt` | 依赖 | streamlit / plotly / yfinance / pandas / numpy / requests / akshare |
| `.devcontainer/devcontainer.json` | Dev Container 配置 | Python 3.11，自动安装依赖并启动 Streamlit |
| `.gitignore` | Git 忽略规则 | 已配置：缓存、虚拟环境、敏感文件、base64 文件 |
| 根目录 `.bat` / `.vbs` / `.ps1` | 便捷启动脚本 | Windows 用户一键启动/安装/推送，详见[安全注意事项](#10-安全注意事项) |

## 3. 架构约定

- **Web 图表** → Plotly（在 `app.py` 中），交互式可缩放
- **CLI 图表** → Matplotlib（在 `chart_plotter.py` 中），静态图片
- **缓存策略**：Streamlit `@st.cache_data`，ttl 10-600 秒
- **数据源优先级**（A股）：AKShare(同花顺/东方财富) > 新浪财经 > Yahoo Finance
- **数据源健康检查**：连续失败 3 次标记为不健康，自动跳过
- **离线模式**：所有在线源失败时，使用 `.stock_cache.json` 24 小时内缓存

## 4. 技术指标细节

- **RSI**：6/12/24 三个周期，`rsi` 字段默认指向 `rsi_6`
- **KDJ**：标准递推公式，前 n-1 天 K=D=50，第 n 天 K=D=RSV
- **BOLL**：20 日中轨，2 倍标准差
- **MACD**：12/26/9 标准参数
- **MA**：5/10/20/60 四条均线
- **信号判断**：`TechnicalIndicators.get_signals()` 综合四个指标给出买入/卖出/观望

## 5. 数据字段规范

历史数据 DataFrame 列名已统一为小写：`open`, `high`, `low`, `close`, `volume`

指标列名：
- `rsi_6`, `rsi_12`, `rsi_24`, `rsi`
- `macd`, `macd_signal`, `macd_hist`
- `kdj_k`, `kdj_d`, `kdj_j`
- `boll_upper`, `boll_mid`, `boll_lower`, `boll_width`, `boll_percent`
- `ma5`, `ma10`, `ma20`, `ma60`

## 6. 已知问题（修改时注意）

- `stock_recommendation.py:99` 换手率用的是 `np.random.uniform()` 随机模拟数据
- `debug_recommendation.py` 调用 `get_short_term_recommendations()` 和 `get_sector_short_term_recommendations()` 可能报错 —— 已接近废弃
- `chart_plotter.py` 与 `app.py` 的图表逻辑重复，改图表需两边同步
- watchlist 无持久化，刷新页面丢失
- 港股/美股热门排行功能远弱于 A 股
- **根目录历史遗留文件**（可在确认无引用后清理）：
  - `app.py.b64` / `app.py.b64.clean` / `app.py.b64.oneline` —— 旧版 base64 备份
  - `update.json` / `update_github.py` / `update_github.bat` —— 旧版更新脚本
  - 多个功能重叠的 `.bat` / `.vbs` / `.ps1` 便捷脚本
- **项目当前无任何自动化测试**，详见测试策略建议（SKILL.md:testing-expert）

## 7. 常用命令

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

# 运行测试（如有）
pytest tests/ -v

# 检查依赖安全漏洞
pip-audit
```

## 8. 修改规则

- 不自动执行 `git commit` / `git push`，除非用户明确要求
- 修改 `requirements.txt` 前确认版本兼容性
- 涉及数据源变更时，要同时更新 health check 和 fallback 链
- 新增 Streamlit 页面时，在侧边栏导航中注册
- 图表修改：Plotly 和 Matplotlib 版本行为不同，建议改完后在 Web 和 CLI 都验证
- 修改技术指标计算逻辑后，必须用真实数据验证输出值范围（如 RSI 0-100、BOLL 上轨≥中轨≥下轨）
- 新增依赖需同时更新 `requirements.txt` 和 `.devcontainer/devcontainer.json`（如有硬编码依赖）
- **绝对不要**将 token、密码、API key 提交到 git（参见[安全注意事项](#10-安全注意事项)）

## 9. Agent Skills 使用指南

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

## 10. 安全注意事项

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
