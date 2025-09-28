# StartTranscodeService.ps1
# PowerShell script to start the TranscodeService microservice

param(
    [switch]$Verbose,
    [switch]$Background
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TranscodeServiceDir = Join-Path $ScriptDir "TranscodeService"
$VenvPath = Join-Path $TranscodeServiceDir "venv"
$MainScript = Join-Path $TranscodeServiceDir "main.py"

Write-Host "Starting TranscodeService..." -ForegroundColor Green

# Check if TranscodeService directory exists
if (-not (Test-Path $TranscodeServiceDir)) {
    Write-Error "TranscodeService directory not found: $TranscodeServiceDir"
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path $VenvPath)) {
    Write-Error "Virtual environment not found: $VenvPath"
    Write-Host "Please create the virtual environment first:" -ForegroundColor Yellow
    Write-Host "  cd TranscodeService" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor Yellow
    exit 1
}

# Check if main script exists
if (-not (Test-Path $MainScript)) {
    Write-Error "Main script not found: $MainScript"
    exit 1
}

# Check if service is already running
$ProcessName = "python"
$ProcessArgs = $MainScript
$ExistingProcess = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*$ProcessArgs*"
}

if ($ExistingProcess) {
    Write-Warning "TranscodeService appears to be already running (PID: $($ExistingProcess.Id))"
    Write-Host "Use StopTranscodeService.ps1 to stop it first, or use -Force to restart" -ForegroundColor Yellow
    if (-not $Force) {
        exit 1
    }
    Write-Host "Stopping existing process..." -ForegroundColor Yellow
    Stop-Process -Id $ExistingProcess.Id -Force
    Start-Sleep -Seconds 2
}

# Activate virtual environment
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    Write-Host "Activating virtual environment..." -ForegroundColor Cyan
    & $ActivateScript
} else {
    Write-Error "Virtual environment activation script not found: $ActivateScript"
    exit 1
}

# Install dependencies if needed
$RequirementsFile = Join-Path $TranscodeServiceDir "requirements.txt"
if (Test-Path $RequirementsFile) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r $RequirementsFile
}

# Change to TranscodeService directory
Set-Location $TranscodeServiceDir

# Start the service
Write-Host "Starting TranscodeService..." -ForegroundColor Green
Write-Host "Working Directory: $TranscodeServiceDir" -ForegroundColor Gray
Write-Host "Python Script: $MainScript" -ForegroundColor Gray

if ($Background) {
    Write-Host "Starting in background..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList $MainScript -WorkingDirectory $TranscodeServiceDir -WindowStyle Hidden
    Write-Host "TranscodeService started in background" -ForegroundColor Green
} else {
    Write-Host "Starting in foreground (Ctrl+C to stop)..." -ForegroundColor Yellow
    try {
        python $MainScript
    } catch {
        Write-Error "Failed to start TranscodeService: $_"
        exit 1
    }
}

Write-Host "TranscodeService startup complete" -ForegroundColor Green
