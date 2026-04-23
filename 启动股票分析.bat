@echo off
chcp 65001 >nul
echo ======================================
echo        股票分析系统
echo ======================================
echo.

:: 切换到程序目录
cd /d "C:\Users\skip8\stock_analyzer"

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b
)

echo 正在启动股票分析系统...
echo.

:: 启动交互模式
python main.py -i

echo.
pause
