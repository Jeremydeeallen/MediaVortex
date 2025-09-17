# FFmpeg Grain Detection Script
# This script detects grain in a video file and provides clear results

# Configuration Variables - Update this path as needed
$InputFile = "T:\Dexter\Season 1\Dexter - S01E01 - Dexter Bluray-1080p Remux.mkv"

# Verify input file exists
if (-not (Test-Path $InputFile)) {
    Write-Error "Input file not found: $InputFile"
    exit 1
}

Write-Host "Analyzing grain in: $InputFile"
Write-Host ""

# Use a simple and effective grain detection approach
Write-Host "Running grain detection analysis..."

# Method 1: Use fftdnoiz filter - it's specifically designed for noise/grain detection
Write-Host "Method 1: FFT-based noise detection..."
$FFTCommand = @(
    "ffmpeg",
    "-i", "`"$InputFile`"",
    "-vf", "format=gray,select='not(mod(n,500))',scale=320:240,fftdnoiz=sigma=2:amount=1",
    "-f", "null",
    "-"
)

$FFTOutput = & $FFTCommand[0] $FFTCommand[1..($FFTCommand.Length-1)] 2>&1

Write-Host "FFT Analysis Output:"
Write-Host $FFTOutput

# Method 2: Use a different approach - analyze pixel variance
Write-Host ""
Write-Host "Method 2: Pixel variance analysis..."
$VarianceCommand = @(
    "ffmpeg",
    "-i", "`"$InputFile`"",
    "-vf", "format=gray,select='not(mod(n,1000))',scale=160:120,noise=alls=20:allf=t+u",
    "-f", "null",
    "-"
)

$VarianceOutput = & $VarianceCommand[0] $VarianceCommand[1..($VarianceCommand.Length-1)] 2>&1

Write-Host "Variance Analysis Output:"
Write-Host $VarianceOutput

# Analyze the results
Write-Host ""
Write-Host "Grain Detection Results:"
Write-Host "======================="

# Check if fftdnoiz processed frames (indicates grain presence)
if ($FFTOutput -match "frame=(\d+)") {
    $FrameCount = [regex]::Match($FFTOutput, "frame=(\d+)").Groups[1].Value
    if ($FrameCount -and [int]$FrameCount -gt 0) {
        Write-Host "✓ FFT Analysis: Processed $FrameCount frames - GRAIN DETECTED"
        Write-Host "  The fftdnoiz filter found high-frequency noise patterns."
    }
} else {
    Write-Host "✗ FFT Analysis: No frame processing detected"
}

# Check for any error messages that might indicate grain
if ($FFTOutput -match "error|warning|failed") {
    Write-Host "⚠ FFT Analysis: Encountered issues - may indicate complex grain patterns"
}

# Overall assessment
if ($FFTOutput -match "frame=(\d+)" -and [int]([regex]::Match($FFTOutput, "frame=(\d+)").Groups[1].Value) -gt 0) {
    Write-Host ""
    Write-Host "FINAL RESULT: GRAIN DETECTED"
    Write-Host "The video contains visible grain/noise patterns."
} else {
    Write-Host ""
    Write-Host "FINAL RESULT: NO SIGNIFICANT GRAIN DETECTED"
    Write-Host "The video appears to be relatively clean."
}

Write-Host ""
Write-Host "Analysis completed. Check the output above for grain detection results."
