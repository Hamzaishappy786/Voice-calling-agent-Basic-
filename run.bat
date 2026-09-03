@echo off
title WebAgent Launcher
echo ===================================================
echo             Launching WebAgent AI Assistant
echo ===================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not added to PATH.
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate

echo Checking dependencies...
pip install -q -r requirements.txt piper-tts

if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
    )
)

echo.
echo Starting WebAgent Server on http://localhost:8000 ...
echo Press Ctrl+C to stop.
echo.

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
