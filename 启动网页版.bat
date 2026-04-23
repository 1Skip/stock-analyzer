@echo off
echo ============================================
echo      Stock Analysis - Web Version
echo ============================================
echo.

cd /d "C:\Users\skip8\stock_analyzer"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    echo Please install Python first:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b
)

echo Installing required packages...
pip install streamlit plotly yfinance pandas numpy requests -q

echo.
echo Starting web server...
echo Please wait...
echo.
echo ============================================
echo  The web page will open automatically
.echo  Or visit: http://localhost:8501
.echo ============================================
echo.

:: Start Streamlit
streamlit run app.py

pause
