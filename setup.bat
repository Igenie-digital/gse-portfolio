@echo off
echo ===== GSE Portfolio Tracker Setup =====
echo.

:: Check Python
py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Please download and install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
py -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
pip install -r requirements.txt

echo [3/4] Installing Playwright browser (headless Chrome)...
playwright install chromium

echo [4/4] Importing your existing trades and seed prices...
python migrate.py

echo.
echo ===== Setup complete! =====
echo Double-click start.bat to launch the app.
pause
