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
