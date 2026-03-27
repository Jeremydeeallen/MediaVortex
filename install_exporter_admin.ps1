$MsiPath = "$env:TEMP\windows_exporter.msi"

if (-not (Test-Path $MsiPath)) {
    Write-Host "ERROR: MSI file not found at $MsiPath"
    exit 1
}

Write-Host "Installing windows_exporter from: $MsiPath"
Write-Host "This requires administrator privileges..."
Write-Host ""

$Arguments = "/i `"$MsiPath`" /quiet /norestart ENABLED_COLLECTORS=cpu,cs,logical_disk,net,os,system,memory"

try {
    $Process = Start-Process msiexec.exe -ArgumentList $Arguments -Verb RunAs -Wait -PassThru

    Write-Host "Installation completed with exit code: $($Process.ExitCode)"

    if ($Process.ExitCode -eq 0) {
        Write-Host "Success! Waiting for service to register..."
        Start-Sleep -Seconds 3

        $Service = Get-Service -Name "windows_exporter" -ErrorAction SilentlyContinue
        if ($Service) {
            Write-Host "Service found: $($Service.Status)"
            if ($Service.Status -ne "Running") {
                Write-Host "Starting service..."
                Start-Service "windows_exporter"
            }
            Write-Host ""
            Write-Host "windows_exporter is now running!"
            Write-Host "Metrics endpoint: http://localhost:9182/metrics"
        } else {
            Write-Host "WARNING: Service not found yet. May need to restart."
        }
    } else {
        Write-Host "Installation failed with exit code: $($Process.ExitCode)"
    }
} catch {
    Write-Host "ERROR: $_"
    exit 1
}
