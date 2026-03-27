# Uninstall old service and reinstall with correct collectors

Write-Host "Uninstalling current windows_exporter service..."
$MsiPath = "$env:TEMP\windows_exporter.msi"

# Uninstall
Start-Process msiexec.exe -ArgumentList "/x `"$MsiPath`" /quiet /norestart" -Verb RunAs -Wait

Write-Host "Waiting for uninstall to complete..."
Start-Sleep -Seconds 5

# Reinstall with correct collectors
Write-Host "Reinstalling with correct collectors..."
$Collectors = "cpu,memory,logical_disk,physical_disk,net,os,system"
Start-Process msiexec.exe -ArgumentList "/i `"$MsiPath`" /quiet /norestart ENABLED_COLLECTORS=$Collectors" -Verb RunAs -Wait

Write-Host "Waiting for installation to complete..."
Start-Sleep -Seconds 5

# Start the service
Write-Host "Starting windows_exporter service..."
Start-Process powershell.exe -ArgumentList "-Command `"Start-Service windows_exporter`"" -Verb RunAs -Wait

Start-Sleep -Seconds 3

# Check status
$Service = Get-Service -Name "windows_exporter" -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host ""
    Write-Host "Service Status: $($Service.Status)"
    if ($Service.Status -eq "Running") {
        Write-Host "SUCCESS! windows_exporter is running!"
        Write-Host "Metrics: http://localhost:9182/metrics"
    } else {
        Write-Host "Service exists but is not running. Status: $($Service.Status)"
    }
} else {
    Write-Host "Service not found after installation."
}
