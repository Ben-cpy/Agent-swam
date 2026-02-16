@echo off
REM AI Task Manager - Environment Setup Script
REM Sets up Python 3.9.13 virtual environment

echo ========================================
echo AI Task Manager - Environment Setup
echo ========================================
echo.

cd /d %~dp0

set PYTHON_EXE=C:\Users\15225\AppData\Local\Programs\Python\Python39\python.exe

REM Check if Python 3.9.13 exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python 3.9.13 not found at: %PYTHON_EXE%
    echo Please install Python 3.9.13 or update the path in this script
    pause
    exit /b 1
)

echo [INFO] Using Python:
%PYTHON_EXE% --version
echo.

REM Check if venv already exists
if exist "venv" (
    echo [WARN] Virtual environment already exists
    set /p RECREATE="Do you want to recreate it? (y/N): "
    if /i not "%RECREATE%"=="y" (
        echo [INFO] Keeping existing virtual environment
        goto :install_deps
    )
    echo [INFO] Removing existing virtual environment...
    rmdir /s /q venv
)

echo [INFO] Creating virtual environment...
%PYTHON_EXE% -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [SUCCESS] Virtual environment created
echo.

:install_deps
echo [INFO] Installing dependencies...
venv\Scripts\pip.exe install --upgrade pip
venv\Scripts\pip.exe install -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo [SUCCESS] Setup completed!
echo ========================================
echo.
echo To start the server, run: start_server.bat
echo Or manually: cd backend ^&^& ..\venv\Scripts\python.exe main.py
echo.

pause
