# ====================================================================
# MEDIAVORTEX: STEP 1 - HIGH-VELOCITY HARDWARE TRANSCODE ENGINE
# ====================================================================
# Focused exclusively on RTX 4060 Ti AV1 Hardware Optimization & Audio Knobs

# --- CONFIGURATION MATRIX ("THE KNOBS") ---
$SourceFile     = "c:\myvideo.mkv"
$TargetWidth    = 1280
$TargetHeight   = 0

$FFmpegPath     = "C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
$FFprobePath    = "C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"

$GlobalTrackedErrorPreference = $ErrorActionPreference

# --- SEAM 0: CORE ENVIRONMENT VALIDATION ---
Write-Host "`n[ ] Executing Environment Validation Seam..." -ForegroundColor Gray

if (-not (Test-Path $FFmpegPath)) {
    Write-Host "[!] ENV CRITICAL FAILURE: FFmpeg executable missing at target path: $FFmpegPath" -ForegroundColor Red
    Exit 1
}
if (-not (Test-Path $FFprobePath)) {
    Write-Host "[!] ENV CRITICAL FAILURE: FFprobe executable missing at target path: $FFprobePath" -ForegroundColor Red
    Exit 1
}
try {
    $SourceItem = Get-Item $SourceFile -ErrorAction Stop
    $OutputFile = Join-Path $SourceItem.DirectoryName ($SourceItem.BaseName + "_done.mp4")
} catch {
    Write-Host "[!] ENV CRITICAL FAILURE: Target source file tracking or path mapping resolution failed." -ForegroundColor Red
    Exit 1
}

# Enforce Idempotency: Purge legacy transcode assets
Write-Host "[+] Cleaning environment workspace to guarantee idempotency..." -ForegroundColor Green
if (Test-Path $OutputFile) { 
    Remove-Item $OutputFile -Force -ErrorAction Stop 
    Write-Host "    -> Stale transcode asset purged successfully." -ForegroundColor Gray
}

# --- SEAM 1b: METADATA CAPTURE - BITRATE ANALYSIS ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "SEAM 1b: Querying Video Stream Bit Budget via FFprobe..." -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$RawBitrate = ""
try {
    $ProbeBitrateCmd = & $FFprobePath -v error -select_streams v:0 -show_entries stream=bit_rate -of csv=p=0 $SourceFile 2>&1
    $RawBitrate = ("$ProbeBitrateCmd").Trim()

    if ([string]::IsNullOrEmpty($RawBitrate) -or $RawBitrate -eq "N/A" -or $RawBitrate -eq "0" -or $RawBitrate -match "Error") {
        Write-Host "[!] Stream header bitrate missing. Querying Container Header Fallback..." -ForegroundColor Yellow
        $ProbeFormatCmd = & $FFprobePath -v error -show_entries format=bit_rate -of csv=p=0 $SourceFile 2>&1
        $RawBitrate = ("$ProbeFormatCmd").Trim()
    }

    $SourceBitrate = [double]$RawBitrate
    $ReadableSrcBitrate = [math]::Round(($SourceBitrate / 1000), 2)
    Write-Host "[+] Successfully Validated Source Media Bitrate: $ReadableSrcBitrate kbps" -ForegroundColor Green
} catch {
    Write-Host "`n[!] CRITICAL FAILURE AT METADATA SEAM 1b (Bitrate Extraction)" -ForegroundColor Red
    Exit 1
}

# --- AUTOMATED VBR BUDGET CALCULATION ENGINE ---
if ($TargetWidth -gt 0 -and $TargetWidth -lt 1920) {
    $CalcBitrate = [math]::Round(($SourceBitrate * 0.30) / 1000)
    if ($CalcBitrate -lt 350)  { $CalcBitrate = 350 }
    if ($CalcBitrate -gt 600)  { $CalcBitrate = 600 } 
    Write-Host "[Mod] Applying Storage-Optimized 720p Modifier." -ForegroundColor Cyan
} else {
    $CalcBitrate = [math]::Round(($SourceBitrate * 0.75) / 1000)
    if ($CalcBitrate -lt 1000) { $CalcBitrate = 1000 }
    if ($CalcBitrate -gt 2500) { $CalcBitrate = 2500 }
    Write-Host "[Mod] Applying Native Resolution Modifier." -ForegroundColor Cyan
}
$CalcMaxRate = [math]::Round($CalcBitrate * 2.0)
$CalcBufSize = $CalcMaxRate

Write-Host "[VBR Constraints Set] -> Target Base: ${CalcBitrate}k | Max Peak: ${CalcMaxRate}k | Buffer: ${CalcBufSize}k" -ForegroundColor Green

# --- SEAM 2: HIGH-VELOCITY HARDWARE NVENC ENCODING PASS ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "SEAM 2: Starting RTX 4060 Ti AV1 Hardware Transcode..." -ForegroundColor Cyan
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan

$FFmpegArgs = @("-i", $SourceFile, "-map", "0:v:0", "-map", "0:a:0")

if ($TargetWidth -gt 0 -or $TargetHeight -gt 0) {
    $W = if ($TargetWidth -gt 0) { $TargetWidth } else { -1 }
    $H = if ($TargetHeight -gt 0) { $TargetHeight } else { -1 }
    $FFmpegArgs += @("-vf", "scale=w=$W:h=$H")
    Write-Host "Scale Target Confirmed: Resizing output target to ${W}x${H}." -ForegroundColor Cyan
} else {
    Write-Host "No scale target specified. Preserving original frame dimensions." -ForegroundColor Gray
}

$FFmpegArgs += @(
    "-c:v", "av1_nvenc", 
    "-preset", "p7", 
    "-tune", "hq", 
    "-multipass", "fullres", 
    "-rc", "vbr", 
    "-b:v", "${CalcBitrate}k", 
    "-maxrate:v", "${CalcMaxRate}k", 
    "-bufsize:v", "${CalcBufSize}k", 
    "-rc-lookahead", "20", 
    "-bf", "4", 
    "-b_ref_mode", "middle", 
    "-temporal-aq", "1", 
    "-spatial-aq", "1", 
    "-c:a", "aac", 
    "-ac", "2", 
    "-b:a", "96k", 
    "-af", "loudnorm=I=-23:LRA=15.00:TP=-2:linear=true", 
    "-pix_fmt", "p010le", 
    "-f", "mp4", 
    "-movflags", "+faststart", 
    "-metadata", "comment=Transcoded by MediaVortex", 
    "-y", $OutputFile
)

$ErrorActionPreference = "SilentlyContinue"
& $FFmpegPath $FFmpegArgs
$ErrorActionPreference = $GlobalTrackedErrorPreference

# Perform Physical Asset Verification Pass
if (-not (Test-Path $OutputFile)) {
    Write-Host "`n[!] CRITICAL FAILURE: Output asset missing." -ForegroundColor Red
    Exit 1
}

$OutputFileLength = (Get-Item $OutputFile).Length
if ($OutputFileLength -le 0) {
    Write-Host "`n[!] CRITICAL FAILURE: File is empty or corrupt." -ForegroundColor Red
    Exit 1
}

Write-Host "`n------------------------------------------------------------" -ForegroundColor Green
Write-Host "[+] TRANSCODE SUCCESSFUL: ($([math]::Round($OutputFileLength/1MB, 2)) MB)" -ForegroundColor Green
Write-Host "Output File Ready for Analysis: $OutputFile" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Green