"""End-to-end deploy automation for a Windows-native MediaVortex worker.

Wraps the 8-step sequence in deploy/worker-deploy-windows.flow.md "Deploy Sequence
(Quick Reference)" into one idempotent invocation. Run from the dev
workstation against any Windows host that has Python 3.12+ and OpenSSH
Server installed.

WHEN TO USE THIS SCRIPT vs the hot-swap flow:
  - Fresh host, host rebuild, env-vars changed: this script.
  - In-place code update on a running worker (most common case): use the
    manual sequence in deploy/worker-deploy-windows.flow.md "Code-Only Update
    (Hot-Swap)" -- this script assumes a fresh host and does NOT stop the
    running worker before scp, so the running Python process holds file
    locks and the scp will fail or partially overwrite.

Steps:
  1. Pre-flight checks (Python, sshd, NetworkCategory, port reachability,
     NFS client feature installed)
  2. scp the MediaVortex repo to C:\\Code\\MediaVortex
  3. Recreate the venv (the source venv's pyvenv.cfg paths don't translate)
  4. Push DB env vars via SSH stdin -> -EncodedCommand
  5. Set the WorkerService's MEDIAVORTEX_MAX_CPU_THREADS hint (optional)
  6. Register the `MediaVortex Worker` Task Scheduler entry
  7. Trigger the task once to validate
  8. Verify the Workers row reaches Status='Online' with fresh heartbeat

Each step prints a one-line status. Idempotent: re-running on a
partially-deployed host completes only the missing steps.

NFS mounts use AUTH_SYS -- no credentials are required. The Windows NFS
client must be installed (Enable-WindowsOptionalFeature -Online -FeatureName
ClientForNFS-Infrastructure,ServicesForNFS-ClientOnly) and persistent drive
mappings established by the operator before this script runs. DB password
is read from MEDIAVORTEX_DB_PASSWORD env var on the dev workstation,
falling back to the project default `mediavortex` if unset.

Usage:
  py deploy/deploy-windows-worker.py 10.0.0.230
  py deploy/deploy-windows-worker.py 10.0.0.230 --check          # pre-flight only
  py deploy/deploy-windows-worker.py 10.0.0.230 --skip-scp       # repo already on host
  py deploy/deploy-windows-worker.py 10.0.0.230 --no-trigger     # register task, don't trigger now
  py deploy/deploy-windows-worker.py 10.0.0.230 --user owner

Exit codes:
  0  success (verified Online with fresh heartbeat)
  1  pre-flight check failed (host unreachable, missing prereqs)
  2  deploy step failed
  3  verification failed (worker not Online within 90 s, or stale heartbeat)
"""

import argparse
import base64
import datetime as _dt
import fnmatch
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

MediaVortexRoot = Path(__file__).resolve().parent.parent
DeployDir = MediaVortexRoot / "deploy"
RemoteRoot = r"C:\Code\MediaVortex"

# DB defaults (match deploy/worker-deploy-windows.flow.md "Environment Variables").
DbDefaults = {
    "MEDIAVORTEX_DB_HOST": "10.0.0.15",
    "MEDIAVORTEX_DB_PORT": "5432",
    "MEDIAVORTEX_DB_NAME": "mediavortex",
    "MEDIAVORTEX_DB_USER": "mediavortex",
    "MEDIAVORTEX_DB_PASSWORD": "mediavortex",
}

SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]

VerificationTimeoutSec = 90
VerificationPollSec = 5
HeartbeatStaleThresholdSec = 60


# ---------------------------------------------------------------------------
# Local + remote command helpers
# ---------------------------------------------------------------------------

def _SshTarget(User: str, Ip: str) -> str:
    return f"{User}@{Ip}"


