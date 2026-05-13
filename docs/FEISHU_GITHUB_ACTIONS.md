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
| `AI_API_KEY` | AI 解读所需 API Key，没有也可以不填 |

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
