# 2026-07-20 Windows 开机调度器隐藏启动

## 已完成

- 确认 Windows 启动文件夹中只有一个 `Stock Analyzer.lnk`，没有对应计划任务；开机出现两个终端不是重复自启动，而是 `start.bat` 分别启动 Web 和调度器。
- 将 `start.bat` 中带标题的最小化调度终端改为 PowerShell `Start-Process -WindowStyle Hidden` 拉起的后台 `cmd` 进程。Windows 登录自启或双击脚本后只保留 Web 主终端，不再显示空白的 `Stock Analyzer Scheduler` 窗口。
- 保留原有调度器运行检测、`scheduler.out.log` / `scheduler.err.log` 追加重定向、PID 实例锁、每日 15:30 分析和 15:45 T+1 推荐计划预生成。
- 更新 Windows 启动入口回归测试，要求隐藏启动参数存在，并禁止旧的可见调度终端命令重新出现。
- 本次未修改推荐策略、股票池、过滤、评分、排序、缓存键或调度时间。

## 真实验证

- 结束旧的可见调度器进程树后，使用新命令重新启动；后台 `cmd` 的 `MainWindowHandle` 为 `0`，没有可见窗口标题。
- `.cache/scheduler.instance.lock` 已由新的实际工作进程持有，`scheduler.err.log` 重新记录每日 15:30 分析和 15:45 T+1 预生成任务，Web `http://localhost:8501` 返回 `HTTP 200`。
- `.venv\Scripts\python.exe -m pytest tests\test_scheduler.py tests\test_dependency_constraints.py -q --basetemp=.tmp\pytest-hidden-scheduler-full` 通过：`17 passed`。
- `.venv\Scripts\python.exe -m ruff check tests\test_dependency_constraints.py` 与 `git diff --check` 通过。
