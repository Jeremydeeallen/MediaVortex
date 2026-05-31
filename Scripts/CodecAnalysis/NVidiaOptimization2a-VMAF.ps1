
# ====================================================================
# MEDIAVORTEX: STEP 2 - STANDALONE SYNCHRONIZED VMAF ANALYZER
# ====================================================================
# Evaluates metrics by matching the reference source file and transcoded file

# --- CONFIGURATION MATRIX ("THE KNOBS") ---
$SourceFile     = "c:\myvideo.mkv"
$TranscodedFile = "c:\myvideo_done.mp4"
$TargetWidth    = 1280
$TargetHeight   = 0

$FFmpegPath     = "C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
$FFprobePath    = "C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"

# --- ENVIRONMENT SEAM VALIDATION ---
if (-not (Test-Path $FFmpegPath) -or -not (Test-Path $FFprobePath)) {
    Write-Host "[!] ENV CRITICAL FAILURE: Executables missing." -ForegroundColor Red
    Exit 1
}
if (-not (Test-Path $SourceFile) -or -not (Test-Path $TranscodedFile)) {
    Write-Host "[!] ANALYSIS FAILURE: Missing inputs. Ensure step 1 completed successfully." -ForegroundColor Red
    Write-Host "Verify Reference Path : $SourceFile" -ForegroundColor Yellow
    Write-Host "Verify Transcoded Path: $TranscodedFile" -ForegroundColor Yellow
    Exit 1
}

$SourceItem = Get-Item $SourceFile
$LogPath    = Join-Path $SourceItem.DirectoryName ($SourceItem.BaseName + "_vmaf.json")

# Enforce Idempotency for telemetries
if (Test-Path $LogPath) { 
    Remove-Item $LogPath -Force 
    Write-Host "[+] Cleaned stale telemetry log." -ForegroundColor Gray
}

# --- EXTRACT REFERENCE FPS FOR METRIC SYNCHRONIZATION ---
Write-Host "`n[ ] Querying Reference Frame Rate for synchronization layout..." -ForegroundColor Gray
$ProbeResult = & $FFprobePath -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 $SourceFile 2>&1
$ProbeResult = ("$ProbeResult").Trim()

if ($ProbeResult -match "(\d+)/(\d+)") {
    $SourceFPS = [math]::Round(([double]$Matches[1] / [double]$Matches[2]), 3)
} else {
    $SourceFPS = [double]$ProbeResult
}
Write-Host "[+] Sync Target Formatted: $SourceFPS FPS" -ForegroundColor Green

# --- CONSTRUCT SYNCHRONIZATION FILTER COMPLEX ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Magenta
Write-Host "Running Synchronized Frame-by-Frame VMAF Analysis..." -ForegroundColor Magenta
Write-Host "------------------------------------------------------------" -ForegroundColor Magenta

$ScaleFilter = ""
if ($TargetWidth -gt 0 -or $TargetHeight -gt 0) {
    $W = if ($TargetWidth -gt 0) { $TargetWidth } else { -1 }
    $H = if ($TargetHeight -gt 0) { $TargetHeight } else { -1 }
    $ScaleFilter = "scale=w=$W:h=$H,"
}

# Clean backslashes for internal FFmpeg libvmaf json string syntax parsing
$VmafLogNormalized = $LogPath.Replace('\', '/')

# Direct layout matching matrix graph
$VmafFilterComplex = "[0:v]format=yuv420p10le,fps=fps=$SourceFPS,setpts=PTS-STARTPTS[transcoded];[1:v]${ScaleFilter}format=yuv420p10le,fps=fps=$SourceFPS,setpts=PTS-STARTPTS[reference];[transcoded][reference]libvmaf=log_fmt=json:log_path='${VmafLogNormalized}':n_threads=4"

$VmafArgs = @(
    "-i", $TranscodedFile, 
    "-i", $SourceFile, 
    "-filter_complex", $VmafFilterComplex, 
    "-f", "null", 
    "-"
)

# Launch analysis via native isolation handle tracking
$VmafProcess = Start-Process -FilePath $FFmpegPath -ArgumentList $VmafArgs -NoNewWindow -PassThru -Wait

# Validation Log Check
if ($VmafProcess.ExitCode -ne 0 -or -not (Test-Path $LogPath) -or (Get-Item $LogPath).Length -le 0) {
    Write-Host "`n[!] CRITICAL FAILURE: VMAF telemetry generation failed." -ForegroundColor Red
    Write-Host "Process Exit Code: $($VmafProcess.ExitCode)" -ForegroundColor Yellow
    Exit 1
}

Write-Host "`n------------------------------------------------------------" -ForegroundColor Green
Write-Host "VMAF Matrix Evaluation Complete!" -ForegroundColor Green
Write-Host "Telemetry Data Exported: $LogPath" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Green