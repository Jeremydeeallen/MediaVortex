"""Remediate remux files that were incorrectly Disposition='Discard' due to
the NoSavings gate firing before the QualityTestNotRequired bypass.

What happened:
- Remux jobs completed successfully (Success=true, QualityTestRequired=false)
- The disposition table checked NoSavings (Row 2) before QualityTestNotRequired (Row 3)
- Audio re-encode produced slightly larger files -> Disposition='Discard'
- FileReplacement never ran -> .orig backup + .mp4 output sitting on disk, DB still points to original

What this script does:
1. Finds all affected TranscodeAttempts (Discard/NoSavings, remux, not yet replaced)
2. Updates their Disposition to 'BypassReplace' so ProcessFileReplacement accepts them
3. Calls ProcessFileReplacement for each, which handles:
   - Archive original metadata to MediaFilesArchive
   - Move/rename output file to final location (with -mv suffix)
   - Re-probe the new file and update all MediaFiles columns
   - Settle the .orig backup (delete or rename based on KeepSource)

Usage:
  py Scripts/SQLScripts/RemediateDiscardedRemuxFiles.py --dry-run    # see what would happen
  py Scripts/SQLScripts/RemediateDiscardedRemuxFiles.py              # execute remediation
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


def GetAffectedAttempts():
    """Return TranscodeAttempt IDs that were incorrectly discarded."""
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
          AND ta.disposition = 'Discard'
          AND ta.dispositionreason = 'NoSavings'
        ORDER BY ta.id
        """
    )
    return Rows


def UpdateDispositions(AttemptIds):
    """Flip Disposition from Discard to BypassReplace for the given attempts."""
    DB = DatabaseService()
    DB.ExecuteNonQuery(
        """
        UPDATE TranscodeAttempts
        SET Disposition = 'BypassReplace',
            DispositionReason = 'QualityTestNotRequired'
        WHERE Id = ANY(%s)
          AND Disposition = 'Discard'
          AND DispositionReason = 'NoSavings'
        """,
        (AttemptIds,),
    )


def RunRemediation(DryRun=False):
    Rows = GetAffectedAttempts()
    Total = len(Rows)
    print(f"Found {Total} affected TranscodeAttempts")

    if Total == 0:
        print("Nothing to remediate.")
        return

    if DryRun:
        print("\n--- DRY RUN (no changes) ---")
        for R in Rows[:10]:
            print(f"  AttemptId={R['id']}  MediaFileId={R['mediafileid']}")
            print(f"    Original: {R['originalpath']}")
            print(f"    Output:   {R['localoutputpath']}")
        if Total > 10:
            print(f"  ... and {Total - 10} more")
        print(f"\nWould update {Total} dispositions and run ProcessFileReplacement on each.")
        return

    # Step 1: Flip dispositions in bulk
    AttemptIds = [R['id'] for R in Rows]
    print(f"Updating {Total} dispositions from Discard -> BypassReplace...")
    UpdateDispositions(AttemptIds)
    print("Done.")

    # Step 2: Run ProcessFileReplacement for each
    from Repositories.DatabaseManager import DatabaseManager
    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
    from Core.PathStorage import LoadStorageRoots

    DBManager = DatabaseManager()

    # Determine local PathTranslation (if any) from worker config
    PathTranslation = None
    FFprobePath = None
    try:
        import socket
        Hostname = socket.gethostname().lower()
        DB = DatabaseService()
        WorkerRows = DB.ExecuteQuery(
            "SELECT PathTranslation, FFprobePath FROM Workers WHERE LOWER(WorkerName) = %s LIMIT 1",
            (Hostname,),
        )
        if WorkerRows:
            PathTranslation = WorkerRows[0].get('PathTranslation')
            FFprobePath = WorkerRows[0].get('FFprobePath')
    except Exception:
        pass

    ReplacementService = FileReplacementBusinessService(
        DBManager,
        PathTranslation=PathTranslation,
        FFprobePath=FFprobePath,
    )

    Succeeded = 0
    Failed = 0
    Errors = []

    for I, R in enumerate(Rows, 1):
        AttemptId = R['id']
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

    print(f"\nRemediation complete: {Succeeded} succeeded, {Failed} failed out of {Total}")
    if Errors:
        print("\nFailed attempts:")
        for AttemptId, ErrMsg in Errors:
            print(f"  AttemptId={AttemptId}: {ErrMsg}")


if __name__ == '__main__':
    DryRun = '--dry-run' in sys.argv
    RunRemediation(DryRun=DryRun)
