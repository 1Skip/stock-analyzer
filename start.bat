@echo off
chcp 65001
cls
cd /d "C:\Users\skip8\stock_analyzer"

python --version >nul 2>&1
if errorlevel 1 (
    echo ============================================
    echo ERROR: Python not found
    echo ============================================
    echo Please install Python 3.8 or higher
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:MENU
cls
echo ============================================
echo        STOCK ANALYSIS SYSTEM
echo ============================================
echo.
echo [1] Analyze Single Stock
echo [2] Hot Stocks Ranking
echo [3] Recommended Stocks
echo [4] Quick Demo
echo [5] Install Dependencies
echo [6] Exit
echo.
echo ============================================

set /p choice="Select option (1-6): "

if "%choice%"=="1" goto ANALYZE
if "%choice%"=="2" goto HOT
if "%choice%"=="3" goto RECOMMEND
if "%choice%"=="4" goto DEMO
if "%choice%"=="5" goto INSTALL
if "%choice%"=="6" goto EXIT
goto MENU

:ANALYZE
cls
echo ============================================
echo         ANALYZE STOCK
echo ============================================
echo.
echo Symbol Format:
echo   CN: 000001, 600519, 300750
echo   US: AAPL, TSLA, NVDA
echo   HK: 0700, 9988
echo.
set /p symbol="Enter stock symbol: "
set /p market="Market (CN/US/HK) [default: CN]: "
if "!market!"=="" set market=CN
set /p period="Period (1mo/3mo/6mo/1y/2y) [default: 1y]: "
if "!period!"=="" set period=1y
echo.
echo Analyzing %symbol% ...
python main.py -s %symbol% -m %market% -p %period%
echo.
pause
goto MENU

:HOT
cls
echo ============================================
echo         HOT STOCKS
echo ============================================
echo.
set /p market="Market (CN/US) [default: CN]: "
if "!market!"=="" set market=CN
echo.
python main.py --hot -m %market%
echo.
pause
goto MENU

:RECOMMEND
cls
echo ============================================
echo      RECOMMENDED STOCKS
echo ============================================
echo.
echo Analyzing stock pool, please wait...
echo.
python main.py --recommend
echo.
pause
goto MENU

:DEMO
cls
echo ============================================
echo         QUICK DEMO
echo ============================================
echo.
echo Analyzing Ping An Bank (000001)...
python main.py --demo
echo.
pause
goto MENU

:INSTALL
cls
echo ============================================
echo      INSTALL DEPENDENCIES
echo ============================================
echo.
python -m pip install --upgrade pip
echo.
pip install yfinance pandas numpy matplotlib requests beautifulsoup4 akshare -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
if errorlevel 1 (
    echo Installation may have issues, but let's try running anyway
echo.
) else (
    echo Installation complete!
)
pause
goto MENU

:EXIT
echo.
echo Thank you for using Stock Analysis System!
echo.
timeout /t 2 >nul
exit
