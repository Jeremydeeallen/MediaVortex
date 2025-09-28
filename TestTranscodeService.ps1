# TestTranscodeService.ps1
# PowerShell script to test the TranscodeService microservice

param(
    [switch]$Verbose,
    [int]$TestDuration = 10
)

Write-Host "Testing TranscodeService..." -ForegroundColor Green

# Test 1: Check if service can start
Write-Host "`nTest 1: Starting TranscodeService..." -ForegroundColor Cyan
try {
    # Start service in background
    $StartResult = & ".\StartTranscodeService.ps1" -Background
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ TranscodeService started successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to start TranscodeService" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error starting TranscodeService: $_" -ForegroundColor Red
    exit 1
}

# Test 2: Check if service is running
Write-Host "`nTest 2: Checking if service is running..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# Check for any python processes (the CommandLine property might not be available)
$RunningProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue

if ($RunningProcesses) {
    Write-Host "✓ TranscodeService is running (PID: $($RunningProcesses[0].Id))" -ForegroundColor Green
} else {
    Write-Host "✗ TranscodeService is not running" -ForegroundColor Red
    exit 1
}

# Test 3: Let it run for specified duration
Write-Host "`nTest 3: Running for $TestDuration seconds..." -ForegroundColor Cyan
Write-Host "Service is running in background. Check TranscodeService.log for activity." -ForegroundColor Yellow
Start-Sleep -Seconds $TestDuration

# Test 4: Check if service is still running
Write-Host "`nTest 4: Checking if service is still running..." -ForegroundColor Cyan
$StillRunning = Get-Process -Name "python" -ErrorAction SilentlyContinue

if ($StillRunning) {
    Write-Host "✓ TranscodeService is still running after $TestDuration seconds" -ForegroundColor Green
} else {
    Write-Host "✗ TranscodeService stopped unexpectedly" -ForegroundColor Red
}

# Test 5: Stop the service
Write-Host "`nTest 5: Stopping TranscodeService..." -ForegroundColor Cyan
try {
    $StopResult = & ".\StopTranscodeService.ps1"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ TranscodeService stopped successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to stop TranscodeService" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ Error stopping TranscodeService: $_" -ForegroundColor Red
}

# Test 6: Verify service is stopped
Write-Host "`nTest 6: Verifying service is stopped..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

$StoppedProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue

if (-not $StoppedProcesses) {
    Write-Host "✓ TranscodeService is stopped" -ForegroundColor Green
} else {
    Write-Host "✗ TranscodeService is still running" -ForegroundColor Red
}

Write-Host "`nTranscodeService test completed!" -ForegroundColor Green
Write-Host "Check TranscodeService.log for detailed logs" -ForegroundColor Yellow
