@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 🚀 正在启动股票分析系统...
echo.
streamlit run app.py --server.headless true
pause
