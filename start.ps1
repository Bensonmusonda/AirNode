<#
.SYNOPSIS
    Start the AirNode server in the background (no console window).

.DESCRIPTION
    Launches uvicorn with the AirNode FastAPI application bound to all
    network interfaces so that devices on the local hotspot can reach it.
    Writes stdout/stderr to airnode.log and saves the uvicorn process ID
    to airnode.pid so the companion stop script can terminate it cleanly.

.NOTES
    Run once after connecting to the phone hotspot.
    Requires: Python virtual environment at .\.venv\
#>

$ProjectRoot = $PSScriptRoot
$LogFile     = Join-Path $ProjectRoot "airnode.log"
$PidFile     = Join-Path $ProjectRoot "airnode.pid"
$Python      = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# Verify the virtual environment exists
if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment not found at $Python. Run setup.ps1 first."
    exit 1
}

# Reject if already running
if (Test-Path $PidFile) {
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
        Write-Host "AirNode is already running (PID $ExistingPid)." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $PidFile -Force
}

# Launch uvicorn directly (not via cmd.exe) so -PassThru gives us the
# real uvicorn process ID rather than a transient cmd.exe wrapper PID.
# stdout/stderr are each redirected to separate temp files then the log
# is tail-merged; PowerShell's Start-Process cannot redirect both to the
# same file in one call so we redirect stderr to <log>.err and let the
# user check either file.
$ErrLog = $LogFile + ".err"

$Process = Start-Process `
    -FilePath               $Python `
    -ArgumentList           "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory       $ProjectRoot `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError  $ErrLog `
    -WindowStyle            Hidden `
    -PassThru

$Process.Id | Out-File -FilePath $PidFile -Encoding ascii -NoNewline

Write-Host "AirNode started (PID $($Process.Id))." -ForegroundColor Green
Write-Host "Log  : $LogFile"
Write-Host "Err  : $ErrLog"
Write-Host "Stop : .\stop.ps1"
