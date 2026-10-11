# Assetly - Quick Run Existing Application (PowerShell)
$ErrorActionPreference = "Continue"

try {
    $rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $rootDir

    $venvPy = Join-Path $rootDir ".venv\Scripts\python.exe"
    $validSetup = $false

    if ((Test-Path $venvPy) -and (Test-Path ".env")) {
        try {
            & $venvPy -c "import sys, os, uvicorn, fastapi, sqlalchemy, pymysql, cryptography; assert os.path.normcase(sys.prefix) == os.path.normcase(os.path.abspath('.venv'))" 2>$null
            if ($LASTEXITCODE -eq 0) {
                & $venvPy scripts\init_db.py --check 2>$null
                if ($LASTEXITCODE -eq 0) { $validSetup = $true }
            }
        } catch {}
    }

    if (-not $validSetup) {
        Write-Host "[!] Environment or MySQL root connection is not configured for this PC yet." -ForegroundColor Yellow
        Write-Host "[*] Launching First-Time Setup automatically...`n" -ForegroundColor Cyan
        & "$rootDir\setup_first_time.ps1"
        return
    }

    Clear-Host
    Write-Host "===============================================================================" -ForegroundColor Green
    Write-Host "  Assetly is running at: http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "  Press Ctrl+C to stop the application" -ForegroundColor Gray
    Write-Host "===============================================================================" -ForegroundColor Green

    Start-Process "http://127.0.0.1:8000"
    & $venvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ERROR] Assetly server exited with an error. Review the message above." -ForegroundColor Red
    }
} catch {
    Write-Host "`n[ERROR] $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Write-Host "`n-------------------------------------------------------------------------------" -ForegroundColor Yellow
    Read-Host "Window kept open so you can review output. Press Enter to close"
}
