"""Set a Windows worker's path resolutions to UNC strings (BUG-0008 fix).

Bypasses the per-logon-session drive-letter binding on the Microsoft NFS client
by storing UNC paths in StorageRootResolutions.AbsolutePath. ffmpeg then receives
UNC strings via PathStorage.Resolve and the worker's CreateFile calls go through
MUP -> NFS redirector instead of through a fragile session-bound drive letter.

StorageRootResolutions is authoritative; WorkerShareMappings is derived from the
SAME rows this script just wrote (read-back projection, by construction). See
WorkerService/windows-unc-path-translation.feature.md for context.

Usage:
    py Scripts/SQLScripts/SetWindowsWorkerUncPaths.py
    py Scripts/SQLScripts/SetWindowsWorkerUncPaths.py --worker I9-2024
    py Scripts/SQLScripts/SetWindowsWorkerUncPaths.py --dry-run

Idempotent. Second run prints no diff.
"""

import argparse
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Repositories.DatabaseManager import DatabaseManager


UNC_PREFIXES = {
    'T': '\\\\10.0.0.43\\srv\\nfs-media-_tv\\',
    'M': '\\\\10.0.0.43\\srv\\nfs-media-_movies\\',
    'Z': '\\\\10.0.0.43\\srv\\nfs-media-_xxx\\',
}


def _FetchCurrentResolutions(Db, WorkerName):
    """Return {DriveLetter: AbsolutePath} from current StorageRootResolutions rows."""
    Rows = Db.ExecuteQuery(
        "SELECT s.CanonicalPrefix, r.AbsolutePath FROM StorageRootResolutions r "
        "JOIN StorageRoots s ON r.StorageRootId = s.Id "
        "WHERE r.WorkerName = %s AND r.IsActive = TRUE",
        (WorkerName,)
    )
    Result = {}
    for Row in Rows:
        Prefix = Row.get('CanonicalPrefix') or Row.get('canonicalprefix')
        Path = Row.get('AbsolutePath') or Row.get('absolutepath')
        if Prefix and Path:
            Result[Prefix[0].upper()] = Path
    return Result


def _FetchCurrentShareMappings(Db, WorkerName):
    """Return {DriveLetter: LocalMountPrefix} from current WorkerShareMappings rows."""
    Rows = Db.ExecuteQuery(
        "SELECT DriveLetter, LocalMountPrefix FROM WorkerShareMappings WHERE WorkerName = %s",
        (WorkerName,)
    )
    Result = {}
    for Row in Rows:
        Letter = (Row.get('DriveLetter') or Row.get('driveletter') or '').strip().upper()
        Prefix = Row.get('LocalMountPrefix') or Row.get('localmountprefix')
        if Letter and Prefix:
            Result[Letter] = Prefix
    return Result


def _DiffMap(Label, Before, After):
    """Print a {DriveLetter: path} before/after diff. Returns True if any change."""
    Changed = False
    AllKeys = sorted(set(Before) | set(After))
    print(f"\n[{Label}]")
    if not AllKeys:
        print("  (no rows)")
        return False
    for Key in AllKeys:
        Old = Before.get(Key, '(missing)')
        New = After.get(Key, '(missing)')
        if Old == New:
            print(f"  {Key}: {Old}  (unchanged)")
        else:
            Changed = True
            print(f"  {Key}: {Old}")
            print(f"     -> {New}")
    return Changed


def Run(WorkerName, DryRun=False):
    Db = DatabaseService()
    Manager = DatabaseManager(Db)

    print(f"Worker: {WorkerName}")
    print(f"Mode:   {'DRY RUN' if DryRun else 'APPLY'}")

    BeforeSrr = _FetchCurrentResolutions(Db, WorkerName)
    BeforeWsm = _FetchCurrentShareMappings(Db, WorkerName)

    if DryRun:
        # Synthesize the after-state without writing
        AfterSrr = dict(UNC_PREFIXES)
        AfterWsm = dict(UNC_PREFIXES)
    else:
        # Step 1: write StorageRootResolutions (authoritative).
        Ok = Manager.RegisterStorageRootResolutions(WorkerName, 'windows', UNC_PREFIXES)
        if not Ok:
            print("[FATAL] RegisterStorageRootResolutions failed", file=sys.stderr)
            return 1

        # Step 2: read back the authoritative values, project to WorkerShareMappings.
        # By construction WSM cannot drift from SRR for this worker -- the values
        # come from the rows we just wrote, not from a separate dict.
        AfterSrr = _FetchCurrentResolutions(Db, WorkerName)
        DerivedWsm = {Letter: AfterSrr[Letter] for Letter in AfterSrr if Letter in UNC_PREFIXES}
        Ok = Manager.RegisterWorkerShareMappings(WorkerName, DerivedWsm)
        if not Ok:
            print("[FATAL] RegisterWorkerShareMappings failed", file=sys.stderr)
            return 1

        AfterWsm = _FetchCurrentShareMappings(Db, WorkerName)

    SrrChanged = _DiffMap("StorageRootResolutions (authoritative)", BeforeSrr, AfterSrr)
    WsmChanged = _DiffMap("WorkerShareMappings (derived)", BeforeWsm, AfterWsm)

    if not SrrChanged and not WsmChanged:
        print("\nNo changes. Worker is already on UNC paths.")
    elif DryRun:
        print("\n[DRY RUN] no rows written. Re-run without --dry-run to apply.")
    else:
        print("\nDone. Restart the worker for the new paths to take effect.")
    return 0


def main():
    Parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    Parser.add_argument("--worker", default=None, help="Worker name (default: hostname)")
    Parser.add_argument("--dry-run", action="store_true", help="Show diff without writing")
    Args = Parser.parse_args()

    WorkerName = (Args.worker or os.environ.get('MEDIAVORTEX_WORKER_NAME') or socket.gethostname()).strip()
    return Run(WorkerName, DryRun=Args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
