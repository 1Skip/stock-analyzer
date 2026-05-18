@echo off
setlocal

cd /d "%~dp0"
set "APP_PORT=8501"
set "APP_URL=http://localhost:%APP_PORT%"

echo ======================================
echo      Stock Analyzer Web Launcher
echo ======================================
echo.

if not exist ".env" if exist ".env.example" (
    echo [INFO] Local .env not found. Copy .env.example to .env and fill API keys if you want local LLM/Feishu enabled.
    echo.
)

set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found.
    echo Please install Python 3.10 or newer:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating local virtual environment: .venv
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "PY=.venv\Scripts\python.exe"

echo [2/3] Installing dependencies. First run may take a few minutes...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed.
    echo Please check your network or pip mirror.
    pause
    exit /b 1
)

echo.
echo [3/3] Starting Streamlit...
echo Browser URL: %APP_URL%
echo Press Ctrl+C to stop the server.
echo.

findstr /R /C:"^[ ]*SCHEDULE_ENABLED[ ]*=[ ]*true[ ]*$" ".env" >nul 2>nul
if not errorlevel 1 (
    powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*main.py --schedule*' }) { exit 0 } else { exit 1 }" >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Starting scheduler in background...
        start "Stock Analyzer Scheduler" /MIN cmd /c ""%PY%" main.py --schedule 1^>^>scheduler.out.log 2^>^>scheduler.err.log"
    ) else (
        echo [INFO] Scheduler already appears to be running.
    )
) else (
    echo [INFO] Scheduler is disabled. Set SCHEDULE_ENABLED=true in .env to enable close-after tasks.
)

start "" "%APP_URL%"
"%PY%" -m streamlit run app.py --server.port %APP_PORT% --server.headless true --browser.gatherUsageStats false

pause
