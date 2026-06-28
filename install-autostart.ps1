<#
.SYNOPSIS
    Register AirNode to start automatically when you log in to Windows.

.DESCRIPTION
    Creates a Windows Task Scheduler task that runs start.ps1 at logon.
    This is the Windows equivalent of a systemd service set to start on boot.
    Requires no elevated (admin) privileges — the task runs as the current user.

.NOTES
    To remove the scheduled task: .\uninstall-autostart.ps1
#>

$TaskName    = "AirNode"
$ProjectRoot = $PSScriptRoot
$StartScript = Join-Path $ProjectRoot "start.ps1"

# Remove any previous registration
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action  = New-ScheduledTaskAction `
    -Execute  "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$StartScript`"" `
    -WorkingDirectory $ProjectRoot

# Trigger: At logon of the current user (no admin required)
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit    (New-TimeSpan -Hours 0) `
    -RestartCount          3 `
    -RestartInterval       (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -MultipleInstances     IgnoreNew

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -RunLevel  Limited `
    -Description "Starts the AirNode LAN file server at user logon." | Out-Null

Write-Host "AirNode autostart registered in Task Scheduler." -ForegroundColor Green
Write-Host "It will start automatically the next time you log in."
Write-Host "Remove with: .\uninstall-autostart.ps1"
