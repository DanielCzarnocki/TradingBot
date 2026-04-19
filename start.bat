@echo off
title New Bot Server
cd /d "%~dp0"

REM Check for virtual environment
if exist "venv\Scripts\activate.bat" goto :ACTIVATE
echo [ERROR] Virtual environment (venv) not found!
echo [TIP] Run 'python -m venv venv' and 'pip install -r requirements.txt'
pause
exit /b

:ACTIVATE
call ".\venv\Scripts\activate.bat"
python main.py


if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application failed to start (Error Code: %ERRORLEVEL%).
    pause
)

echo.
echo Server closed.
pause
