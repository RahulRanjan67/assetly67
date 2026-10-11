@echo off
if "%ASSETLY_KEEP_OPEN%"=="" (
    set "ASSETLY_KEEP_OPEN=1"
    cmd /k call "%~f0" %*
    exit /b
)
title Assetly - First-Time Setup ^& Initialization
color 0A

cd /d "%~dp0"

echo ===============================================================================
echo               ASSETLY - FIRST-TIME SETUP ^& DATABASE INITIALIZATION
echo ===============================================================================
echo   Project Folder: %CD%
echo ===============================================================================
echo.

:: 1. Locate a valid Python 3.10+ interpreter on this PC
echo [1/4] Detecting Python installation on this PC...
set "PY_CMD="

py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :found_python
)

python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :found_python
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "C:\Python3*") do (
    if exist "%%~fD\python.exe" (
        "%%~fD\python.exe" -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD="%%~fD\python.exe""
            goto :found_python
        )
    )
)

:ask_python
echo.
echo [!] Could not automatically find Python 3.10+ in your PC PATH.
echo     Please enter the full path to python.exe or the folder where Python is installed.
echo     Example: C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312
set /p "USER_PY_PATH=Python Path: "
set "USER_PY_PATH=%USER_PY_PATH:"=%"
if "%USER_PY_PATH%"=="" goto :ask_python

if exist "%USER_PY_PATH%\python.exe" set "USER_PY_PATH=%USER_PY_PATH%\python.exe"
if exist "%USER_PY_PATH%" (
    "%USER_PY_PATH%" -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD="%USER_PY_PATH%""
        goto :found_python
    )
)
echo [ERROR] "%USER_PY_PATH%" is not a valid Python 3.10+ executable. Please try again.
goto :ask_python

:found_python
for /f "delims=" %%V in ('%PY_CMD% -c "import sys; print(sys.executable + ' - Python ' + sys.version.split()[0])"') do (
    echo       Found: %%V
)

:: 2. Prepare Virtual Environment adapted to THIS PC and folder
echo.
echo [2/4] Preparing local virtual environment for this PC...
if not exist ".venv" goto :create_venv
".venv\Scripts\python.exe" -c "import sys, os; assert os.path.normcase(sys.prefix) == os.path.normcase(os.path.abspath('.venv'))" >nul 2>&1
if not errorlevel 1 goto :venv_ready
echo       Removing old .venv from previous PC or folder...
rmdir /s /q ".venv"

:create_venv
if exist ".venv\Scripts\python.exe" goto :venv_ready
echo       Creating fresh virtual environment in %CD%\.venv ...
%PY_CMD% -m venv ".venv"
if errorlevel 1 goto :venv_error

:venv_ready
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
echo       Virtual environment ready.

:: 3. Install dependencies using this PC .venv Python
echo.
echo [3/4] Installing Python dependencies from requirements.txt...
"%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_error

"%VENV_PY%" -c "import fastapi, uvicorn, sqlalchemy, pymysql, cryptography, qrcode" >nul 2>&1
if errorlevel 1 (
    echo       Ensuring cryptography package is installed...
    "%VENV_PY%" -m pip install cryptography
    if errorlevel 1 goto :pip_error
)

:: 4. Configure MySQL root credentials, clean previous DB, create views and seed data
echo.
echo [4/4] Configuring MySQL database for user root, applying views, and seeding data...
"%VENV_PY%" scripts\init_db.py --setup
if errorlevel 1 goto :db_error

if not exist "app\static\uploads" mkdir "app\static\uploads"

echo.
echo ===============================================================================
echo   SETUP COMPLETE! Database initialized, views created, and demo data seeded.
echo   Local Web Link:  http://127.0.0.1:8000
echo ===============================================================================
echo.
echo Starting web server and opening browser...
start "" "http://127.0.0.1:8000"
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
echo.
echo [!] Web server stopped. Window remains open so you can review any output above.
pause
exit /b 0

:venv_error
color 0C
echo.
echo [ERROR] Failed to create virtual environment in .venv!
echo         Review the error message above.
pause
exit /b 1

:pip_error
color 0C
echo.
echo [ERROR] Failed to install dependencies from requirements.txt!
echo         Check your internet connection and review the pip error output above.
pause
exit /b 1

:db_error
color 0C
echo.
echo ===============================================================================
echo [ERROR] Database initialization did not complete.
echo         Review the error details printed above.
echo         Ensure MySQL Server is running on your PC and re-run setup_first_time.bat.
echo ===============================================================================
pause
exit /b 1
