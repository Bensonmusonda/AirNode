<#
.SYNOPSIS
    Stop the AirNode server.

.DESCRIPTION
    Reads the PID written by start.ps1 and terminates the uvicorn process
    gracefully. Cleans up the PID file afterwards.
#>

$ProjectRoot = $PSScriptRoot
$PidFile     = Join-Path $ProjectRoot "airnode.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "AirNode does not appear to be running (no PID file found)." -ForegroundColor Yellow
    exit 0
}

$TargetPid = Get-Content $PidFile -ErrorAction SilentlyContinue

if (-not $TargetPid) {
    Remove-Item $PidFile -Force
    Write-Host "PID file was empty. Cleaned up." -ForegroundColor Yellow
    exit 0
}

$Process = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue

if ($Process) {
    Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue
    Write-Host "AirNode (PID $TargetPid) stopped." -ForegroundColor Green
} else {
    Write-Host "No process found for PID $TargetPid. It may have already exited." -ForegroundColor Yellow
}

# Ensure any orphaned uvicorn worker processes listening on port 8000 are also terminated
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue

