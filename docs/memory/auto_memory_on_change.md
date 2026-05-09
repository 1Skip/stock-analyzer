---
name: Auto-save memory and push
description: 每次代码改动后自动记录到 memory 并推送到 GitHub，无需用户提醒
type: feedback
---

每次代码改动提交后，自动更新 memory 文档记录修复内容，并推送到 GitHub。

**Why:** 用户不想每次都提醒我做这件事，应该是默认行为。

**How to apply:** 每次 `git commit` + `git push` 完成后，自动创建/更新对应的 memory 文件记录改动内容，然后再次 commit + push memory 变更。
