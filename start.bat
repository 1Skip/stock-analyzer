@echo off
setlocal

cd /d "%~dp0"
set "APP_PORT=8501"
set "APP_URL=http://localhost:%APP_PORT%"
set "APP_HEALTH_URL=http://127.0.0.1:%APP_PORT%/_stcore/health"

echo ======================================
echo      Stock Analyzer Web Launcher
echo ======================================
echo.

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%APP_HEALTH_URL%' -TimeoutSec 2; if ($response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Stock Analyzer is already running. Opening existing page...
    start "" "%APP_URL%"
    exit /b 0
)

if not exist ".env" if exist ".env.example" (
    echo [INFO] Local .env not found. Copy .env.example to .env and fill API keys if you want local LLM enabled.
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
    echo Please install Python 3.11 or newer:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.11 or newer is required.
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

"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] The existing .venv uses Python older than 3.11.
    echo Remove .venv and run start.bat again with Python 3.11 or newer.
    echo.
    pause
    exit /b 1
)

echo [2/3] Installing dependencies. First run may take a few minutes...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt -c constraints.txt
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

"%PY%" -c "import config; raise SystemExit(0 if config.SCHEDULE_ENABLED else 1)" >nul 2>nul
if not errorlevel 1 (
    powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*main.py --schedule*' }) { exit 0 } else { exit 1 }" >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Starting scheduler in background...
        powershell -NoProfile -Command "$workDir = (Get-Location).Path; $python = (Resolve-Path '%PY%').Path; $command = [char]34 + $python + [char]34 + ' main.py --schedule 1>>scheduler.out.log 2>>scheduler.err.log'; Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c',$command -WorkingDirectory $workDir -WindowStyle Hidden"
    ) else (
        echo [INFO] Scheduler already appears to be running.
    )
) else (
    echo [INFO] Scheduler is disabled. Set SCHEDULE_ENABLED=true in .env to enable local report/cache tasks.
)

start "" "%APP_URL%"
"%PY%" -m streamlit run app.py --server.port %APP_PORT% --server.headless true --browser.gatherUsageStats false

pause
