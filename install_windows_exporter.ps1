$ProgressPreference = 'SilentlyContinue'
$Version = "0.31.5"
$DownloadUrl = "https://github.com/prometheus-community/windows_exporter/releases/download/v$Version/windows_exporter-$Version-amd64.msi"
$OutFile = "$env:TEMP\windows_exporter.msi"

Write-Host "Downloading windows_exporter v$Version..."
Invoke-WebRequest -Uri $DownloadUrl -OutFile $OutFile -UseBasicParsing

Write-Host "Downloaded to: $OutFile"
Write-Host "Installing windows_exporter..."
Write-Host "This will require administrator privileges and may show a UAC prompt."
Write-Host ""

# Install with default collectors
Start-Process msiexec.exe -ArgumentList "/i `"$OutFile`" /quiet /norestart ENABLED_COLLECTORS=cpu,cs,logical_disk,net,os,system,memory" -Wait -NoNewWindow

Write-Host ""
Write-Host "Installation complete. Checking service status..."
Start-Sleep -Seconds 2

$Service = Get-Service -Name "windows_exporter" -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host "Service Status: $($Service.Status)"
    if ($Service.Status -eq "Running") {
        Write-Host "windows_exporter is running successfully!"
        Write-Host "Metrics available at: http://localhost:9182/metrics"
    } else {
        Write-Host "Starting service..."
        Start-Service "windows_exporter"
        Write-Host "Service started."
    }
} else {
    Write-Host "Service not found. Installation may have failed."
}
