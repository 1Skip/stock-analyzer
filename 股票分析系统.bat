@echo off
chcp 65001 >nul
title Stock Analyzer

cd /d "C:\Users\skip8\stock_analyzer"

python --version >nul 2>&1
if errorlevel 1 (
    echo ======================================
    echo Python not found
    echo ======================================
    echo Please install Python 3.8 or higher
    echo https://www.python.org/downloads/
    pause
    exit /b
)

:MENU
cls
echo ======================================
echo      Stock Analysis System
echo ======================================
echo.
echo [1] Analyze Stock - Enter symbol to analyze
echo [2] Hot Stocks    - View top gainers/volume
echo [3] Recommended   - AI-based stock picks
echo [4] Quick Demo    - Run demo (Ping An Bank)
echo [5] Compare       - Compare multiple stocks
echo [6] Install       - Install dependencies
echo [7] Exit
.
echo ======================================

set /p choice="Select option (1-7): "

if "%choice%"=="1" goto ANALYZE
if "%choice%"=="2" goto HOT
if "%choice%"=="3" goto RECOMMEND
if "%choice%"=="4" goto DEMO
if "%choice%"=="5" goto COMPARE
if "%choice%"=="6" goto INSTALL
if "%choice%"=="7" goto EXIT
goto MENU

:ANALYZE
cls
echo ======================================
echo         Analyze Stock
echo ======================================
echo.
echo Symbol format:
echo CN: 000001 (Ping An Bank), 600519 (Moutai)
echo US: AAPL, TSLA, NVDA
HK: 0700 (Tencent)
echo.
set /p symbol="Enter symbol: "
set /p market="Market (CN/US/HK, default CN): "
if "!market!"=="" set market=CN
set /p period="Period (1mo/3mo/6mo/1y/2y, default 1y): "
if "!period!"=="" set period=1y
echo.
echo Analyzing %symbol% ...
python main.py -s %symbol% -m %market% -p %period%
echo.
pause
goto MENU

:HOT
cls
echo ======================================
echo          Hot Stocks
echo ======================================
echo.
set /p market="Market (CN/US, default CN): "
if "!market!"=="" set market=CN
echo.
python main.py --hot -m %market%
echo.
pause
goto MENU

:RECOMMEND
cls
echo ======================================
echo       Recommended Stocks
echo ======================================
echo.
echo Analyzing stock pool...
echo.
python main.py --recommend
echo.
pause
goto MENU

:DEMO
cls
echo ======================================
echo         Quick Demo
echo ======================================
echo.
echo Analyzing Ping An Bank (000001)...
python main.py --demo
echo.
pause
goto MENU

:COMPARE
cls
echo ======================================
echo        Compare Stocks
echo ======================================
echo.
echo Enter multiple symbols separated by comma
echo Example: 000001,000002,000858
echo.
set /p symbols="Enter symbols: "
set /p market="Market (CN/US/HK, default CN): "
if "!market!"=="" set market=CN
echo.
python main.py -s %symbols% -m %market% -p 3mo
echo.
pause
goto MENU

:INSTALL
cls
echo ======================================
echo      Install Dependencies
echo ======================================
echo.
python -m pip install --upgrade pip
echo.
echo Installing packages...
pip install yfinance pandas numpy matplotlib requests beautifulsoup4 akshare
echo.
if errorlevel 1 (
    echo [Warning] Some packages failed to install
) else (
    echo [Success] Installation complete!
)
echo.
pause
goto MENU

:EXIT
echo.
echo Goodbye!
timeout /t 2 >nul
exit
