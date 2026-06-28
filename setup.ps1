<#
.SYNOPSIS
    One-time setup: creates the virtual environment and installs dependencies.

.DESCRIPTION
    Equivalent to the Phase 5 step of creating a Python virtual environment.
    Run this once after cloning the repository before using start.ps1.
#>

$ProjectRoot = $PSScriptRoot
$VenvPath    = Join-Path $ProjectRoot ".venv"
$ReqFile     = Join-Path $ProjectRoot "requirements.txt"

Write-Host "Setting up AirNode..." -ForegroundColor Cyan

# Create virtual environment if it does not already exist
if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Gray
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment. Ensure Python 3.11+ is installed."
        exit 1
    }
} else {
    Write-Host "Virtual environment already exists, skipping creation." -ForegroundColor Gray
}

# Install / upgrade dependencies
$Pip = Join-Path $VenvPath "Scripts\pip.exe"
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Gray
& $Pip install -r $ReqFile --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    exit 1
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Start : .\start.ps1"
Write-Host "  Stop  : .\stop.ps1"
Write-Host "  Autostart (on login): .\install-autostart.ps1"
