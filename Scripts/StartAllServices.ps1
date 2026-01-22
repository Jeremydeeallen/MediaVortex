#!/usr/bin/env pwsh
# StartAllServices.ps1
# Opens Windows Terminal tabs for each service and starts them with admin privileges

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath

# Define services
$Services = @(
    @{
        Name = "WebService"
        Path = Join-Path $ProjectRoot "WebService"
    },
    @{
        Name = "TranscodeService"
        Path = Join-Path $ProjectRoot "TranscodeService"
    },
    @{
        Name = "QualityTestService"
        Path = Join-Path $ProjectRoot "QualityTestService"
    }
)

# Check if Windows Terminal is available
$WtPath = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $WtPath) {
    Write-Host "Windows Terminal (wt.exe) not found. Please install Windows Terminal or use a different terminal." -ForegroundColor Red
    exit 1
}

Write-Host "Starting all services in Windows Terminal (Admin)..." -ForegroundColor Green
Write-Host ""

# Create temporary script files for each service to avoid escaping issues
$TempScripts = @()
$TempDir = Join-Path $env:TEMP "MediaVortexServiceScripts"

# Create temp directory if it doesn't exist
if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Path $TempDir | Out-Null
}

# Clean up any old scripts
Get-ChildItem -Path $TempDir -Filter "StartService_*.ps1" | Remove-Item -Force -ErrorAction SilentlyContinue

# Build the command to open all tabs in a single window
$WtCommandParts = @()

foreach ($Service in $Services) {
    $ServicePath = $Service.Path
    $ServiceName = $Service.Name
    $VenvActivate = Join-Path $ServicePath "venv\Scripts\Activate.ps1"
    
    Write-Host "Preparing $ServiceName..." -ForegroundColor Cyan
    
    # Create a temporary script file for this service
    $TempScript = Join-Path $TempDir "StartService_$ServiceName.ps1"
    $ScriptContent = @"
Set-Location -LiteralPath '$ServicePath'
if (Test-Path '$VenvActivate') {
    . '$VenvActivate'
}
py Main.py
"@
    
    $ScriptContent | Out-File -FilePath $TempScript -Encoding UTF8 -Force
    $TempScripts += $TempScript
    
    # Build wt.exe command for this tab with title
    $TabCommand = "new-tab", "--title", "`"$ServiceName`"", "-d", "`"$ServicePath`"", "powershell", "-NoExit", "-File", "`"$TempScript`""
    $WtCommandParts += ($TabCommand -join " ")
}

# Join all tab commands with semicolons
$WtCommand = $WtCommandParts -join "; "

# Launch Windows Terminal with all tabs in a single window, elevated as admin
Write-Host "Launching Windows Terminal with all services..." -ForegroundColor Green
Write-Host ""

# Use Start-Process with RunAs to elevate - pass as single string
Start-Process -FilePath "wt.exe" -ArgumentList $WtCommand -Verb RunAs

# Note: Temp scripts will be cleaned up on next run (they're in $env:TEMP)

Write-Host "Windows Terminal launched with admin privileges!" -ForegroundColor Green
Write-Host "Each tab will:"
Write-Host "  1. Change to the service directory"
Write-Host "  2. Activate the virtual environment"
Write-Host "  3. Run 'py Main.py'"
Write-Host ""

