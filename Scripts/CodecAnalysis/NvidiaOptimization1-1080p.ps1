# ====================================================================
# MEDIAVORTEX: TRANSCODE, SCALE, AUDIO ENHANCEMENT & VALIDATION
# ====================================================================

# --- CONFIGURATION VARIABLES ---
$SourceFile     = "c:\myvideo.mkv"

# Target Resolution Settings (Set to 1280 for 720p, or 0 to keep original native size)
$TargetWidth    = 1280
$TargetHeight   = 0

# --- AUTOMATED ENVIRONMENT DETECTION ---
$FFmpegPath     = "C:\\Code\\MediaVortex\\FFmpegMaster\\bin\\ffmpeg.exe"
$FFprobePath    = $FFmpegPath.Replace("ffmpeg.exe", "ffprobe.exe")

try {
    $SourceItem = Get-Item $SourceFile -ErrorAction Stop
    $OutputFile = Join-Path $SourceItem.DirectoryName ($SourceItem.BaseName + "_done1080.mp4")
    $LogPath    = Join-Path $SourceItem.DirectoryName ($SourceItem.BaseName + "_vmaf1080.json")
} catch {
    Write-Host "`n[!] CRITICAL FAILURE: File path resolution failed." -ForegroundColor Red
    Write-Host "Ensure '$SourceFile' actually exists." -ForegroundColor White
    Exit 1
}

# --- STEP 1a: AUTOMATICALLY EXTRACT SOURCE FRAME RATE ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Extracting source frame rate via FFprobe..." -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$ProbeCmdString = "& `"$FFprobePath`" -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 `"$SourceFile`""

try {
    $ProbeResult = & $FFprobePath -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 $SourceFile 2>&1
    $ProbeResult = ("$ProbeResult").Trim()

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($ProbeResult)) { 
        throw "FFprobe returned exit code $LASTEXITCODE or empty output. Raw message: $ProbeResult" 
    }
    
    if ($ProbeResult -match "(\d+)/(\d+)") {
        $SourceFPS = [math]::Round(([double]$Matches[1] / [double]$Matches[2]), 3)
    } else {
        $SourceFPS = [double]$ProbeResult
    }
    Write-Host "Detected Source Framerate: $SourceFPS FPS" -ForegroundColor Green
} catch {
    Write-Host "`n[!] CRITICAL FAILURE DURING METADATA EXTRACTION" -ForegroundColor Red
    Write-Host "Failed Command String:" -ForegroundColor Yellow
    Write-Host $ProbeCmdString -ForegroundColor Yellow
    Write-Host "`nError Details: $_" -ForegroundColor White
    Exit 1
}

# --- STEP 1b: EXTRACT NATIVE BITRATE & VALIDATE (FAIL-FAST WITH CONTAINER FALLBACK) ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Extracting source video stream bitrate via FFprobe..." -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$ProbeBitrateCmd = & $FFprobePath -v error -select_streams v:0 -show_entries stream=bit_rate -of csv=p=0 $SourceFile 2>&1
$RawBitrate = ("$ProbeBitrateCmd").Trim()

if ([string]::IsNullOrEmpty($RawBitrate) -or $RawBitrate -eq "N/A" -or [double]$RawBitrate -le 0) {
    Write-Host "[!] Stream-level bitrate is N/A. Querying container format header instead..." -ForegroundColor Yellow
    $ProbeFormatCmd = & $FFprobePath -v error -show_entries format=bit_rate -of csv=p=0 $SourceFile 2>&1
    $RawBitrate = ("$ProbeFormatCmd").Trim()
}

if ([string]::IsNullOrEmpty($RawBitrate) -or $RawBitrate -eq "N/A" -or $RawBitrate -match "[a-zA-Z]" -or [double]$RawBitrate -le 0) {
    Write-Host "`n[!] CRITICAL FAILURE: Source stream and container bitrates are both entirely missing." -ForegroundColor Red
    Write-Host "Raw FFprobe Output: '$RawBitrate'" -ForegroundColor Yellow
    Write-Host "Aborting execution immediately to prevent unmonitored VBR parameter estimation." -ForegroundColor Red
    Exit 1
}

$SourceBitrate = [double]$RawBitrate
$ReadableSrcBitrate = [math]::Round(($SourceBitrate / 1000), 2)
Write-Host "Detected Valid Bitrate Source: $ReadableSrcBitrate kbps" -ForegroundColor Green

