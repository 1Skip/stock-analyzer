# 2026-08-06 取消本机自动运行

## 用户要求

- 取消 `stock_analyzer` 在 Windows 登录后的开机自启动。
- 取消每周一运行的短线闭环学习阶段检查。

## 已完成

- 删除 Windows 启动文件夹中的 `Stock Analyzer.lnk`。删除前确认该快捷方式指向 `C:\Users\skip8\stock_analyzer\start.bat`，工作目录为项目根目录。
- 删除 Codex 自动任务“短线闭环学习阶段检查”。该任务原定每周一 09:30 在本项目本地目录中运行，只检查和报告学习阶段。
- 没有删除 `install_startup.bat`、`uninstall_startup.bat` 或 `start.bat`，因此项目仍保留手动启动和重新启用开机启动的能力。
- 没有修改调度器、短线学习、推荐股票池、过滤、评分、排序、T+1 缓存或其他策略语义。

## 现场核验

- Windows 启动文件夹已不存在 `Stock Analyzer.lnk`，仅保留其他无关启动项。
- 注册表 `Run` / `RunOnce`、Windows 计划任务和 Windows 服务中均未发现指向本项目、`start.bat` 或 `main.py --schedule` 的其他自动启动入口。
- Codex 自动任务配置文件已不存在，删除操作返回 `deleted`。
- 取消时调度器仍有工作进程并持有实例锁；按用户要求只取消后续自动运行，没有强制终止当日已运行服务。关机或手动退出后，它不会再由 Windows 启动入口恢复。

## 恢复方式

- 如需恢复 Windows 登录自启动，可重新运行 `install_startup.bat`。
- 如需恢复每周短线学习检查，需要重新创建 Codex 自动任务。
