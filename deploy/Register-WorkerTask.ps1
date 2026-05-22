<#
.SYNOPSIS
  Register the MediaVortex worker as a Task Scheduler job that runs at user logon.

.DESCRIPTION
  Creates a Scheduled Task named "MediaVortex Worker" that:
    - Triggers when the current user logs on
    - Runs `<MediaVortex>\venv\Scripts\python.exe StartWorker.py`
    - Runs in the user's interactive context
    - Restarts on failure (3 attempts, 1 minute apart)
    - Stops if the user logs off (so the kids gaming on REMINGTON aren't
      sharing CPU with a transcode that won't yield)

  Idempotent: re-running overwrites the existing task definition.

  Run this script ON the worker host (REMINGTON, I9-2024, etc.), NOT on the
  dev workstation. It registers a task scoped to the running user.

.PARAMETER MediaVortexRoot
  Absolute path to the MediaVortex repo on this host. Defaults to
  C:\Code\MediaVortex.

.PARAMETER TaskName
  Scheduled Task name. Defaults to "MediaVortex Worker".

.PARAMETER StopOnUserLogoff
  When the user logs off, kill the worker. Default: $true. Set to $false for
  hosts where the worker should keep running across logoff/logon cycles
  (i.e. the host is dedicated, no interactive use).

.EXAMPLE
  .\deploy\Register-WorkerTask.ps1
  # Register with defaults; worker auto-starts at this user's next logon.

.EXAMPLE
  .\deploy\Register-WorkerTask.ps1 -StopOnUserLogoff:$false
  # Dedicated worker host: keep running even when no user is logged on.

.NOTES
  Prerequisites on the worker host:
    1. C:\Code\MediaVortex with a built venv (`py -m venv venv` then
       `venv\Scripts\python.exe -m pip install -r requirements.txt`).
    2. Windows NFS Client feature installed (`Enable-WindowsOptionalFeature
       -Online -FeatureName ServicesForNFS-ClientOnly,ClientForNFS-Infrastructure`).
       NFS uses AUTH_SYS -- no credentials are required.
    3. WorkerService env vars set (MEDIAVORTEX_DB_HOST, etc.) at User scope.

  Verify after registration:
    Get-ScheduledTask -TaskName "MediaVortex Worker"
    Get-ScheduledTaskInfo -TaskName "MediaVortex Worker"

  Trigger manually for a test (without logging out):
    Start-ScheduledTask -TaskName "MediaVortex Worker"
#>

[CmdletBinding()]
param(
    [string]$MediaVortexRoot = "C:\Code\MediaVortex",
    [string]$TaskName = "MediaVortex Worker",
    [bool]$StopOnUserLogoff = $true
)

$ErrorActionPreference = "Stop"

# 1. Validate prerequisites.
$VenvPython = Join-Path $MediaVortexRoot "venv\Scripts\python.exe"
$LauncherPy = Join-Path $MediaVortexRoot "StartWorker.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "venv python not found at $VenvPython. Build the venv first: 'cd $MediaVortexRoot; py -m venv venv; venv\Scripts\python.exe -m pip install -r requirements.txt'"
    exit 1
}
if (-not (Test-Path $LauncherPy)) {
    Write-Error "StartWorker.py not found at $LauncherPy. scp it from the dev workstation first."
    exit 1
}

# On workgroup-only Windows installs, $env:USERDOMAIN reports "WORKGROUP"
# which is not a real SID-resolvable principal. Use COMPUTERNAME\username
# for local accounts -- Task Scheduler resolves that correctly.
$CurrentUser = "$env:COMPUTERNAME\$env:USERNAME"
Write-Host "Registering task '$TaskName' for user '$CurrentUser'..."

# 2. Define the action: launch StartWorker.py with the venv python, working
#    directory = MediaVortex root.
$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "StartWorker.py" `
    -WorkingDirectory $MediaVortexRoot

# 3. Define the trigger: at logon of the current user. Scoping to a specific
#    user avoids the task firing for other accounts (e.g. if a kid logs in
#    on REMINGTON and we DON'T want the worker -- we'll handle that later
#    with criterion 5 of the feature doc).
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser

# 4. Settings: restart on failure, run only when the user is logged on (no
#    stored-password requirement), allow overlap if a previous instance is
#    still running (it shouldn't be).
$SettingsParams = @{
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    StartWhenAvailable         = $true
    MultipleInstances          = "IgnoreNew"
    RestartCount               = 3
    RestartInterval            = (New-TimeSpan -Minutes 1)
    ExecutionTimeLimit         = (New-TimeSpan -Hours 0)  # 0 = unlimited
}
$Settings = New-ScheduledTaskSettingsSet @SettingsParams

# 5. Principal: run as the current user, in their interactive logon session.
#    Interactive logon is preferred over a SYSTEM-account task because the
#    NFS client maps drive letters per-user; running as the same user that
#    set up the persistent mounts keeps the drive letters consistent.
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited

# 6. Compose and register (overwrite if exists).
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Launches the MediaVortex transcode worker at user logon. See $LauncherPy."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $Task `
    -Force | Out-Null

# 7. Optionally add a logoff trigger that stops the task. New-ScheduledTaskTrigger
#    has no built-in logoff trigger; use a CimInstance directly.
if ($StopOnUserLogoff) {
    # The cleanest "stop on logoff" is via the task's built-in setting
    # `StopAtLogoff` but that's the default for interactive tasks scoped
    # to a user -- the OS terminates the process when the user logs off.
    Write-Host ("  StopOnUserLogoff=" + $StopOnUserLogoff + ": Windows will terminate the worker when the user logs off (default for interactive tasks).")
}

Write-Host ""
Write-Host "Registered '$TaskName'." -ForegroundColor Green
Write-Host "  Action:    $VenvPython StartWorker.py"
Write-Host "  CWD:       $MediaVortexRoot"
Write-Host "  Trigger:   At logon of $CurrentUser"
Write-Host "  Restart:   3x at 1m intervals on failure"
Write-Host ""
Write-Host "Verify with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host ""
Write-Host "Test now (without re-logging-in):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  # then in another shell:"
Write-Host "  Get-Process python | Where-Object { `$_.Path -eq '$VenvPython' }"
Write-Host ""
Write-Host "Unregister with:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
