"""StartWorker - Launch MediaVortex WorkerService natively on Windows.

Worker-only analog of StartMediaVortex.py for hosts that run only the
transcode worker (no WebService) -- e.g. REMINGTON, I9-2024, future bare-metal
workers.

What this does on every run:
  1. Mount required SMB drives (T:, M:, Z:) in *this* process's session.
  2. Verify each drive is accessible.
  3. Launch WorkerService\\Main.py inline (this script blocks until it exits).

Why re-mount every run: persistent SMB mappings do NOT reconnect for non-
interactive sessions (Task Scheduler, NSSM, SSH). See windows-worker.flow.md.

Credential resolution (priority order):
  1. Cached SMB cred in Windows Credential Manager. The launcher first tries
     `New-SmbMapping` with NO `-UserName`/`-Password`; Windows resolves the
     credential from the per-user store keyed by the SMB server. Stash via
     `deploy\\Bootstrap-WorkerCreds.ps1` from an interactive session (RDP or
     physical -- cmdkey refuses from Network-logon sessions like SSH).
  2. Env vars MEDIAVORTEX_BRAIN_PASSWORD / MEDIAVORTEX_SYNOLOGY_PASSWORD.
     Set at User scope so they survive logoff.
  3. Vault helper at MEDIAVORTEX_VAULT_HELPER (default
     C:\\Code\\infrastructure\\terraform\\secrets.py). Calls
     `<python> <helper> get <key>` and uses stdout. Requires the worker
     host to have the infrastructure repo, the bw CLI, and a DPAPI session
     cache stashed via tools\\bw-cache-session.ps1.
  4. If a required drive cannot be mounted by any of the above, exit 2.

Designed for unattended use:
  - No Windows Terminal tabs (wt.exe is unavailable in service contexts).
  - Inline subprocess launch so the parent's exit code reflects the worker's.
  - Exits 2 on infrastructure problems and propagates worker exit codes.

Usage:
  py StartWorker.py
  py StartWorker.py --no-mount    # drives already mounted
  py StartWorker.py --dry-run     # mount + verify but don't launch worker
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

RootDirectory = Path(__file__).resolve().parent

WorkerEntry = RootDirectory / "WorkerService" / "Main.py"
DefaultVenvPython = RootDirectory / "venv" / "Scripts" / "python.exe"
DefaultVaultHelper = Path(r"C:\Code\infrastructure\terraform\secrets.py")

NetworkDrives = [
    {
        "Letter": "T",
        "UncPath": r"\\10.0.0.40\Media_tv",
        "User": "media",
        "VaultKey": "homelab/brain/cifs-media",
        "EnvVar": "MEDIAVORTEX_BRAIN_PASSWORD",
        "Required": True,
    },
    {
        "Letter": "M",
        "UncPath": r"\\10.0.0.61\_video\Adults\Movies",
        "User": "jallen11",
        "VaultKey": "homelab/synology/jallen11",
        "EnvVar": "MEDIAVORTEX_SYNOLOGY_PASSWORD",
        "Required": True,
    },
    {
        "Letter": "Z",
        "UncPath": r"\\10.0.0.61\xxx",
        "User": "jallen11",
        "VaultKey": "homelab/synology/jallen11",
        "EnvVar": "MEDIAVORTEX_SYNOLOGY_PASSWORD",
        "Required": True,
    },
]


def _ResolveVaultHelper():
    HelperPath = os.environ.get("MEDIAVORTEX_VAULT_HELPER", str(DefaultVaultHelper))
    return HelperPath if os.path.exists(HelperPath) else None


def _ResolvePassword(Drive):
    EnvValue = os.environ.get(Drive["EnvVar"])
    if EnvValue:
        return EnvValue

    Helper = _ResolveVaultHelper()
    if not Helper:
        return None

    PythonExe = sys.executable or "py"
    try:
        Result = subprocess.run(
            [PythonExe, Helper, "get", Drive["VaultKey"]],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as Exc:
        print(f"  [WARN] vault helper failed for {Drive['VaultKey']}: {Exc}")
        return None

    if Result.returncode != 0:
        print(
            f"  [WARN] vault helper exit {Result.returncode} for "
            f"{Drive['VaultKey']}: {Result.stderr.strip()[:200]}"
        )
        return None
    return Result.stdout.strip()


def _RunPowerShell(Script, Env=None):
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", Script],
        capture_output=True,
        text=True,
        timeout=30,
        env=Env,
    )


def _MountDrive(Drive):
    """Mount one SMB drive. Try cached creds first, then explicit creds."""
    Letter = Drive["Letter"]
    UncPath = Drive["UncPath"]

    if os.path.exists(f"{Letter}:\\"):
        print(f"  [OK]   {Letter}:\\ already mounted")
        return True

    # 1. Cached-credential path: New-SmbMapping with no user/pass uses the
    #    per-user Credential Manager entry keyed by the SMB server.
    CachedScript = (
        f"$ErrorActionPreference='Stop'; "
        f"New-SmbMapping -LocalPath {Letter}: -RemotePath '{UncPath}' | Out-Null"
    )
    try:
        Result = _RunPowerShell(CachedScript)
        if Result.returncode == 0 and os.path.exists(f"{Letter}:\\"):
            print(f"  [OK]   {Letter}:\\ mounted via cached creds ({UncPath})")
            return True
    except subprocess.TimeoutExpired:
        print(f"  [WARN] {Letter}:\\ cached-cred mount timed out; trying explicit")

    # 2. Explicit-credential path: pull password from env var or vault helper,
    #    pass via env var to avoid PowerShell argument-quoting hazards.
    Password = _ResolvePassword(Drive)
    if not Password:
        Tag = "[FAIL]" if Drive.get("Required") else "[WARN]"
        print(
            f"  {Tag} {Letter}:\\ -- cached cred missing AND no password "
            f"source available (set ${Drive['EnvVar']} or stash "
            f"{Drive['VaultKey']} in vault, or run "
            f"deploy\\Bootstrap-WorkerCreds.ps1 from an interactive session)"
        )
        return False

    ExplicitScript = (
        f"$ErrorActionPreference='Stop'; "
        f"New-SmbMapping -LocalPath {Letter}: -RemotePath '{UncPath}' "
        f"-UserName '{Drive['User']}' -Password $env:_MV_PWD | Out-Null"
    )
    Env = os.environ.copy()
    Env["_MV_PWD"] = Password

    try:
        Result = _RunPowerShell(ExplicitScript, Env=Env)
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] {Letter}:\\ explicit-cred mount timed out")
        return False

    if Result.returncode == 0 and os.path.exists(f"{Letter}:\\"):
        print(f"  [OK]   {Letter}:\\ mounted ({UncPath})")
        return True

    Combined = (Result.stdout + Result.stderr).strip()
    FirstLine = Combined.splitlines()[0] if Combined else f"exit {Result.returncode}"
    print(f"  [FAIL] {Letter}:\\: {FirstLine}")
    return False


def _MountAllDrives():
    print("Mounting SMB drives...")
    Failed = []
    for Drive in NetworkDrives:
        if not _MountDrive(Drive) and Drive.get("Required"):
            Failed.append(Drive["Letter"])
    return Failed


def _VerifyDrives():
    print("Verifying drive accessibility...")
    Missing = []
    for Drive in NetworkDrives:
        DrivePath = f"{Drive['Letter']}:\\"
        if os.path.exists(DrivePath):
            print(f"  [OK]   {DrivePath} accessible")
            continue
        Tag = "[FAIL]" if Drive.get("Required") else "[WARN]"
        print(f"  {Tag} {DrivePath} not accessible")
        if Drive.get("Required"):
            Missing.append(Drive["Letter"])
    return Missing


def _ResolveWorkerPython():
    if DefaultVenvPython.exists():
        return str(DefaultVenvPython)
    print(
        f"  [WARN] venv not found at {DefaultVenvPython}; "
        f"falling back to {sys.executable}"
    )
    return sys.executable


def _LaunchWorker():
    if not WorkerEntry.exists():
        print(f"[FAIL] WorkerService entry not found at {WorkerEntry}")
        return 2

    PythonExe = _ResolveWorkerPython()
    print(f"Launching WorkerService: {PythonExe} {WorkerEntry}")
    print("=" * 50)
    try:
        Result = subprocess.run([PythonExe, str(WorkerEntry)], cwd=str(RootDirectory))
    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt; worker shutting down.")
        return 130
    return Result.returncode


def main():
    Parser = argparse.ArgumentParser(description="MediaVortex worker launcher.")
    Parser.add_argument(
        "--no-mount",
        action="store_true",
        help="Skip SMB mount step (drives already mounted).",
    )
    Parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mount + verify but do not launch WorkerService.",
    )
    Args = Parser.parse_args()

    print("=" * 50)
    print("MediaVortex Worker Launcher")
    print(f"Host: {os.environ.get('COMPUTERNAME', '<unknown>')}")
    print("=" * 50)

    if not Args.no_mount:
        Failed = _MountAllDrives()
        if Failed:
            print(f"\n[FAIL] could not mount required drives: {', '.join(Failed)}")
            return 2

    Missing = _VerifyDrives()
    if Missing:
        print(f"\n[FAIL] required drives missing: {', '.join(Missing)}")
        return 2

    if Args.dry_run:
        print("\n[DRY-RUN] all checks passed; not launching worker.")
        return 0

    return _LaunchWorker()


if __name__ == "__main__":
    sys.exit(main())
