# StartQualityCompareService.ps1
# PowerShell script to start the QualityCompareService microservice

param(
    [switch]$Verbose,
    [switch]$Background,
    [switch]$Force
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Get script directory and store original location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OriginalLocation = Get-Location
$QualityCompareServiceDir = Join-Path $ScriptDir "QualityCompareService"
$VenvPath = Join-Path $QualityCompareServiceDir "venv"
$MainScript = Join-Path $QualityCompareServiceDir "Main.py"

Write-Host "Starting QualityCompareService..." -ForegroundColor Green

# Check if QualityCompareService directory exists
if (-not (Test-Path $QualityCompareServiceDir)) {
    Write-Error "QualityCompareService directory not found: $QualityCompareServiceDir"
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path $VenvPath)) {
    Write-Error "Virtual environment not found: $VenvPath"
    Write-Host "Please create the virtual environment first:" -ForegroundColor Yellow
    Write-Host "  cd QualityCompareService" -ForegroundColor Yellow
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
    Write-Warning "QualityCompareService appears to be already running (PID: $($ExistingProcess.Id))"
    Write-Host "Use StopQualityCompareService.ps1 to stop it first, or use -Force to restart" -ForegroundColor Yellow
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
$RequirementsFile = Join-Path $QualityCompareServiceDir "requirements.txt"
if (Test-Path $RequirementsFile) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r $RequirementsFile
}

# Change to QualityCompareService directory
Set-Location $QualityCompareServiceDir

try {
    # Start the service
    Write-Host "Starting QualityCompareService..." -ForegroundColor Green
    Write-Host "Working Directory: $QualityCompareServiceDir" -ForegroundColor Gray
    Write-Host "Python Script: $MainScript" -ForegroundColor Gray

    if ($Background) {
        Write-Host "Starting in background..." -ForegroundColor Yellow
        Start-Process -FilePath "python" -ArgumentList $MainScript -WorkingDirectory $QualityCompareServiceDir -WindowStyle Hidden
        Write-Host "QualityCompareService started in background" -ForegroundColor Green
    } else {
        Write-Host "Starting in foreground (Ctrl+C to stop)..." -ForegroundColor Yellow
        try {
            python $MainScript
        } catch {
            Write-Error "Failed to start QualityCompareService: $_"
            throw
        }
    }

    Write-Host "QualityCompareService startup complete" -ForegroundColor Green
} finally {
    # Always restore original directory
    Set-Location $OriginalLocation
    Write-Host "Restored to original directory: $OriginalLocation" -ForegroundColor Gray
}
