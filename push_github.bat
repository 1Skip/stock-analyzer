@echo off
cd /d "C:\Users\skip8\stock_analyzer"
echo ========================================
echo    Pushing to GitHub...
echo ========================================
echo.

PowerShell -ExecutionPolicy Bypass -File "push_to_github_en.ps1"

if errorlevel 1 (
    echo.
    echo Push failed, check error message
    pause
) else (
    echo.
    echo Push complete!
    timeout /t 2 >nul
)
