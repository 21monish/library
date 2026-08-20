param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [switch]$SeedDemo,
    [switch]$SkipInstall,
    [switch]$RunTests,
    [switch]$RunAutomation,
    [switch]$CheckOnly,
    [switch]$NoReload,
    [ValidatePattern('^[^:]+:\d+$')]
    [string]$BindAddress = '127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$requirements = Join-Path $projectRoot 'requirements.txt'

function Invoke-ProjectCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-Host $Label -ForegroundColor DarkCyan
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run: py -m venv `"$projectRoot\.venv`""
}
if (-not (Test-Path -LiteralPath $requirements)) {
    throw "requirements.txt was not found at $requirements"
}

Set-Location -LiteralPath $projectRoot

# Load a local .env file without printing secrets. Explicit process variables
# and command-line parameters always take precedence over file values.
$environmentFile = Join-Path $projectRoot '.env'
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
    Write-Host 'Environment    Loaded .env' -ForegroundColor DarkCyan
}

if (-not $DatabaseUrl -and $env:DATABASE_URL) {
    $DatabaseUrl = $env:DATABASE_URL
}
$hasStandardDatabaseComponents = (
    $env:DATABASE_HOST -and
    $env:DATABASE_PORT -and
    $env:DATABASE_NAME -and
    $env:DATABASE_USER -and
    $env:DATABASE_PASSWORD
)
$hasSevallaDatabaseComponents = (
    $env:DB_HOST -and
    $env:DB_PORT -and
    $env:DB_DATABASE -and
    $env:DB_USERNAME -and
    $env:DB_PASSWORD
)
$hasComponentDatabase = $hasStandardDatabaseComponents -or $hasSevallaDatabaseComponents
if (-not $DatabaseUrl -and -not $hasComponentDatabase -and $env:DB_URL) {
    $DatabaseUrl = $env:DB_URL
}

if ($DatabaseUrl) {
    $env:DATABASE_URL = $DatabaseUrl
    Write-Host 'Database       Configured PostgreSQL' -ForegroundColor Green
} elseif ($hasComponentDatabase) {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Write-Host 'Database       Configured PostgreSQL' -ForegroundColor Green
} else {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Write-Host 'Database       Local SQLite' -ForegroundColor Yellow
}
Write-Host "Project        $projectRoot"
Write-Host "Python         $python"

if (-not $SkipInstall) {
    Invoke-ProjectCommand 'Checking dependencies...' @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirements)
}

Invoke-ProjectCommand 'Checking Django configuration...' @('manage.py', 'check')
Invoke-ProjectCommand 'Checking for missing migrations...' @('manage.py', 'makemigrations', '--check', '--dry-run')
Invoke-ProjectCommand 'Applying database migrations...' @('manage.py', 'migrate', '--noinput')

if ($SeedDemo) {
    Invoke-ProjectCommand 'Loading repeatable demo data...' @('manage.py', 'seed_demo')
}

if ($RunTests) {
    Invoke-ProjectCommand 'Running the test suite...' @('manage.py', 'test', 'catalog', '--verbosity', '1')
}

if ($RunAutomation) {
    Invoke-ProjectCommand 'Running Shelfwise automation...' @('manage.py', 'run_library_automation')
}

if ($CheckOnly) {
    Write-Host 'Shelfwise checks completed successfully.' -ForegroundColor Green
    return
}

$parts = $BindAddress.Split(':')
$bindHost = $parts[0]
$bindPort = [int]$parts[1]
$listener = Get-NetTCPConnection -LocalPort $bindPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "Port $bindPort is already in use by process $($listener.OwningProcess). Stop that process or use -BindAddress '127.0.0.1:8001'."
}

$browserHost = if ($bindHost -in @('0.0.0.0', '::')) { '127.0.0.1' } else { $bindHost }
$localUrl = "http://${browserHost}:$bindPort/"
$serverArguments = @('manage.py', 'runserver', $BindAddress)
if ($NoReload) { $serverArguments += '--noreload' }

Write-Host ''
Write-Host 'Shelfwise is ready' -ForegroundColor Green
Write-Host "Library        $localUrl" -ForegroundColor Cyan
Write-Host "Health check   ${localUrl}health/" -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop the server.'
& $python @serverArguments
