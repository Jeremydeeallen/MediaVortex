# StopQualityCompareService.ps1
# PowerShell script to stop the QualityCompareService microservice

param(
    [switch]$Force,
    [switch]$Verbose
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$QualityCompareServiceDir = Join-Path $ScriptDir "QualityCompareService"
$MainScript = Join-Path $QualityCompareServiceDir "Main.py"

Write-Host "Stopping QualityCompareService..." -ForegroundColor Yellow

# Find running QualityCompareService processes
$ProcessName = "python"
$ProcessArgs = $MainScript
$RunningProcesses = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*$ProcessArgs*"
}

if (-not $RunningProcesses) {
    Write-Host "No QualityCompareService processes found" -ForegroundColor Green
    exit 0
}

Write-Host "Found $($RunningProcesses.Count) QualityCompareService process(es)" -ForegroundColor Cyan

foreach ($Process in $RunningProcesses) {
    Write-Host "Stopping process PID: $($Process.Id)" -ForegroundColor Yellow
    
    try {
        if ($Force) {
            Write-Host "Force stopping process..." -ForegroundColor Red
            Stop-Process -Id $Process.Id -Force
        } else {
            Write-Host "Gracefully stopping process..." -ForegroundColor Yellow
            # Send SIGTERM equivalent (Ctrl+C)
            $Process.CloseMainWindow()
            
            # Wait for graceful shutdown
            $Timeout = 10
            $Elapsed = 0
            while (-not $Process.HasExited -and $Elapsed -lt $Timeout) {
                Start-Sleep -Milliseconds 500
                $Elapsed += 0.5
            }
            
            # Force kill if still running
            if (-not $Process.HasExited) {
                Write-Host "Process did not stop gracefully, force killing..." -ForegroundColor Red
                Stop-Process -Id $Process.Id -Force
            }
        }
        
        Write-Host "Process stopped successfully" -ForegroundColor Green
        
    } catch {
        Write-Error "Failed to stop process PID $($Process.Id): $_"
    }
}

# Wait a moment for cleanup
Start-Sleep -Seconds 2

# Verify all processes are stopped
$RemainingProcesses = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*$ProcessArgs*"
}

if ($RemainingProcesses) {
    Write-Warning "Some processes may still be running:"
    foreach ($Process in $RemainingProcesses) {
        Write-Host "  PID: $($Process.Id)" -ForegroundColor Red
    }
    Write-Host "Use -Force parameter to force stop all processes" -ForegroundColor Yellow
} else {
    Write-Host "All QualityCompareService processes stopped successfully" -ForegroundColor Green
}

Write-Host "QualityCompareService shutdown complete" -ForegroundColor Green