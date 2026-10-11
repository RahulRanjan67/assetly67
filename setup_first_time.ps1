# Assetly - First-Time Setup & Initialization (PowerShell)
$ErrorActionPreference = "Continue"

try {
    $rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $rootDir

    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host "              ASSETLY - FIRST-TIME SETUP & DATABASE INITIALIZATION             " -ForegroundColor Cyan
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host "  Project Folder: $rootDir" -ForegroundColor Gray
    Write-Host "===============================================================================`n" -ForegroundColor Cyan

    # 1. Detect a valid Python 3.10+ interpreter on this PC
    Write-Host "[1/4] Detecting Python installation on this PC..." -ForegroundColor Yellow
    $pythonExe = $null

    foreach ($candidate in @("python", "py")) {
        try {
            $exePath = & $candidate -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exePath -and (Test-Path $exePath.Trim())) {
                $pythonExe = $exePath.Trim()
                break
            }
        } catch {}
    }

    if (-not $pythonExe) {
        $searchDirs = @(
            "$env:LOCALAPPDATA\Programs\Python\Python3*",
            "$env:ProgramFiles\Python3*",
            "C:\Python3*"
        )
        foreach ($pattern in $searchDirs) {
            $found = Get-Item "$pattern\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $pythonExe = $found.FullName
                break
            }
        }
    }

    while (-not $pythonExe) {
        Write-Host "`n[!] Could not automatically find Python 3.10+ in your PC PATH." -ForegroundColor Red
        $userInput = Read-Host "Please enter the full path to python.exe or folder containing python.exe"
        $userInput = $userInput.Trim('"').Trim()
        if (Test-Path "$userInput\python.exe") {
            $userInput = "$userInput\python.exe"
        }
        if (Test-Path $userInput) {
            try {
                & $userInput -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $pythonExe = $userInput
                    break
                }
            } catch {}
        }
        Write-Host "[ERROR] '$userInput' is not a valid Python 3.10+ executable. Please try again." -ForegroundColor Red
    }

    Write-Host "      Found Python: $pythonExe" -ForegroundColor Green

    # 2. Prepare Virtual Environment (.venv) adapted to THIS PC and folder
    Write-Host "`n[2/4] Preparing local virtual environment (.venv) for this PC..." -ForegroundColor Yellow
    $venvPy = Join-Path $rootDir ".venv\Scripts\python.exe"
    if (Test-Path ".venv") {
        $validVenv = $false
        if (Test-Path $venvPy) {
            try {
                & $venvPy -c "import sys, os; assert os.path.normcase(sys.prefix) == os.path.normcase(os.path.abspath('.venv'))" 2>$null
                if ($LASTEXITCODE -eq 0) { $validVenv = $true }
            } catch {}
        }
        if (-not $validVenv) {
            Write-Host "      Removing old .venv from previous PC or folder..." -ForegroundColor Gray
            Remove-Item -Recurse -Force ".venv" -ErrorAction SilentlyContinue
        }
    }

    if (-not (Test-Path $venvPy)) {
        Write-Host "      Creating fresh virtual environment bound to $rootDir\.venv ..." -ForegroundColor Gray
        & $pythonExe -m venv ".venv"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
            Write-Host "`n[ERROR] Failed to create virtual environment (.venv)." -ForegroundColor Red
            return
        }
    }
    Write-Host "      Virtual environment ready." -ForegroundColor Green

    # 3. Install dependencies (including cryptography for MySQL 8.0)
    Write-Host "`n[3/4] Installing Python dependencies from requirements.txt..." -ForegroundColor Yellow
    & $venvPy -m pip install --upgrade pip | Out-Null
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ERROR] Failed to install dependencies from requirements.txt." -ForegroundColor Red
        Write-Host "        Review the pip error message above and check your internet connection." -ForegroundColor Yellow
        return
    }
    & $venvPy -c "import fastapi, uvicorn, sqlalchemy, pymysql, cryptography, qrcode" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Ensuring cryptography package is installed..." -ForegroundColor Gray
        & $venvPy -m pip install cryptography
    }
    Write-Host "      Dependencies installed." -ForegroundColor Green

    # 4. Database Reset and Initialization (writes .env after verifying MySQL root connection)
    Write-Host "`n[4/4] Configuring MySQL database for user root, applying views, and seeding data..." -ForegroundColor Yellow
    & $venvPy scripts\init_db.py --setup
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n===============================================================================" -ForegroundColor Red
        Write-Host "[ERROR] Database initialization did not complete." -ForegroundColor Red
        Write-Host "        Review the error output above and ensure MySQL Server is running." -ForegroundColor Yellow
        Write-Host "===============================================================================" -ForegroundColor Red
        return
    }

    if (-not (Test-Path "app\static\uploads")) {
        New-Item -ItemType Directory -Path "app\static\uploads" -Force | Out-Null
    }

    Write-Host "`n===============================================================================" -ForegroundColor Green
    Write-Host "  SETUP COMPLETE! Database initialized, views created, and demo data seeded." -ForegroundColor Green
    Write-Host "  Local Web Link:  http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "===============================================================================`n" -ForegroundColor Green

    Start-Process "http://127.0.0.1:8000"
    & $venvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
} catch {
    Write-Host "`n===============================================================================" -ForegroundColor Red
    Write-Host "[ERROR] An unexpected error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    Write-Host "===============================================================================" -ForegroundColor Red
} finally {
    Write-Host "`n-------------------------------------------------------------------------------" -ForegroundColor Yellow
    Read-Host "Window kept open so you can review output. Press Enter to close"
}
