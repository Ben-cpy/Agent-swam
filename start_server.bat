@echo off
REM AI Task Manager - Backend Startup Script
REM Python 3.9.13 environment

echo ========================================
echo AI Task Manager Backend
echo ========================================
echo.

cd /d %~dp0

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run: C:\Users\15225\AppData\Local\Programs\Python\Python39\python.exe -m venv venv
    echo Then: venv\Scripts\pip.exe install -r backend\requirements.txt
    pause
    exit /b 1
)

echo [INFO] Using Python from virtual environment
venv\Scripts\python.exe --version
echo.

echo [INFO] Starting backend server...
echo [INFO] Server will be available at: http://127.0.0.1:8000
echo [INFO] Press Ctrl+C to stop the server
echo.

cd backend
..\venv\Scripts\python.exe main.py

pause
