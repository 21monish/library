param(
    [ValidateNotNullOrEmpty()]
    [string]$TaskName = 'Shelfwise Daily Automation',
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')]
    [string]$DailyAt = '08:00',
    [switch]$SkipEmail,
    [switch]$RunNow,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$automationScript = Join-Path $projectRoot 'automation.ps1'

if ($Uninstall) {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Yellow
    } else {
        Write-Host "Scheduled task '$TaskName' is not installed."
    }
    return
}

if (-not (Test-Path -LiteralPath $automationScript)) {
    throw "Automation runner not found at $automationScript"
}

$dailyTime = [datetime]::ParseExact(
    $DailyAt,
    'HH:mm',
    [System.Globalization.CultureInfo]::InvariantCulture
)
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$automationScript`""
if ($SkipEmail) {
    $arguments += ' -SkipEmail'
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $dailyTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Daily Shelfwise alerts, email delivery, CSV backup, and monthly PDF report.' `
    -Force | Out-Null

Write-Host "Installed '$TaskName' for $DailyAt every day." -ForegroundColor Green
Write-Host "Runner: $automationScript"
if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host 'The first automation run has been started.' -ForegroundColor DarkCyan
}