# --- DYNAMIC VBR DATA BUDGET CALCULATION (STORAGE OPTIMIZED) ---
if ($TargetWidth -gt 0 -and $TargetWidth -lt 1920) {
    $CalcBitrate = [math]::Round(($SourceBitrate * 0.30) / 1000)
    
    if ($CalcBitrate -lt 350)  { $CalcBitrate = 350 }
    if ($CalcBitrate -gt 600)  { $CalcBitrate = 600 } 
    Write-Host "Applying Storage-Optimized 720p Modifier." -ForegroundColor Cyan
} else {
    $CalcBitrate = [math]::Round(($SourceBitrate * 0.75) / 1000)
    
    if ($CalcBitrate -lt 1000) { $CalcBitrate = 1000 }
    if ($CalcBitrate -gt 2500) { $CalcBitrate = 2500 }
    Write-Host "Applying Native Resolution Modifier." -ForegroundColor Cyan
}

$CalcMaxRate = [math]::Round($CalcBitrate * 2.0)
$CalcBufSize = $CalcMaxRate

Write-Host "Explicit VBR Constraints -> Base: ${CalcBitrate}k | Max: ${CalcMaxRate}k | Buffer: ${CalcBufSize}k" -ForegroundColor Green

# --- STEP 2: RUN THE BLAZING FAST NVIDIA AV1 TRANSCODE ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Starting RTX 4060 Ti AV1 Hardware Transcode..." -ForegroundColor Cyan
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan

$FFmpegArgs = @("-i", $SourceFile, "-map", "0:v:0", "-map", "0:a:0")

$ScaleFilter = ""
if ($TargetWidth -gt 0 -or $TargetHeight -gt 0) {
    $W = if ($TargetWidth -gt 0) { $TargetWidth } else { -1 }
    $H = if ($TargetHeight -gt 0) { $TargetHeight } else { -1 }
    
    $ScaleFilter = [string]::Format("scale=w={0}:h={1},", $W, $H)
    $PureVFParam = [string]::Format("scale=w={0}:h={1}", $W, $H)
    
    $FFmpegArgs += @("-vf", $PureVFParam)
    Write-Host "Scale Target Confirmed: Resizing output target to ${W}x${H}." -ForegroundColor Cyan
} else {
    Write-Host "No scale target specified. Preserving original frame dimensions." -ForegroundColor Gray
}

# Appending optimized video, audio downmix, 96k bits, and single-pass loudness normalization
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

& $FFmpegPath $FFmpegArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[!] CRITICAL FAILURE: FFmpeg transcoding engine crashed with exit code $LASTEXITCODE." -ForegroundColor Red
    Write-Host "Stopping execution immediately to prevent corrupted downstream validation workflows." -ForegroundColor Red
    Exit $LASTEXITCODE
}

# --- STEP 3: RUN THE ALIGNED VMAF ASSESSMENT ---
Write-Host "`n------------------------------------------------------------" -ForegroundColor Magenta
Write-Host "Running Synchronized Frame-by-Frame VMAF Analysis..." -ForegroundColor Magenta
Write-Host "------------------------------------------------------------" -ForegroundColor Magenta

if (-not (Test-Path $OutputFile)) {
    Write-Host "`n[!] CRITICAL FAILURE: Transcoded output file could not be located at: $OutputFile" -ForegroundColor Red
    Exit 1
}

$EscapedLogPath = $LogPath.Replace('\', '/').Replace(':', '\:')

$FilterString = [string]::Format("[0:v]format=yuv420p10le,fps=fps={0},setpts=PTS-STARTPTS[transcoded];[1:v]{1}format=yuv420p10le,fps=fps={0},setpts=PTS-STARTPTS[reference];[transcoded][reference]libvmaf=log_fmt=json:log_path='{2}':n_threads=4", $SourceFPS, $ScaleFilter, $EscapedLogPath)
$VmafCmdString = "& `"$FFmpegPath`" -i `"$OutputFile`" -i `"$SourceFile`" -filter_complex `"$FilterString`" -f null -"

& $FFmpegPath -i $OutputFile -i $SourceFile -filter_complex $FilterString -f null -

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[!] CRITICAL FAILURE: VMAF analysis filter engine crashed with exit code $LASTEXITCODE." -ForegroundColor Red
    Write-Host "Failed Command String:" -ForegroundColor Yellow
    Write-Host $VmafCmdString -ForegroundColor Yellow
    Exit $LASTEXITCODE
}

Write-Host "`n------------------------------------------------------------" -ForegroundColor Green
Write-Host "Process Complete! VMAF data saved to: $LogPath" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Green