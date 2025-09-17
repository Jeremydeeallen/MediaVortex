# FFmpeg VMAF Comparison Script
# This script compares video quality between source and transcoded files using VMAF

# Configuration Variables - Update these paths as needed
$SourceFile = "T:\Dexter\Season 1\Dexter - S01E01 - Dexter Bluray-1080p Remux.mkv"
$TranscodedFile = "c:\HandbrakeTemp\Dexter - S01E01 - Dexter Bluray-720p27grainsvtav1Score95.mkv"

# Simple output path - just write to VMAFComparison.json
$JsonOutputPath = "c:\HandbrakeTemp\VMAFComparison.json"

# Ensure the HandbrakeTemp directory exists
if (-not (Test-Path "c:\HandbrakeTemp")) {
    New-Item -ItemType Directory -Path "c:\HandbrakeTemp" -Force
    Write-Host "Created directory: c:\HandbrakeTemp"
}

# Verify source file exists
if (-not (Test-Path $SourceFile)) {
    Write-Error "Source file not found: $SourceFile"
    exit 1
}

# Verify transcoded file exists
if (-not (Test-Path $TranscodedFile)) {
    Write-Error "Transcoded file not found: $TranscodedFile"
    exit 1
}


Write-Host "Starting VMAF comparison..."
Write-Host "Source: $SourceFile"
Write-Host "Transcoded: $TranscodedFile"
Write-Host "JSON Output: $JsonOutputPath"
Write-Host ""

# Build and execute FFmpeg command
$FFmpegCommand = @(
    "ffmpeg",
    "-i", "`"$SourceFile`"",
    "-i", "`"$TranscodedFile`"",
    "-filter_complex", "[0:v]scale=1280:720,setsar=1[ref];[1:v]setsar=1[distorted];[distorted][ref]libvmaf=log_fmt=json",
    "-an",
    "-f", "null",
    "-"
)

Write-Host "Executing command:"
Write-Host ($FFmpegCommand -join " ")
Write-Host ""

# Execute the FFmpeg command and capture output
try {
    $VMAFOutput = & $FFmpegCommand[0] $FFmpegCommand[1..($FFmpegCommand.Length-1)] 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "VMAF comparison completed successfully!"
        
        # Extract JSON from the output (it will be mixed with other FFmpeg output)
        # Look for lines that start with { and end with }
        $JsonLines = $VMAFOutput | Where-Object { $_ -match '^\s*\{.*\}\s*$' }
        
        if ($JsonLines) {
            # Save the JSON output to file
            $JsonLines | Out-File -FilePath $JsonOutputPath -Encoding UTF8
            Write-Host "Results saved to: $JsonOutputPath"
            
            # Check file size
            if (Test-Path $JsonOutputPath) {
                $JsonFileSize = (Get-Item $JsonOutputPath).Length
                Write-Host "JSON file size: $JsonFileSize bytes"
                Write-Host "File created successfully at: $JsonOutputPath"
            }
        } else {
            Write-Warning "No JSON output found in FFmpeg results"
            Write-Host "FFmpeg output was:"
            $VMAFOutput | ForEach-Object { Write-Host "  $_" }
        }
    } else {
        Write-Error "FFmpeg command failed with exit code: $LASTEXITCODE"
        Write-Host "FFmpeg output was:"
        $VMAFOutput | ForEach-Object { Write-Host "  $_" }
        exit $LASTEXITCODE
    }
} catch {
    Write-Error "Error executing FFmpeg command: $($_.Exception.Message)"
    exit 1
}
