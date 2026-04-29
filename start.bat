@echo off
call venv\Scripts\activate.bat
echo Starting GSE Portfolio Tracker at http://localhost:8000
start "" http://localhost:8000
python app.py
