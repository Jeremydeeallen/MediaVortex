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
    {"Letter": "T", "UncPath": r"\\10.0.0.43\srv\nfs-media-_tv", "Required": True},
    {"Letter": "M", "UncPath": r"\\10.0.0.61\volume1\_video\Adults\Movies", "Required": True},
    {"Letter": "Z", "UncPath": r"\\10.0.0.61\volume2\XXX", "Required": True},
]


def _MountDrive(Drive):
    """Mount one NFS drive via net use /persistent:yes. NFS uses AUTH_SYS -- no credentials."""
    Letter = Drive["Letter"]
    UncPath = Drive["UncPath"]

    if os.path.exists(f"{Letter}:\\"):
        print(f"  [OK]   {Letter}:\\ already mounted")
        return True

    Cmd = ["net", "use", f"{Letter}:", UncPath, "/persistent:yes"]
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
