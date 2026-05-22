@echo off
setlocal

cd /d "%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\Stock Analyzer.lnk"
set "ICON=%CD%\assets\app.ico"

echo ======================================
echo      Enable Windows startup launch
echo ======================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell = New-Object -ComObject WScript.Shell; " ^
  "$shortcut = $shell.CreateShortcut('%SHORTCUT%'); " ^
  "$shortcut.TargetPath = '%CD%\start.bat'; " ^
  "$shortcut.WorkingDirectory = '%CD%'; " ^
  "$shortcut.WindowStyle = 7; " ^
  "if (Test-Path -LiteralPath '%ICON%') { $shortcut.IconLocation = '%ICON%' }; " ^
  "$shortcut.Description = 'Start Stock Analyzer automatically'; " ^
  "$shortcut.Save()"

if errorlevel 1 (
    echo [ERROR] Failed to enable startup launch.
    pause
    exit /b 1
)

echo Startup launch has been enabled:
echo %SHORTCUT%
echo.
echo The app will start after you log in to Windows.
pause
