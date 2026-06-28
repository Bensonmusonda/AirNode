<#
.SYNOPSIS
    Remove the AirNode autostart entry from Windows Task Scheduler.
#>

$TaskName = "AirNode"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "AirNode autostart task removed." -ForegroundColor Green
} else {
    Write-Host "No scheduled task named '$TaskName' found." -ForegroundColor Yellow
}
