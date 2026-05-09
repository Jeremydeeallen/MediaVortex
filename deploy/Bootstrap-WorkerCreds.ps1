<#
.SYNOPSIS
  Stash SMB credentials in Windows Credential Manager so New-SmbMapping can
  mount shares without inline passwords.

.DESCRIPTION
  Reads a JSON object from stdin in this shape:

    {
      "10.0.0.40": { "user": "media",     "password": "..." },
      "10.0.0.61": { "user": "jallen11",  "password": "..." }
    }

  For each entry, runs:

    cmdkey /add:<host> /user:<user> /pass:<password>

  Idempotent: cmdkey overwrites an existing entry for the same target with
  no prompt. The credential is stored encrypted at rest via DPAPI, scoped to
  the user account that runs this script. New-SmbMapping with no
  -UserName/-Password automatically uses the matching cached credential.

  This script never echoes passwords. Output reports only the target name
  and the cmdkey exit code.

.NOTES
  - Run this ON the worker host (the user account that will run the worker),
    not on the dev workstation.
  - Pipe the JSON via SSH stdin to keep credentials off the command line.

  Local-side (dev workstation) example:

    py -c "
    import json, subprocess
    from terraform import secrets
    creds = {
      '10.0.0.40': {'user':'media','password':secrets.get('homelab/brain/cifs-media')},
      '10.0.0.61': {'user':'jallen11','password':secrets.get('homelab/synology/jallen11')},
    }
    subprocess.run(
      ['ssh','owner@<target-ip>',
       'powershell -NoProfile -File C:\\Code\\MediaVortex\\deploy\\Bootstrap-WorkerCreds.ps1'],
      input=json.dumps(creds), text=True, check=True)
    "

.EXAMPLE
  Get-Content creds.json | .\deploy\Bootstrap-WorkerCreds.ps1
  # Local-only test from a JSON file.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# 1. Read JSON from stdin.
$Raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($Raw)) {
    Write-Error "No input on stdin. Pipe the credentials JSON to this script."
    exit 1
}

try {
    $Creds = $Raw | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Error "Could not parse stdin as JSON: $($_.Exception.Message)"
    exit 1
}

# 2. For each host entry, call cmdkey. Iterate via NoteProperty enumeration
#    because the parsed JSON is a PSCustomObject, not a hashtable.
$Targets = $Creds.PSObject.Properties | Where-Object { $_.MemberType -eq 'NoteProperty' }
if (-not $Targets) {
    Write-Error "JSON contained no host entries."
    exit 1
}

$Failures = @()
foreach ($Property in $Targets) {
    $TargetHost = $Property.Name
    $Entry = $Property.Value
    if (-not $Entry.user -or -not $Entry.password) {
        Write-Host "  [SKIP] $TargetHost : missing 'user' or 'password' field"
        $Failures += $TargetHost
        continue
    }

    # cmdkey writes "CMDKEY: Credential added successfully." on success.
    # Capture but don't echo.
    $null = cmdkey /add:$TargetHost /user:$($Entry.user) /pass:$($Entry.password)
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK]   $TargetHost (user=$($Entry.user)) stored"
    } else {
        Write-Host "  [FAIL] $TargetHost : cmdkey exit $LASTEXITCODE"
        $Failures += $TargetHost
    }
}

# 3. Drop the JSON blob from memory now that we're done with it.
Remove-Variable Raw, Creds -Force -ErrorAction SilentlyContinue

if ($Failures.Count -gt 0) {
    Write-Host ""
    Write-Error "Failed to stash credentials for: $($Failures -join ', ')"
    exit 1
}

Write-Host ""
Write-Host "All credentials stored." -ForegroundColor Green
Write-Host "Verify (no plaintext shown): cmdkey /list"
Write-Host "New-SmbMapping with no -UserName/-Password will now auto-resolve them."
