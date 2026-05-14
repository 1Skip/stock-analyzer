# GitHub Actions + 飞书 Webhook 云端推送

这个方案用于“电脑关机也能自动推送”。GitHub 会在工作日北京时间 15:30 云端运行项目，并把结果推送到飞书群。

## 1. 创建飞书群机器人

1. 打开目标飞书群。
2. 添加机器人，选择自定义机器人。
3. 复制 Webhook 地址，形如：

```text
https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
```

## 2. 配置 GitHub Secrets

进入 GitHub 仓库：

```text
Settings → Secrets and variables → Actions → New repository secret
```

新增：

| Secret 名称 | 值 |
|------|------|
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook |

可选：

| Secret 名称 | 值 |
|------|------|
| `STOCK_LIST` | 云端日报使用的自选股，逗号分隔，推荐 |
| `WATCHLIST_JSON` | 云端日报使用的高级自选股 JSON |
| `AI_API_KEY` | LLM 多空辩论所需 API Key，没有也可以不填 |
| `AI_BASE_URL` | 可选，自定义 LLM API 地址 |

如需开启 LLM 多空辩论，还要进入：

```text
Settings → Secrets and variables → Actions → Variables
```

新增：

| Variable 名称 | 值 |
|------|------|
| `AI_DEBATE_ENABLED` | `true` |
| `AI_MODEL` | 可选，默认 `deepseek/deepseek-chat` |
| `AI_DEBATE_MAX_SYMBOLS` | 可选，默认 `3` |

不开启 `AI_DEBATE_ENABLED` 时，日报仍会使用本项目的五层 A股决策委员会，不依赖外部 LLM。

`STOCK_LIST` 示例：

```text
600519,600036,000001
```

也支持中文名称和市场前缀：

```text
贵州茅台,招商银行,CN:平安银行,HK:00700,US:AAPL
```

A 股中文名称会先用内置全量名称索引解析，再尝试在线刷新；如果仍未识别，Actions 会在“写入自选股 Secret”步骤直接报错并提示改用 6 位代码，避免把中文名称误当股票代码查询。

如果同时配置 `WATCHLIST_JSON` 和 `STOCK_LIST`，优先使用 `WATCHLIST_JSON`。

`WATCHLIST_JSON` 高级格式示例：

```json
[
  {
    "symbol": "600519",
    "name": "贵州茅台",
    "market": "CN"
  },
  {
    "symbol": "600036",
    "name": "招商银行",
    "market": "CN"
  }
]
```

如果不配置 `STOCK_LIST` 或 `WATCHLIST_JSON`，云端日报会显示“暂无自选股”。本地网页里的 `watchlist.json` 默认不会提交到 GitHub，因此 GitHub Actions 不能自动读取你本地电脑的自选股。

## 3. 运行方式

工作流文件：

```text
.github/workflows/daily_analysis.yml
```

触发方式：

- 工作日北京时间 15:30 自动运行。
- GitHub Actions 页面手动点击 `Run workflow` 立即测试。

## 4. 推送内容

每次运行会按顺序推送：

1. 自选股摘要。
2. 四板块推荐：算力租赁、电力、苹果概念、特斯拉概念。
3. 每日完整 Markdown 决策日报。

推荐股推送仅包含沪深主板股票；热门板块排行仍保留全市场观察。

完整日报包含：

- A股决策委员会评分、仓位、风险等级、置信度。
- 买卖点、关键价位、看多依据、风险警报、催化因素。
- 研报、公告、龙虎榜、限售解禁、行业/概念归因。
- 可选 LLM 多空辩论：多头研究员、空头研究员、风控经理裁决。

飞书卡片会自动把超长 Markdown 拆成多个元素，避免日报过长导致推送失败。

## 5. 常见问题

### 没有收到飞书消息

检查：

1. `FEISHU_WEBHOOK_URL` 是否配置到 GitHub Secrets。
2. 飞书机器人是否仍在群里。
3. GitHub Actions 运行日志中是否有 `FEISHU_WEBHOOK_URL` 缺失或飞书返回错误。

### 电脑关机后还能推送吗

可以。这个方案运行在 GitHub 云端，不依赖本地电脑。

### 能实时对话吗

不能。这个是飞书 Webhook 主动推送方案；实时对话需要飞书事件订阅和公网回调服务。
