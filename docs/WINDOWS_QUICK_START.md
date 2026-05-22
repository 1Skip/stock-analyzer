# Windows 快速使用指南

## 自己电脑：双击启动

1. 安装 Python 3.10 或以上版本，安装时勾选 `Add Python to PATH`。
2. 双击项目根目录的 `start.bat`。
3. 首次运行会自动创建 `.venv` 并安装依赖。
4. 浏览器会自动打开 `http://localhost:8501`。

## 本机开启 LLM

如果希望本机网页左侧状态卡显示 LLM 多空辩论已开启：

1. 复制项目根目录的 `.env.example`，重命名为 `.env`。
2. 打开 `.env`，把 `AI_API_KEY` 改成你的模型 API Key。
3. 按需配置 `AI_BASE_URL`、`AI_MODEL`、`AI_DEBATE_ENABLED`。
4. 重新双击 `start.bat`。

示例：

```env
AI_DEBATE_ENABLED=true
AI_API_KEY=sk-替换成你的模型Key
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek/deepseek-v4-pro
AI_DEBATE_MAX_SYMBOLS=3
```

`.env` 已被 `.gitignore` 忽略，不会提交到 GitHub。

## 开机后自动启动

1. 双击 `install_startup.bat`。
2. 下次登录 Windows 后会自动启动股票分析系统。
3. 如需取消，双击 `uninstall_startup.bat`。

## 别人下载后直接使用

1. 安装 Python 3.10 或以上版本。
2. 安装 Python 时勾选 `Add Python to PATH`。
3. 下载并解压本项目。
4. 双击 `start.bat`。

## 常见问题

### 提示找不到 Python

重新安装 Python，并勾选 `Add Python to PATH`。

### 依赖安装很慢

可以在项目目录打开 PowerShell 后执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 浏览器没有自动打开

手动访问：

```text
http://localhost:8501
```

### 端口被占用

关闭旧的命令行窗口，或在任务管理器中结束旧的 Python/Streamlit 进程后重新双击 `start.bat`。
