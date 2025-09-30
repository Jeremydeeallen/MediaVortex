# StartSystemOrchestrator.ps1
# PowerShell script to start the SystemOrchestratorService (master controller)

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
$SystemOrchestratorDir = Join-Path $ScriptDir "SystemOrchestratorService"
$VenvPath = Join-Path $SystemOrchestratorDir "venv"
$MainScript = Join-Path $SystemOrchestratorDir "Main.py"

Write-Host "Starting SystemOrchestratorService (MediaVortex Master Controller)..." -ForegroundColor Green

# Check if SystemOrchestratorService directory exists
if (-not (Test-Path $SystemOrchestratorDir)) {
    Write-Error "SystemOrchestratorService directory not found: $SystemOrchestratorDir"
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path $VenvPath)) {
    Write-Error "Virtual environment not found: $VenvPath"
    Write-Host "Please create the virtual environment first:" -ForegroundColor Yellow
    Write-Host "  cd SystemOrchestratorService" -ForegroundColor Yellow
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
    Write-Warning "SystemOrchestratorService appears to be already running (PID: $($ExistingProcess.Id))"
    Write-Host "Use StopSystemOrchestrator.ps1 to stop it first, or use -Force to restart" -ForegroundColor Yellow
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
$RequirementsFile = Join-Path $SystemOrchestratorDir "requirements.txt"
if (Test-Path $RequirementsFile) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r $RequirementsFile
}

# Change to SystemOrchestratorService directory
Set-Location $SystemOrchestratorDir

try {
    # Start the service
    Write-Host "Starting SystemOrchestratorService..." -ForegroundColor Green
    Write-Host "Working Directory: $SystemOrchestratorDir" -ForegroundColor Gray
    Write-Host "Python Script: $MainScript" -ForegroundColor Gray
    Write-Host "This will start all MediaVortex services:" -ForegroundColor Cyan
    Write-Host "  - MediaVortex (Web UI on port 5000)" -ForegroundColor Gray
    Write-Host "  - TranscodeService (Transcoding operations)" -ForegroundColor Gray
    Write-Host "  - QualityCompareService (Quality testing)" -ForegroundColor Gray

    if ($Background) {
        Write-Host "Starting in background..." -ForegroundColor Yellow
        Start-Process -FilePath "python" -ArgumentList $MainScript -WorkingDirectory $SystemOrchestratorDir -WindowStyle Hidden
        Write-Host "SystemOrchestratorService started in background" -ForegroundColor Green
        Write-Host "All MediaVortex services should be starting..." -ForegroundColor Green
    } else {
        Write-Host "Starting in foreground (Ctrl+C to stop all services)..." -ForegroundColor Yellow
        try {
            python $MainScript
        } catch {
            Write-Error "Failed to start SystemOrchestratorService: $_"
            throw
        }
    }

    Write-Host "SystemOrchestratorService startup complete" -ForegroundColor Green
} finally {
    # Always restore original directory
    Set-Location $OriginalLocation
    Write-Host "Restored to original directory: $OriginalLocation" -ForegroundColor Gray
}
