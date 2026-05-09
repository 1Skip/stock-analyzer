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
- Telegram Bot
- Bark（iOS 推送）
- 默认关闭，通过环境变量 `NOTIFY_CHANNELS` 开启

### 市场支持
- **A股** — AKShare → 新浪财经 → Yahoo Finance 三级回退
- **港股** — 新浪财经 → Yahoo Finance
- **美股** — 新浪财经 → Yahoo Finance

### 其他功能
- **热门股票** — 涨幅榜/跌幅榜/成交量榜 + 行业板块排行 + 概念板块排行
- **推荐股票** — 多因子技术分析评分（0-100），含短线/长线/板块推荐
- **股票对比** — 多只股票技术指标横向对比
- **回测引擎** — 信号→交易模拟，含止损/止盈/中性区间
- **大盘温度** — 上证/深证/沪深300/北证50 实时跟踪
- **自选股** — 持久化管理，支持 A股/港股/美股，侧边栏 mini 分析面板
- **定时调度** — 收盘后自动分析+推送（默认关闭）
- **飞书机器人** — 对话式股票查询（默认关闭）
- **三种配色** — A股传统（红涨绿跌）/ 国际惯例（绿涨红跌）/ 色盲友好（蓝涨橙跌）
- **离线缓存** — 所有在线源失败时使用 24h 缓存兜底

## 快速开始

### 安装

```bash
cd stock_analyzer
pip install -r requirements.txt
```

### Web 界面

```bash
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
```

### 运行测试

```bash
pytest tests/ -v                    # 全部测试
pytest tests/ -v -m "not network"   # 跳过网络测试（离线环境）
pytest tests/test_technical_indicators.py -v  # 单文件
```

## 项目结构

| 文件 | 职责 |
|------|------|
| `app.py` | Streamlit Web UI |
| `main.py` | CLI 入口 |
| `data_fetcher.py` | 多源数据获取 + 健康检查 + 离线缓存 |
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
| `tests/` | 测试（18 文件，514 测试） |

## 指标说明

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
