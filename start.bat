@echo off
setlocal
title Lunar LITE - AI Aimbot

:: Require admin: if not elevated, re-launch as admin and exit
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    echo.
    powershell -Command "Start-Process '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

:: Ensure we run from the folder where this batch file lives
cd /d "%~dp0"

:: Optional: show that we have admin
echo Running as Administrator.
echo Starting Lunar LITE...
echo.

python lunar.py --debug
if %errorlevel% neq 0 (
    echo.
    echo Python exited with error. Make sure Python is installed and run install_requirements.bat first.
    pause
) else (
    pause
)
