"""Clean up stale .orig backups left by the NoSavings disposition bug,
then retry ProcessFileReplacement for each affected TranscodeAttempt.

Context: The remux pipeline renamed the original to .orig before FFmpeg,
then FFmpeg wrote the remuxed output to the freed source path. But the
NoSavings disposition bug prevented FileReplacement from running, so
the .orig was never settled. When remediation retried ProcessFileReplacement,
it hit the "Pre-existing .orig backup AND original is still at source path"
safety guard and refused to proceed.

In this case:
  - source_path     = the REMUXED output (good file, written by FFmpeg)
  - source_path.orig = the PRE-REMUX original (backup, safe to delete)

This script deletes the .orig and retries ProcessFileReplacement. The
replacement function will then see the source file (which is actually
the remuxed output) and proceed normally.

Usage:
  py Scripts/SQLScripts/CleanupOrigAndRetryReplacement.py --dry-run
  py Scripts/SQLScripts/CleanupOrigAndRetryReplacement.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


def GetBlockedAttempts():
    """Return attempts that have BypassReplace but FileReplaced=false."""
    DB = DatabaseService()
    Rows = DB.ExecuteQuery(
        """
        SELECT ta.id, ta.mediafileid, m.filepath AS media_filepath,
               tf.originalpath, tf.localoutputpath
        FROM TranscodeAttempts ta
        JOIN MediaFiles m ON m.id = ta.mediafileid
        JOIN TemporaryFilePaths tf ON tf.transcodeattemptid = ta.id
        WHERE ta.success = true
          AND ta.ffpmpegcommand ILIKE '%%copy%%loudnorm%%'
          AND ta.filereplaced = false
          AND ta.disposition = 'BypassReplace'
        ORDER BY ta.id
        """
    )
    return Rows


def GetPathTranslation(WorkerName=None):
    """Get FFprobePath for the given worker (or current hostname)."""
    FFprobePath = None
    try:
        if not WorkerName:
            import socket
            WorkerName = socket.gethostname().lower()
        DB = DatabaseService()
        WorkerRows = DB.ExecuteQuery(
            "SELECT FFprobePath FROM Workers WHERE LOWER(WorkerName) = %s LIMIT 1",
            (WorkerName.lower(),),
        )
        if WorkerRows:
            FFprobePath = WorkerRows[0].get('FFprobePath')
    except Exception:
        pass
    return WorkerName, FFprobePath


def RunCleanup(DryRun=False, WorkerNameArg=None):
    Rows = GetBlockedAttempts()
    Total = len(Rows)
    print(f"Found {Total} blocked TranscodeAttempts (BypassReplace, not replaced)")

    if Total == 0:
        print("Nothing to clean up.")
        return

    WorkerName, FFprobePath = GetPathTranslation(WorkerNameArg)
    print(f"WorkerName: {WorkerName}")
    print(f"FFprobePath: {FFprobePath}")

    from Repositories.DatabaseManager import DatabaseManager
    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService

    DBManager = DatabaseManager()
    ReplacementService = FileReplacementBusinessService(
        DBManager,
        FFprobePath=FFprobePath,
        WorkerName=WorkerName,
    )

    if DryRun:
        print("\n--- DRY RUN ---")
        Reachable = 0
        HasOrig = 0
        for R in Rows:
            LocalOriginal = ReplacementService._ToLocalPath(R['originalpath'])
            OrigBackup = LocalOriginal + ".orig" if LocalOriginal else None
            if OrigBackup and os.path.exists(OrigBackup):
                HasOrig += 1
            if LocalOriginal and (os.path.exists(LocalOriginal) or os.path.exists(OrigBackup or '')):
                Reachable += 1
        print(f"  Reachable from this host: {Reachable}/{Total}")
        print(f"  With .orig backup to delete: {HasOrig}")
        print(f"\nWould delete .orig files and retry ProcessFileReplacement.")
        return

    from Repositories.DatabaseManager import DatabaseManager
    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService

    DBManager = DatabaseManager()
    ReplacementService = FileReplacementBusinessService(
        DBManager,
        FFprobePath=FFprobePath,
        WorkerName=WorkerName,
    )

    Succeeded = 0
    Failed = 0
    Skipped = 0
    Errors = []

    for I, R in enumerate(Rows, 1):
        AttemptId = R['id']
        LocalOriginal = ReplacementService._ToLocalPath(R['originalpath'])
        OrigBackup = LocalOriginal + ".orig" if LocalOriginal else None

        # Delete stale .orig if it exists
        if OrigBackup and os.path.exists(OrigBackup):
            try:
                os.remove(OrigBackup)
                print(f"  [{I}/{Total}] Deleted .orig: {OrigBackup}")
            except Exception as Ex:
                Failed += 1
                Errors.append((AttemptId, f"Failed to delete .orig: {Ex}"))
                print(f"  [{I}/{Total}] AttemptId={AttemptId} -- FAILED to delete .orig: {Ex}")
                continue
        elif LocalOriginal and not os.path.exists(LocalOriginal):
            # Neither original nor .orig exists -- file is unreachable from this host
            Skipped += 1
            continue

        # Retry ProcessFileReplacement
        try:
            Result = ReplacementService.ProcessFileReplacement(AttemptId)
            if Result.get('Success'):
                Succeeded += 1
                print(f"  [{I}/{Total}] AttemptId={AttemptId} -- OK")
            else:
                Failed += 1
                ErrMsg = Result.get('ErrorMessage', 'Unknown')
                Errors.append((AttemptId, ErrMsg))
                print(f"  [{I}/{Total}] AttemptId={AttemptId} -- FAILED: {ErrMsg}")
        except Exception as Ex:
            Failed += 1
            Errors.append((AttemptId, str(Ex)))
            print(f"  [{I}/{Total}] AttemptId={AttemptId} -- EXCEPTION: {Ex}")

    print(f"\nCleanup complete: {Succeeded} succeeded, {Failed} failed, {Skipped} skipped (unreachable) out of {Total}")
    if Errors:
        print("\nFailed attempts:")
        for AttemptId, ErrMsg in Errors:
            print(f"  AttemptId={AttemptId}: {ErrMsg}")


if __name__ == '__main__':
    DryRun = '--dry-run' in sys.argv
    WorkerNameArg = None
    for Arg in sys.argv:
        if Arg.startswith('--worker='):
            WorkerNameArg = Arg.split('=', 1)[1]
    RunCleanup(DryRun=DryRun, WorkerNameArg=WorkerNameArg)
