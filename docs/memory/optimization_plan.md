---
name: optimization plan
description: 当前项目优化待处理清单，区分已处理项、保留观察项和后续建议。
type: project
originSessionId: 35a65abf-4e04-45e9-9335-f14881646c5d
updated: 2026-06-25
---

# 项目优化待处理清单

## 本轮已处理

1. 文档/规则乱码巡检
   - 确认 `agent.md`、`pytest.ini`、`.github/workflows/test.yml`、`docs/memory/optimization_plan.md` 文件内容本身可按 UTF-8 读取；PowerShell 乱码属于终端显示编码问题。
   - 修正 Codex Skill 中过期的推荐策略描述：短线只保留 `全部 / 苹果概念 / 特斯拉概念`，激进突破型和多因子稳健型只使用 `全部`。
   - 将本清单重写为正常 UTF-8 中文，降低后续协作误读风险。

2. 静态检查配置固化
   - 新增 `pyproject.toml`，把 ruff 高信号规则 `E9,F63,F7,F82` 固化到仓库配置。
   - GitHub Actions 改为执行 `ruff check .`，由仓库配置决定规则，避免 README/CI/本地命令分叉。

3. 编码检查加强
   - 扩展 `scripts/check_doc_encoding.py`，检查 `README.md`、`agent.md`、`docs/`、`.codex/`、`.github/` 和 `pytest.ini`。
   - 检查范围从 Markdown 扩展到 `.md/.yml/.yaml/.ini`，并识别常见 mojibake 乱码标记。
   - 新增 `tests/test_doc_encoding_check.py`，覆盖乱码识别和正常中文 ini。

4. 工作区杂物处置
   - 清理未跟踪的误写路径副本 `Users/skip8/stock_analyzer/docs/memory/bug_fixes_and_context_2026-06-23.md`。
   - 清理未跟踪的临时分析图片 `tmp_kangsheng_analysis.png`。

5. 换行符状态降噪
   - 新增 `.gitattributes`，统一文本文件使用 LF，Windows 批处理和 VBS 脚本保留 CRLF。
   - `stock_recommendation.py` 可能仍在当前未刷新索引中显示为 modified，但 `git diff --name-only` 不再列出内容 diff。

6. 数据源异常诊断收敛
   - 将 `data_fetcher.py` 中日 K、实时行情、批量行情、指数行情关键入口的 `print(...)` 和部分静默 `pass` 收敛为 `logger.info/debug/warning`。
   - 将 `stock_recommendation.py` 中板块榜和短线分析跳过原因收敛为日志，保留模块末尾 CLI demo 的 `print(...)` 和子进程 JSON 输出。
   - 不改变数据源优先级、fallback 顺序、缓存策略、推荐条件、评分或排序。

7. 离线数据契约快检
   - 新增 `scripts/check_offline_data_contracts.py`，只校验 K 线、实时行情、指数行情、`StockProfile` 的字段结构和缺失状态。
   - 新增 `tests/test_offline_data_contracts.py`，覆盖缺失真实数据时的结构表达和破损结构拒绝。
   - 保留 `scripts/check_real_data_contracts.py --network` 作为显式联网真实数据抽样检查；离线脚本不访问网络、不写缓存、不构造假行情。

8. 本地测试噪音处理
   - `pytest.ini` 增加 `-p no:cacheprovider`，避免受工作区 `.pytest_cache` 权限/状态影响产生无关警告。

## 保留观察

1. 低风险大文件治理
   - 本轮仅抽出短线跳过日志 helper，没有拆分策略逻辑。
   - 后续若继续治理 `stock_recommendation.py`，优先拆纯展示、诊断文本、字段格式化和板块解析辅助函数；不得改推荐池、过滤条件、评分、排序或 T+1 语义。

2. 文档显示体验
   - PowerShell 默认编码仍可能把中文显示成乱码；文件内容和 CI 读取不受影响。
   - 若要改善人工查看体验，可后续补一段 Windows 终端 UTF-8 设置说明。

3. 真实数据契约
   - 离线结构快检已补齐。
   - 真实行情链路仍需在需要时显式运行 `scripts/check_real_data_contracts.py --network`，并按实际网络/API 状态解释结果。

## 当前建议

1. 短期可以先停止继续优化，观察 CI 和日常运行日志是否更清楚。
2. 下一轮若继续做，只建议围绕“纯展示/诊断/文档”动手，不建议在没有明确需求时碰推荐策略语义。
