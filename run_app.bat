@echo off
if "%ASSETLY_KEEP_OPEN%"=="" (
    set "ASSETLY_KEEP_OPEN=1"
    cmd /k call "%~f0" %*
    exit /b
)
cd /d "%~dp0"
title Assetly

:: Verify that .venv exists, belongs to THIS PC, has cryptography, and can connect to MySQL
if not exist ".venv\Scripts\python.exe" goto :need_setup
if not exist ".env" goto :need_setup
".venv\Scripts\python.exe" -c "import sys, os, uvicorn, fastapi, sqlalchemy, pymysql, cryptography; assert os.path.normcase(sys.prefix) == os.path.normcase(os.path.abspath('.venv'))" >nul 2>&1
if errorlevel 1 goto :need_setup
".venv\Scripts\python.exe" scripts\init_db.py --check >nul 2>&1
if errorlevel 1 goto :need_setup

cls
echo ===============================================================================
echo   Assetly is running at: http://127.0.0.1:8000
echo   Press Ctrl+C to stop the application
echo ===============================================================================
start "" "http://127.0.0.1:8000"
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
if errorlevel 1 goto :server_error
echo.
pause
exit /b 0

:server_error
color 0C
echo.
echo [ERROR] Assetly server exited with an error. Review the message above.
echo         If your MySQL password or database changed, run setup_first_time.bat.
pause
exit /b 1

:need_setup
echo [!] Environment or MySQL root connection is not configured for this PC yet.
echo [*] Launching First-Time Setup automatically...
echo.
call "%~dp0setup_first_time.bat"
