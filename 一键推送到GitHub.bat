@echo off
cd /d "C:\Users\skip8\stock_analyzer"
echo ========================================
echo    正在推送到 GitHub...
echo ========================================
echo.

PowerShell -ExecutionPolicy Bypass -File "push_to_github.ps1"

if errorlevel 1 (
    echo.
    echo 推送失败，请检查错误信息
    pause
) else (
    echo.
    echo 推送完成！
    timeout /t 2 >nul
)
