"""StartWorker - Launch MediaVortex WorkerService natively on Windows.

Worker-only analog of StartMediaVortex.py for hosts that run only the
transcode worker (no WebService) -- e.g. REMINGTON, I9-2024, future bare-metal
workers.

What this does on every run:
  1. Mount required NFS drives (T:, M:, Z:) in *this* process's session.
  2. Verify each drive is accessible.
  3. Launch WorkerService\\Main.py inline (this script blocks until it exits).

Why re-mount every run: persistent mappings do NOT reconnect for non-
interactive sessions (Task Scheduler, NSSM, SSH). See worker-deploy-windows.flow.md.

The mounts are NFS via the Windows NFS client (AUTH_SYS, no credentials).
Porky exports the TV share; Synology exports Movies + XXX.

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

NetworkDrives = [
    {"Letter": "T", "UncPath": r"\\10.0.0.43\TV", "Required": True},
    {"Letter": "M", "UncPath": r"\\10.0.0.43\Movies", "Required": True},
    {"Letter": "Z", "UncPath": r"\\10.0.0.43\XXX", "Required": True},
]


def _MountDrive(Drive):
    """Mount one NFS drive via mount.exe with mtype=hard. NFS uses AUTH_SYS -- no credentials.

    Hard mounts retry RPCs forever instead of returning EINVAL when the server is briefly
    slow. net use without explicit options defaults to mtype=soft + timeout=0.8s + retry=1,
    which caused intermittent FFmpeg 'Error opening output file: Invalid argument' failures
    on output writes against a brief-stall NFS server.
    """
    Letter = Drive["Letter"]
    UncPath = Drive["UncPath"]

    if os.path.exists(f"{Letter}:\\"):
        print(f"  [OK]   {Letter}:\\ already mounted")
        return True

    Cmd = ["mount.exe",
           "-o", "mtype=hard",
           "-o", "timeout=30",
           "-o", "rsize=1024",
           "-o", "wsize=1024",
           "-o", "anon",
           UncPath, f"{Letter}:"]
    try:
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] {Letter}:\\ mount timed out")
        return False

    if Result.returncode == 0 and os.path.exists(f"{Letter}:\\"):
        print(f"  [OK]   {Letter}:\\ mounted ({UncPath})")
        return True

    Combined = (Result.stdout + Result.stderr).strip()
    FirstLine = Combined.splitlines()[0] if Combined else f"exit {Result.returncode}"
    Tag = "[FAIL]" if Drive.get("Required") else "[WARN]"
    print(f"  {Tag} {Letter}:\\: {FirstLine}")
    return False


def _MountAllDrives():
    print("Mounting NFS drives...")
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


def _SetUncResolutions():
    """Run SetWindowsWorkerUncPaths.py to ensure StorageRootResolutions + WorkerShareMappings
    for this host store UNC strings, not drive letters. Idempotent; safe to run every boot.
    Fix for BUG-0008: drive-letter session unbinding on the Microsoft NFS client surfaced
    EINVAL on ffmpeg output-open. UNC paths route through MUP + NFS redirector and survive
    drive-letter flapping. See WorkerService/windows-unc-path-translation.feature.md."""
    Script = RootDirectory / "Scripts" / "SQLScripts" / "SetWindowsWorkerUncPaths.py"
    if not Script.exists():
        print(f"  [WARN] UNC-path script not found at {Script}; skipping (legacy drive-letter mode)")
        return True
    PythonExe = _ResolveWorkerPython()
    print("Applying UNC path resolutions for this worker...")
    try:
        Result = subprocess.run([PythonExe, str(Script)], cwd=str(RootDirectory), timeout=30)
    except subprocess.TimeoutExpired:
        print("  [FAIL] UNC-path script timed out")
        return False
    if Result.returncode != 0:
        print(f"  [FAIL] UNC-path script exited {Result.returncode}")
        return False
    return True


def _StampVersion():
    """Run Scripts/StampVersion.py to refresh VERSION + BUILD_INFO from local git HEAD.

    Non-fatal: if git is missing or the checkout isn't a repo, the stamper exits
    non-zero and we leave any existing VERSION file alone. The worker process
    will then read whatever VERSION says, or "unknown" if nothing was ever
    stamped. The directive (criterion 2) demands we never fall through to a
    live git resolution INSIDE the worker -- stamping here is fine because
    it writes a file the worker reads at startup; the worker never sees git."""
    Script = RootDirectory / "Scripts" / "StampVersion.py"
    if not Script.exists():
        print(f"  [WARN] StampVersion.py not found at {Script}; skipping (VERSION not refreshed)")
        return
    PythonExe = _ResolveWorkerPython()
    try:
        subprocess.run([PythonExe, str(Script), "--quiet"], cwd=str(RootDirectory), timeout=30)
    except subprocess.TimeoutExpired:
        print("  [WARN] StampVersion.py timed out; leaving existing VERSION as-is")


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
        help="Skip NFS mount step (drives already mounted).",
    )
    Parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mount + verify but do not launch WorkerService.",
    )
    Args = Parser.parse_args()

    print("=" * 50)
    print("MediaVortex Worker Launcher")
    # allow: StartWorker.py is a worker bootstrap script (Windows analog of StartMediaVortex.py); COMPUTERNAME is a display-only Windows-provided value
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

    if not _SetUncResolutions():
        print("\n[FAIL] could not apply UNC path resolutions")
        return 2

    _StampVersion()

    if Args.dry_run:
        print("\n[DRY-RUN] all checks passed; not launching worker.")
        return 0

    return _LaunchWorker()


if __name__ == "__main__":
    sys.exit(main())
