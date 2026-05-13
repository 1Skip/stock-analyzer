@echo off
setlocal

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Stock Analyzer.lnk"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo Startup launch has been disabled.
) else (
    echo Startup shortcut was not found.
)

pause
