@echo off
title Roblox Bot - Quick Start
echo.
echo ============================================
echo    ROBLOX BOT - Quick Start
echo ============================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
)

REM Check if dependencies installed
python -c "import click" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt -q
    playwright install chromium
)

REM Start the shell
echo.
echo Starting Interactive Shell...
echo.
python cli.py shell
pause
