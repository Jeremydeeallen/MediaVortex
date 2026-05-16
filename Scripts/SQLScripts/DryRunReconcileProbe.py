"""Dry-run probe for ReconcileWithDisk's set-membership logic.

Walks the disk for one RootFolder, computes (StorageRootId, RelativePath)
for every disk path via Core.PathStorage, then reports how many DB rows
would be classified as KEEP / MISSING / PRESERVE_NULL_STORAGE_ROOT
WITHOUT touching the DB. Run this BEFORE flipping ScanEnabled on a
worker the first time on a new platform.

Usage (inside a worker container or any host with the repo + DB access):
    py Scripts/SQLScripts/DryRunReconcileProbe.py <RootFolderCanonical>

Example:
    py Scripts/SQLScripts/DryRunReconcileProbe.py 'T:\\'
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.PathStorage import LoadStorageRoots, Parse as PathParse
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Services.FileManagerService import FileManagerService


def Run(RootFolderCanonical: str):
    print(f"=== Dry-run reconcile probe for {RootFolderCanonical!r} ===")

    Repo = FileScanningRepository()
    FileMgr = FileManagerService()

    # Translate canonical -> local for the disk walk.
    StorageRoots = LoadStorageRoots()
    RootSid, RootRel = PathParse(RootFolderCanonical, StorageRoots)
    if RootSid is None:
        print(f"FAIL: '{RootFolderCanonical}' does not match any registered StorageRoot prefix.")
        sys.exit(2)

    # Find the local AbsolutePath for this StorageRoot on this worker.
    import socket
    WorkerName = socket.gethostname()
    Resolutions = Repo.DatabaseService.ExecuteQuery(
        "SELECT AbsolutePath FROM StorageRootResolutions "
        "WHERE StorageRootId = %s AND WorkerName = %s AND IsActive = TRUE LIMIT 1",
        (RootSid, WorkerName),
    )
    if not Resolutions:
        print(f"FAIL: no active StorageRootResolutions row for (StorageRootId={RootSid}, WorkerName={WorkerName!r}).")
        sys.exit(3)
    LocalRoot = Resolutions[0]['AbsolutePath']
    print(f"WorkerName: {WorkerName}")
    print(f"StorageRootId: {RootSid}")
    print(f"LocalRoot: {LocalRoot}")

    # Walk disk
    Start = time.time()
    LocalMediaFiles = FileMgr.ScanDirectory(LocalRoot, recursive=True)
    WalkSec = time.time() - Start
    print(f"\nWalked {len(LocalMediaFiles)} media files in {WalkSec:.1f}s")

    # Build disk set on (StorageRootId, RelativePath.lower())
    DiskSet = set()
    Unparseable = 0
    for LocalPath in LocalMediaFiles:
        # Convert local -> canonical (strip the LocalRoot prefix)
        if LocalPath.lower().startswith(LocalRoot.lower()):
            Rel = LocalPath[len(LocalRoot):].replace('\\', '/').lstrip('/')
            DiskSet.add((RootSid, Rel.lower()))
        else:
            Unparseable += 1
    print(f"Disk set built: {len(DiskSet)} entries; {Unparseable} unparseable")

    # Load DB rows for this RootFolder
    DatabaseFiles = Repo.GetMediaFilesByRootFolder(RootFolderCanonical)
    print(f"\nDatabase rows for {RootFolderCanonical}: {len(DatabaseFiles)}")

    # Classify
    Keep = 0
    Missing = 0
    PreserveNull = 0
    for DbFile in DatabaseFiles:
        DbSid = getattr(DbFile, 'StorageRootId', None)
        DbRel = getattr(DbFile, 'RelativePath', None) or ''
        if DbSid is None:
            PreserveNull += 1
            continue
        if (DbSid, DbRel.lower()) in DiskSet:
            Keep += 1
        else:
            Missing += 1

    print(f"\n=== CLASSIFICATION (no DB writes) ===")
    print(f"  KEEP                  {Keep:>7}")
    print(f"  MISSING (would delete or reassign) {Missing:>7}")
    print(f"  PRESERVE_NULL_STORAGE_ROOT {PreserveNull:>7}")

    if DatabaseFiles:
        Pct = 100.0 * Missing / len(DatabaseFiles)
        Verdict = "SAFETY GUARD WOULD TRIP" if Pct > 90.0 else "OK to proceed"
        print(f"\nMissing %: {Pct:.1f}%  ({Verdict})")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    Run(sys.argv[1])
