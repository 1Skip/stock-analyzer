@echo off
chcp 65001 >nul
echo ======================================
echo      安装股票分析系统依赖
echo ======================================
echo.

cd /d "C:\Users\skip8\stock_analyzer"

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python
    pause
    exit /b
)

echo 检测到Python版本:
python --version
echo.
echo 开始安装依赖包...
echo.

:: 升级pip
python -m pip install --upgrade pip

:: 安装依赖
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [警告] 部分依赖安装失败，尝试安装核心依赖...
    pip install yfinance pandas numpy matplotlib requests beautifulsoup4
)

echo.
echo 安装完成！
pause