def _RunSshPlain(Target: str, RemoteCmd: str, *, Timeout: int = 30,
                 Input: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a plain SSH command. Use for things that survive bash/ssh quoting."""
    return subprocess.run(
        ["ssh", *SshOpts, Target, RemoteCmd],
        capture_output=True, text=True, timeout=Timeout, input=Input,
    )


def _PsScriptToEncodedCommand(Script: str) -> str:
    """Encode a PowerShell script as -EncodedCommand-compatible base64.

    PS expects UTF-16-LE-encoded bytes, base64-encoded, passed to
    -EncodedCommand. This is the only reliable way to ship multi-line or
    quote-heavy PS through SSH/Bash without quote eating.
    """
    return base64.b64encode(Script.encode("utf-16-le")).decode("ascii")


def _RunRemotePowerShell(Target: str, Script: str, *, Timeout: int = 60,
                         Input: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a PowerShell script block on the remote host via -EncodedCommand."""
    Encoded = _PsScriptToEncodedCommand(Script)
    Cmd = f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {Encoded}"
    return _RunSshPlain(Target, Cmd, Timeout=Timeout, Input=Input)


def _Status(Step: int, Total: int, Title: str, Result: str = "...",
            Detail: str = "") -> None:
    """Print a step status line. Result: OK / SKIPPED / FAILED / ..."""
    Tag = {
        "OK":      "[OK]   ",
        "SKIPPED": "[SKIP] ",
        "FAILED":  "[FAIL] ",
        "...":     "[..]   ",
    }.get(Result, f"[{Result}] ")
    Suffix = f" -- {Detail}" if Detail else ""
    print(f"  {Tag}({Step}/{Total}) {Title}{Suffix}", flush=True)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def StepPreflight(Target: str) -> tuple[bool, dict]:
    """Probe the worker host for required prereqs. Non-destructive."""
    Script = (
        '$out = @{};\n'
        '$out["py"] = (Get-Command py -EA 0) -ne $null;\n'
        '$out["sshd"] = (Get-Service sshd -EA 0).Status -eq "Running";\n'
        '$prof = Get-NetConnectionProfile -EA 0 | Where-Object { $_.IPv4Connectivity -eq "Internet" } | Select-Object -First 1;\n'
        '$out["network_private"] = ($prof -ne $null) -and ($prof.NetworkCategory -eq "Private");\n'
        '$out["db_reachable"] = (Test-NetConnection 10.0.0.15 -Port 5432 -InformationLevel Quiet -WarningAction SilentlyContinue);\n'
        '$out["porky_reachable"] = (Test-NetConnection 10.0.0.43 -Port 2049 -InformationLevel Quiet -WarningAction SilentlyContinue);\n'
        '$out["synology_reachable"] = (Test-NetConnection 10.0.0.61 -Port 2049 -InformationLevel Quiet -WarningAction SilentlyContinue);\n'
        '$out["nfs_client_installed"] = (Get-WindowsOptionalFeature -Online -FeatureName ClientForNFS-Infrastructure -EA 0).State -eq "Enabled";\n'
        '$out["computer_name"] = $env:COMPUTERNAME;\n'
        '$out["mv_dir_exists"] = Test-Path "C:\\Code\\MediaVortex";\n'
        '$out["venv_exists"] = Test-Path "C:\\Code\\MediaVortex\\venv\\Scripts\\python.exe";\n'
        '$out["task_registered"] = (Get-ScheduledTask -TaskName "MediaVortex Worker" -EA 0) -ne $null;\n'
        '$out | ConvertTo-Json -Compress\n'
    )
    R = _RunRemotePowerShell(Target, Script, Timeout=20)
    if R.returncode != 0:
        return False, {"_error": (R.stderr or R.stdout).strip()[:400]}

    # Strip the CLIXML progress junk that PowerShell sometimes emits to stderr
    # but JSON ends up cleanly on stdout.
    Stdout = R.stdout.strip().splitlines()
    JsonLine = next((line for line in Stdout if line.startswith("{")), None)
    if not JsonLine:
        return False, {"_error": f"no JSON on stdout: {R.stdout[:300]}"}

    try:
        Data = json.loads(JsonLine)
    except json.JSONDecodeError as Exc:
        return False, {"_error": f"bad JSON: {Exc}: {JsonLine[:200]}"}

    Required = ["py", "sshd", "network_private", "db_reachable",
                "porky_reachable", "synology_reachable", "nfs_client_installed"]
    Missing = [k for k in Required if not Data.get(k)]
    return (len(Missing) == 0), Data


def _LoadDeployIgnorePatterns() -> list:
    """Load exclusion patterns from .deployignore."""
    IgnoreFile = MediaVortexRoot / ".deployignore"
    if not IgnoreFile.exists():
        return []
    Patterns = []
    for Line in IgnoreFile.read_text(encoding="utf-8").splitlines():
        Stripped = Line.strip()
        if Stripped and not Stripped.startswith("#"):
            Patterns.append(Stripped)
    return Patterns


def _CopytreeIgnoreFactory(Patterns: list):
    """Return a callable for shutil.copytree(ignore=...) that applies .deployignore."""
    def _Ignore(Directory, Contents):
        return {
            C for C in Contents
            if any(fnmatch.fnmatch(C, P) for P in Patterns)
        }
    return _Ignore


def StepScpRepo(Target: str, RootDir: Path) -> bool:
    """Filtered scp of the MediaVortex repo to the remote host.

    Creates a temp directory with only the files allowed by .deployignore,
    then scp's that filtered tree. Pre-creates C:\\Code on the target.
    """
    Mkdir = (
        'if (-not (Test-Path "C:\\Code")) { '
        'New-Item -ItemType Directory -Path "C:\\Code" -Force | Out-Null }'
    )
    R = _RunRemotePowerShell(Target, Mkdir, Timeout=10)
    if R.returncode != 0:
        print(f"    mkdir C:\\Code failed: {R.stderr.strip()[:200]}")
        return False

    Patterns = _LoadDeployIgnorePatterns()
    if Patterns:
        print(f"    filtering with {len(Patterns)} .deployignore patterns")

    with tempfile.TemporaryDirectory() as TmpDir:
        FilteredDir = os.path.join(TmpDir, "MediaVortex")
        shutil.copytree(
            str(RootDir), FilteredDir,
            ignore=_CopytreeIgnoreFactory(Patterns) if Patterns else None,
        )

        R = subprocess.run(
            ["scp", "-r", "-o", "ConnectTimeout=5",
             FilteredDir, f"{Target}:C:/Code/"],
            capture_output=True, text=True, timeout=900,
        )
        if R.returncode != 0:
            print(f"    scp failed: {(R.stderr or R.stdout).strip()[:300]}")
            return False
    return True


def StepRecreateVenv(Target: str) -> bool:
    """Drop any pre-existing venvs and rebuild the canonical one at root."""
    Script = (
        'cd C:\\Code\\MediaVortex\n'
        'Remove-Item -Recurse -Force venv -EA SilentlyContinue\n'
        'Remove-Item -Recurse -Force WebService\\venv -EA SilentlyContinue\n'
        'Remove-Item -Recurse -Force WorkerService\\venv -EA SilentlyContinue\n'
        'py -m venv venv\n'
        'venv\\Scripts\\python.exe -m pip install --upgrade pip --quiet\n'
        'venv\\Scripts\\python.exe -m pip install -r requirements.txt --quiet\n'
        'if (-not (Test-Path "venv\\Scripts\\python.exe")) { exit 1 }\n'
    )
    R = _RunRemotePowerShell(Target, Script, Timeout=600)
    if R.returncode != 0:
        print(f"    venv build failed: {(R.stderr or R.stdout).strip()[:300]}")
        return False
    return True


def _ResolveLocalHeadSha() -> str:
    """Return the dev workstation's git HEAD, or empty string on any failure."""
    try:
        R = subprocess.run(
            ["git", "-C", str(MediaVortexRoot), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if R.returncode == 0:
            return (R.stdout or "").strip()
    except Exception:
        pass
    return ""


def StepStampVersion(Target: str, Sha: str) -> bool:
    """Write VERSION + BUILD_INFO into C:\\Code\\MediaVortex on the target.

    Uses the same artifact shape as Scripts/StampVersion.py and the Linux
    Dockerfile, so WorkerService.Main._ResolveWorkerVersion has one reader.
    Idempotent: re-running with the same Sha produces identical files.
    """
    if not Sha:
        print("    refusing to stamp: dev-workstation HEAD did not resolve")
        return False

    BuiltAt = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    BuiltBy = socket.gethostname()

    Payload = {"sha": Sha, "built_at": BuiltAt, "built_by": BuiltBy}
    Script = (
        '$j = [Console]::In.ReadToEnd() | ConvertFrom-Json\n'
        '$root = "C:\\Code\\MediaVortex"\n'
        'if (-not (Test-Path $root)) {\n'
        '  Write-Error "MediaVortex root not present at $root"; exit 1\n'
        '}\n'
        '$verPath = Join-Path $root "VERSION"\n'
        '$biPath = Join-Path $root "BUILD_INFO"\n'
        '[IO.File]::WriteAllText($verPath, $j.sha + "`n", [Text.UTF8Encoding]::new($false))\n'
        '$bi = "commit=" + $j.sha + "`n" + "built_at=" + $j.built_at + "`n" + "built_by=" + $j.built_by + "`n"\n'
        '[IO.File]::WriteAllText($biPath, $bi, [Text.UTF8Encoding]::new($false))\n'
        'Write-Host ("stamped " + $verPath + " (" + $j.sha.Substring(0,7) + ")")\n'
    )
    R = _RunRemotePowerShell(Target, Script, Timeout=20, Input=json.dumps(Payload))
    if R.returncode != 0:
        print(f"    stamp failed: {(R.stderr or R.stdout).strip()[:300]}")
        return False
    return True


def StepPushEnvVars(Target: str, EnvVars: dict[str, str]) -> bool:
    """Set User-scope env vars on the remote host via SSH stdin."""
    Script = (
        '$j = [Console]::In.ReadToEnd() | ConvertFrom-Json\n'
        'foreach ($p in $j.PSObject.Properties) {\n'
        '  [Environment]::SetEnvironmentVariable($p.Name, $p.Value, "User")\n'
        '  Write-Host ("  set " + $p.Name + " (length " + $p.Value.Length + ")")\n'
        '}\n'
    )
    R = _RunRemotePowerShell(Target, Script, Timeout=20,
                             Input=json.dumps(EnvVars))
    if R.returncode != 0:
        print(f"    env-var set failed: {(R.stderr or R.stdout).strip()[:300]}")
        return False
    return True


def StepRegisterTask(Target: str) -> bool:
    """Run the in-tree Register-WorkerTask.ps1 on the remote host."""
    Cmd = (
        'powershell -NoProfile -ExecutionPolicy Bypass '
        '-File C:\\Code\\MediaVortex\\deploy\\Register-WorkerTask.ps1'
    )
    R = _RunSshPlain(Target, Cmd, Timeout=30)
    if R.returncode != 0:
        print(f"    Register-WorkerTask.ps1 failed: "
              f"{(R.stderr or R.stdout).strip()[:300]}")
        return False
    return True


def StepTriggerTask(Target: str) -> bool:
    Script = "Start-ScheduledTask -TaskName 'MediaVortex Worker'"
    R = _RunRemotePowerShell(Target, Script, Timeout=15)
    if R.returncode != 0:
        print(f"    trigger failed: {(R.stderr or R.stdout).strip()[:300]}")
        return False
    return True


def StepGetRemoteHostname(Target: str) -> Optional[str]:
    """Get the worker's `socket.gethostname()` so we know the WorkerName."""
    R = _RunSshPlain(Target,
                     'py -c "import socket; print(socket.gethostname())"',
                     Timeout=10)
    if R.returncode != 0:
        return None
    Name = R.stdout.strip()
    return Name or None


def StepVerifyWorkerOnline(WorkerName: str, ExpectedSha: str) -> bool:
    """Poll the Workers row from the dev workstation; verdict within 90 s.

    Asserts Status IN ('Online','Paused'), FFmpegPath non-NULL, heartbeat fresh,
    and Workers.Version equals ExpectedSha (the SHA just stamped on the target).
    """
    PythonExe = MediaVortexRoot / "venv" / "Scripts" / "python.exe"
    QueryScript = MediaVortexRoot / "Scripts" / "SQLScripts" / "QueryDatabase.py"
    if not PythonExe.exists() or not QueryScript.exists():
        print("    cannot verify: dev-workstation venv or QueryDatabase.py missing")
        return False

    Sql = (
        f"SELECT WorkerName, Status, FFmpegPath, Version, "
        f"EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS hb_age "
        f"FROM Workers WHERE LOWER(WorkerName) = LOWER('{WorkerName}')"
    )
    Deadline = time.time() + VerificationTimeoutSec
    LastReason = "no row found"
    while time.time() < Deadline:
        try:
            R = subprocess.run(
                [str(PythonExe), str(QueryScript), "sql", Sql],
                capture_output=True, text=True, timeout=15,
                cwd=str(MediaVortexRoot),
            )
        except subprocess.TimeoutExpired:
            LastReason = "QueryDatabase.py timed out"
            time.sleep(VerificationPollSec); continue
        Out = R.stdout
        if "0 rows returned" in Out or "1 rows returned" not in Out:
            LastReason = "Workers row not present yet"
            time.sleep(VerificationPollSec); continue

        DataLines = [
            ln for ln in Out.splitlines()
            if "|" in ln and "---" not in ln and "workername" not in ln.lower()
        ]
        if not DataLines:
            LastReason = "could not parse row from QueryDatabase output"
            time.sleep(VerificationPollSec); continue

        Cols = [c.strip() for c in DataLines[-1].split("|")]
        if len(Cols) < 5:
            LastReason = f"unexpected col count: {Cols}"
            time.sleep(VerificationPollSec); continue

        Name, Status, FfmpegPath, Version, HbAge = Cols[0], Cols[1], Cols[2], Cols[3], Cols[4]
        try:
            HbAgeInt = int(HbAge)
        except ValueError:
            LastReason = f"could not parse heartbeat age: {HbAge!r}"
            time.sleep(VerificationPollSec); continue

        if Status not in ("Online", "Paused"):
            LastReason = f"Status={Status!r} (want Online or Paused)"
        elif not FfmpegPath or FfmpegPath.lower() == "none":
            LastReason = "FFmpegPath is NULL"
        elif HbAgeInt > HeartbeatStaleThresholdSec:
            LastReason = f"heartbeat stale: {HbAgeInt}s old"
        elif Version != ExpectedSha:
            LastReason = (
                f"version mismatch: Workers.Version={Version!r} but stamped "
                f"{ExpectedSha!r} (worker likely did not restart after stamp)"
            )
        else:
            print(f"    Workers.{Name}: Status={Status}, FFmpegPath set, "
                  f"heartbeat {HbAgeInt}s, version={Version[:7]}")
            return True

        time.sleep(VerificationPollSec)

    print(f"    verification timed out after {VerificationTimeoutSec}s: {LastReason}")
    return False


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def BuildEnvVarPayload() -> dict[str, str]:
    """Compose the env-var bundle pushed to the worker host."""
    Payload = dict(DbDefaults)
    LocalPwd = os.environ.get("MEDIAVORTEX_DB_PASSWORD")
    if LocalPwd:
        Payload["MEDIAVORTEX_DB_PASSWORD"] = LocalPwd
    Payload["MEDIAVORTEX_MAX_CPU_THREADS"] = os.environ.get(
        "MEDIAVORTEX_MAX_CPU_THREADS", "12"
    )
    return Payload


def main() -> int:
    Parser = argparse.ArgumentParser(
        description="Deploy a MediaVortex worker to a Windows host end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    Parser.add_argument("target_ip", help="IP of the Windows worker host.")
    Parser.add_argument("--user", default="owner",
                        help="SSH user (default: owner).")
    Parser.add_argument("--check", action="store_true",
                        help="Run pre-flight only; do not change remote state.")
    Parser.add_argument("--skip-scp", action="store_true",
                        help="Skip repo scp (assumes repo already on host).")
    Parser.add_argument("--skip-venv", action="store_true",
                        help="Skip venv recreate (assumes venv already built).")
    Parser.add_argument("--skip-creds", action="store_true",
                        help="Skip env-var push (assumes already set).")
    Parser.add_argument("--skip-task", action="store_true",
                        help="Skip Task Scheduler registration.")
    Parser.add_argument("--no-trigger", action="store_true",
                        help="Register task but don't trigger it now (next logon will).")
    Parser.add_argument("--skip-verify", action="store_true",
                        help="Don't poll the DB to confirm worker is Online.")
    Args = Parser.parse_args()

    Target = _SshTarget(Args.user, Args.target_ip)
    print(f"Deploying MediaVortex worker to {Target}")
    print("=" * 60)

    Total = 8

    # Step 1: pre-flight.
    _Status(1, Total, "Pre-flight checks", "...")
    Ok, PreflightData = StepPreflight(Target)
    if not Ok:
        Issues = [k for k, v in PreflightData.items()
                  if not v and not k.startswith("_") and k not in ("mv_dir_exists",
                                                                    "venv_exists",
                                                                    "task_registered",
                                                                    "computer_name")]
        if "_error" in PreflightData:
            Issues.append(f"error={PreflightData['_error']}")
        _Status(1, Total, "Pre-flight checks", "FAILED",
                Detail=", ".join(Issues) or "see error above")
        return 1
    _Status(1, Total, "Pre-flight checks", "OK",
            Detail=f"host={PreflightData.get('computer_name', '?')}")

    if Args.check:
        print("\n[--check] pre-flight passed; no further actions taken.")
        return 0

    # Step 2: scp.
    if Args.skip_scp:
        _Status(2, Total, "scp repo", "SKIPPED", Detail="--skip-scp")
    else:
        _Status(2, Total, "scp repo", "...")
        if not StepScpRepo(Target, MediaVortexRoot):
            _Status(2, Total, "scp repo", "FAILED")
            return 2
        _Status(2, Total, "scp repo", "OK")

    # Step 3: venv. Skip if already built unless explicitly forced.
    if Args.skip_venv or PreflightData.get("venv_exists"):
        Reason = "--skip-venv" if Args.skip_venv else "already built"
        _Status(3, Total, "Recreate venv", "SKIPPED", Detail=Reason)
    else:
        _Status(3, Total, "Recreate venv", "...")
        if not StepRecreateVenv(Target):
            _Status(3, Total, "Recreate venv", "FAILED")
            return 2
        _Status(3, Total, "Recreate venv", "OK")

    # Step 4: push env vars (DB).
    if Args.skip_creds:
        _Status(4, Total, "Push env vars (DB)", "SKIPPED",
                Detail="--skip-creds")
    else:
        _Status(4, Total, "Push env vars (DB)", "...")
        Payload = BuildEnvVarPayload()
        if not StepPushEnvVars(Target, Payload):
            _Status(4, Total, "Push env vars (DB)", "FAILED")
            return 2
        _Status(4, Total, "Push env vars (DB)", "OK",
                Detail=f"{len(Payload)} vars set at User scope")

    # Step 5: stamp VERSION + BUILD_INFO on the target with dev workstation HEAD.
    Sha = _ResolveLocalHeadSha()
    if not Sha:
        _Status(5, Total, "Stamp VERSION on target", "FAILED",
                Detail="dev-workstation git rev-parse HEAD failed")
        return 2
    _Status(5, Total, "Stamp VERSION on target", "...")
    if not StepStampVersion(Target, Sha):
        _Status(5, Total, "Stamp VERSION on target", "FAILED")
        return 2
    _Status(5, Total, "Stamp VERSION on target", "OK",
            Detail=f"sha={Sha[:7]}")

    # Step 6: register task.
    if Args.skip_task:
        _Status(6, Total, "Register Task Scheduler entry", "SKIPPED",
                Detail="--skip-task")
    else:
        _Status(6, Total, "Register Task Scheduler entry", "...")
        if not StepRegisterTask(Target):
            _Status(6, Total, "Register Task Scheduler entry", "FAILED")
            return 2
        _Status(6, Total, "Register Task Scheduler entry", "OK")

    # Step 7: trigger.
    if Args.no_trigger:
        _Status(7, Total, "Trigger task", "SKIPPED",
                Detail="--no-trigger; next user logon will fire it")
    else:
        _Status(7, Total, "Trigger task", "...")
        if not StepTriggerTask(Target):
            _Status(7, Total, "Trigger task", "FAILED")
            return 2
        _Status(7, Total, "Trigger task", "OK")

    # Step 8: verify.
    if Args.skip_verify or Args.no_trigger:
        _Status(8, Total, "Verify worker Online", "SKIPPED",
                Detail="--skip-verify or --no-trigger")
        print("\nDone (unverified). Check Workers row manually.")
        return 0

    _Status(8, Total, "Verify worker Online", "...")
    Hostname = StepGetRemoteHostname(Target)
    if not Hostname:
        _Status(8, Total, "Verify worker Online", "FAILED",
                Detail="could not get remote socket.gethostname()")
        return 3
    if StepVerifyWorkerOnline(Hostname, Sha):
        _Status(8, Total, "Verify worker Online", "OK",
                Detail=f"WorkerName={Hostname}, version={Sha[:7]}")
        print("\nDeploy complete. Worker is Online, heartbeating, and on the stamped version.")
        return 0
    _Status(8, Total, "Verify worker Online", "FAILED",
            Detail=f"WorkerName={Hostname} did not reach a healthy state on version {Sha[:7]}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
