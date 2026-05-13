# Windows 快速使用指南

## 自己电脑：打开就能用

1. 双击 `start.bat`。
2. 首次运行会自动创建 `.venv` 并安装依赖。
3. 浏览器会自动打开 `http://localhost:8501`。

如果希望开机后自动启动：

1. 双击 `install_startup.bat`。
2. 下次登录 Windows 后会自动启动股票分析系统。
3. 如需取消，双击 `uninstall_startup.bat`。

## 别人下载后：直接使用

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
