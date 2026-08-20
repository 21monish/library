param(
    [switch]$SkipEmail,
    [switch]$SkipBackup,
    [switch]$SkipMonthlyReport,
    [switch]$ForceMonthlyReport
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$environmentFile = Join-Path $projectRoot '.env'
$runtimeDirectory = Join-Path $projectRoot '.runtime'
$lockPath = Join-Path $runtimeDirectory 'automation.lock'
$logPath = Join-Path $runtimeDirectory 'automation.log'
$lockStream = $null
$transcriptStarted = $false

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found at $python"
}

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

function New-AutomationLock {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        return [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::Read
        )
    } catch [System.IO.IOException] {
        $existingPid = 0
        if (Test-Path -LiteralPath $Path) {
            [void][int]::TryParse((Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim(), [ref]$existingPid)
        }
        if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            throw "Shelfwise automation is already running in process $existingPid."
        }
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        return [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::Read
        )
    }
}

try {
    $lockStream = New-AutomationLock -Path $lockPath
    $lockBytes = [System.Text.Encoding]::UTF8.GetBytes([string]$PID)
    $lockStream.Write($lockBytes, 0, $lockBytes.Length)
    $lockStream.Flush()

    try {
        Start-Transcript -Path $logPath -Append | Out-Null
        $transcriptStarted = $true
    } catch {
        Write-Warning "Automation transcript could not be started: $($_.Exception.Message)"
    }

    # Load project settings without printing secret values. Existing process
    # variables take priority over values stored in .env.
    if (Test-Path -LiteralPath $environmentFile) {
        foreach ($line in Get-Content -LiteralPath $environmentFile) {
            $trimmed = $line.Trim()
            if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) {
                continue
            }
            $name, $value = $trimmed.Split('=', 2)
            $name = $name.Trim()
            $value = $value.Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$' -and -not [Environment]::GetEnvironmentVariable($name, 'Process')) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }

    $commandArguments = @('manage.py', 'run_library_automation')
    if ($SkipEmail) { $commandArguments += '--skip-email' }
    if ($SkipBackup) { $commandArguments += '--skip-backup' }
    if ($SkipMonthlyReport) { $commandArguments += '--skip-monthly-report' }
    if ($ForceMonthlyReport) { $commandArguments += '--force-monthly-report' }

    Write-Host "Shelfwise automation started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkCyan
    & $python @commandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Shelfwise automation failed with exit code $LASTEXITCODE."
    }
    Write-Host 'Shelfwise automation finished successfully.' -ForegroundColor Green
} finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
    if ($lockStream) {
        $lockStream.Dispose()
    }
    if (Test-Path -LiteralPath $lockPath) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}
