
# 1. Set your file path here
$SourceFile = "C:\MV\ATKGirlfriends.25.11.21.Compilation.XXX.2160p.MP4-WRB.mp4"
$FFprobePath = "C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"
# 2. Get the real frame rate mathematically (avoids blank duration fields)
$RawFPS = & $FFprobePath -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 $SourceFile
if ($RawFPS.Contains("/")) {
    $SplitFPS = $RawFPS.Split("/")
    $FrameDuration = [double]$SplitFPS[1] / [double]$SplitFPS[0]
} else {
    $FrameDuration = 1 / [double]$RawFPS
}

Write-Host "[-] Analyzing frame packets (Frame Duration calculated at: $([math]::Round($FrameDuration, 5)) seconds)..." -ForegroundColor Cyan

# 3. Stream all frame sizes, multiply bytes to bits, divide by exact frame duration
& $FFprobePath -v error -select_streams v:0 -show_entries frame=pkt_size -of csv=p=0 $SourceFile | 
    Where-Object { $_ -match '^\d+$' } | 
    ForEach-Object { ([double]$_ * 8) / $FrameDuration } | 
    Measure-Object -Min -Max | 
    ForEach-Object {
        Write-Host "==========================================" -ForegroundColor Green
        Write-Host "Absolute Floor Packet Spurt:   $([math]::Round(($_.Minimum / 1Mb), 2)) Mbps" -ForegroundColor Green
        Write-Host "Absolute Ceiling Packet Spike: $([math]::Round(($_.Maximum / 1Mb), 2)) Mbps" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Green
    } 