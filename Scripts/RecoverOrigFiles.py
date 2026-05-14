"""Recover from the remux re-queue loop bug.

Root cause: RecomputeForFiles was never called after successful file replacement,
so RecommendedMode stayed 'Remux' on already-remuxed MP4 files. They got re-queued
indefinitely, leaving stale .orig backups on disk.

Phases:
  1. .orig disk cleanup -- restore or delete based on whether a successful remux exists
  2. Bulk RecomputeForFiles on all stale MP4 files (RecommendedMode='Remux' but already MP4)
  3. Queue cleanup -- remove bogus remux queue items for now-compliant files
  4. Clean up wasted TranscodeAttempts with .orig collision errors

Usage:
  py Scripts/RecoverOrigFiles.py --dry-run      # Preview all actions
  py Scripts/RecoverOrigFiles.py --execute       # Apply changes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Logging.LoggingService import LoggingService


def Phase1_OrigDiskCleanup(DB, DryRun):
    """Handle .orig files left on disk by the re-queue loop."""
    print("\n=== PHASE 1: .orig disk cleanup ===\n")

    Rows = DB.ExecuteQuery(
        """SELECT DISTINCT ON (ta.mediafileid) ta.mediafileid, mf.filepath
           FROM transcodeattempts ta
           JOIN mediafiles mf ON ta.mediafileid = mf.id
           WHERE ta.success = false AND ta.errormessage LIKE %s
           ORDER BY ta.mediafileid, ta.id DESC""",
        ('%Pre-existing .orig%',)
    )
    print("Affected MediaFiles: %d" % len(Rows))

    SafeDeleted = 0
    CorruptDeleted = []
    NeitherExists = []
    AlreadyClean = 0

    for R in Rows:
        FP = R['filepath']
        OrigPath = FP + '.orig'
        FPExists = os.path.exists(FP)
        OrigExists = os.path.exists(OrigPath)

        if FPExists and OrigExists:
            # Both exist -- check if file ever had a successful remux
            SuccRows = DB.ExecuteQuery(
                """SELECT COUNT(*) as cnt FROM transcodeattempts
                   WHERE mediafileid = %s AND success = true AND profilename = 'Remux'""",
                (R['mediafileid'],)
            )
            HadSuccess = SuccRows[0]['cnt'] > 0

            if HadSuccess:
                # Category A: .mp4 is valid, .orig is safe to delete
                OrigSize = os.path.getsize(OrigPath)
                if DryRun:
                    print("  [DRY-RUN] DELETE .orig: %s (%s bytes)" % (OrigPath, "{:,}".format(OrigSize)))
                else:
                    os.remove(OrigPath)
                    print("  DELETED .orig: %s (%s bytes)" % (OrigPath, "{:,}".format(OrigSize)))
                SafeDeleted += 1
            else:
                # Category B: .mp4 is corrupt (partial FFmpeg write), .orig is pre-remux source
                # User wants both deleted -- report for visibility
                Mp4Size = os.path.getsize(FP)
                OrigSize = os.path.getsize(OrigPath)
                CorruptDeleted.append({
                    'MediaFileId': R['mediafileid'],
                    'FilePath': FP,
                    'Mp4Size': Mp4Size,
                    'OrigSize': OrigSize,
                })
                if DryRun:
                    print("  [DRY-RUN] DELETE BOTH (corrupt): %s (mp4=%s, orig=%s)" % (
                        FP, "{:,}".format(Mp4Size), "{:,}".format(OrigSize)))
                else:
                    os.remove(FP)
                    os.remove(OrigPath)
                    print("  DELETED BOTH (corrupt): %s (mp4=%s, orig=%s)" % (
                        FP, "{:,}".format(Mp4Size), "{:,}".format(OrigSize)))

        elif FPExists and not OrigExists:
            # Category C: .orig already gone, .mp4 exists -- nothing to do on disk
            AlreadyClean += 1

        elif not FPExists and OrigExists:
            # .orig exists but DB path missing -- restore .orig to DB path
            OrigSize = os.path.getsize(OrigPath)
            if DryRun:
                print("  [DRY-RUN] RESTORE .orig -> %s (%s bytes)" % (FP, "{:,}".format(OrigSize)))
            else:
                os.rename(OrigPath, FP)
                print("  RESTORED .orig -> %s (%s bytes)" % (FP, "{:,}".format(OrigSize)))

        else:
            # Category D: neither exists
            NeitherExists.append({'MediaFileId': R['mediafileid'], 'FilePath': FP})

    print("\nPhase 1 summary:")
    print("  Safe .orig deleted:          %d" % SafeDeleted)
    print("  Corrupt pairs deleted:       %d" % len(CorruptDeleted))
    print("  Already clean (mp4 only):    %d" % AlreadyClean)
    print("  Neither exists (orphan DB):  %d" % len(NeitherExists))

    if CorruptDeleted:
        print("\n--- FILES DELETED (both corrupt .mp4 and .orig) ---")
        print("These files had no successful remux. The .mp4 was a partial FFmpeg write.")
        print("Re-scan or re-acquire these files to restore them.\n")
        for E in CorruptDeleted:
            print("  MF %d: %s" % (E['MediaFileId'], E['FilePath']))
            print("         mp4 was %s bytes, orig was %s bytes" % (
                "{:,}".format(E['Mp4Size']), "{:,}".format(E['OrigSize'])))

    if NeitherExists:
        print("\n--- ORPHAN DB ROWS (neither file exists on disk) ---")
        for E in NeitherExists:
            print("  MF %d: %s" % (E['MediaFileId'], E['FilePath']))

    return CorruptDeleted, NeitherExists


def Phase2_BulkRecompute(DB, DryRun):
    """Recompute cached columns on all MP4 files with stale RecommendedMode='Remux'."""
    print("\n=== PHASE 2: Bulk RecomputeForFiles ===\n")

    Rows = DB.ExecuteQuery(
        """SELECT Id FROM MediaFiles
           WHERE ContainerFormat LIKE %s AND RecommendedMode = 'Remux'
           ORDER BY Id""",
        ('%mp4%',)
    )
    AllIds = [R['id'] for R in Rows]
    print("Stale MP4 files with RecommendedMode='Remux': %d" % len(AllIds))

    if not AllIds:
        print("Nothing to recompute.")
        return

    if DryRun:
        print("[DRY-RUN] Would recompute %d files in batches of 500" % len(AllIds))
        return

    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    Service = QueueManagementBusinessService()

    BatchSize = 500
    TotalUpdated = 0
    for i in range(0, len(AllIds), BatchSize):
        Batch = AllIds[i:i + BatchSize]
        Updated = Service.RecomputeForFiles(Batch)
        TotalUpdated += Updated
        print("  Batch %d-%d: recomputed %d rows" % (i + 1, min(i + BatchSize, len(AllIds)), Updated))

    print("\nPhase 2 summary: recomputed %d / %d files" % (TotalUpdated, len(AllIds)))


def Phase3_QueueCleanup(DB, DryRun, CorruptDeleted, NeitherExists):
    """Remove bogus remux queue items for files that are now compliant or deleted."""
    print("\n=== PHASE 3: Queue cleanup ===\n")

    # Find remux queue items where the MediaFile is now compliant (IsCompliant=True)
    CompliantRows = DB.ExecuteQuery(
        """SELECT tq.Id, tq.MediaFileId, tq.Status
           FROM TranscodeQueue tq
           JOIN MediaFiles mf ON tq.MediaFileId = mf.Id
           WHERE tq.ProcessingMode = 'Remux'
           AND tq.Status IN ('Pending', 'Running')
           AND mf.IsCompliant = true"""
    )

    # Also find queue items for files we just deleted
    DeletedIds = [E['MediaFileId'] for E in CorruptDeleted] + [E['MediaFileId'] for E in NeitherExists]
    OrphanQueueRows = []
    if DeletedIds:
        Placeholders = ','.join(['%s'] * len(DeletedIds))
        OrphanQueueRows = DB.ExecuteQuery(
            f"""SELECT Id, MediaFileId, Status FROM TranscodeQueue
                WHERE MediaFileId IN ({Placeholders})
                AND Status IN ('Pending', 'Running')""",
            tuple(DeletedIds)
        )

    AllQueueIds = [R['id'] for R in CompliantRows] + [R['id'] for R in OrphanQueueRows]
    # Deduplicate
    AllQueueIds = list(set(AllQueueIds))

    print("Compliant-file queue items to remove: %d" % len(CompliantRows))
    print("Deleted-file queue items to remove:   %d" % len(OrphanQueueRows))
    print("Total queue items to delete:          %d" % len(AllQueueIds))

    if not AllQueueIds:
        print("No queue items to clean up.")
        return

    if DryRun:
        print("[DRY-RUN] Would delete %d queue items" % len(AllQueueIds))
        for R in CompliantRows[:10]:
            print("  Queue %d (MF %d, %s) -- now compliant" % (R['id'], R['mediafileid'], R['status']))
        for R in OrphanQueueRows[:10]:
            print("  Queue %d (MF %d, %s) -- file deleted" % (R['id'], R['mediafileid'], R['status']))
        return

    Placeholders = ','.join(['%s'] * len(AllQueueIds))
    DB.ExecuteNonQuery(
        f"DELETE FROM TranscodeQueue WHERE Id IN ({Placeholders})",
        tuple(AllQueueIds)
    )
    print("Deleted %d queue items." % len(AllQueueIds))


def Phase4_CleanWastedAttempts(DB, DryRun):
    """Delete the wasted TranscodeAttempt rows with .orig collision errors."""
    print("\n=== PHASE 4: Clean wasted TranscodeAttempts ===\n")

    CountRows = DB.ExecuteQuery(
        "SELECT COUNT(*) as cnt FROM TranscodeAttempts WHERE success = false AND errormessage LIKE %s",
        ('%Pre-existing .orig%',)
    )
    Count = CountRows[0]['cnt']
    print("Wasted .orig collision attempts: %d" % Count)

    if Count == 0:
        print("Nothing to clean.")
        return

    if DryRun:
        print("[DRY-RUN] Would delete %d TranscodeAttempts rows" % Count)
        return

    DB.ExecuteNonQuery(
        "DELETE FROM TranscodeAttempts WHERE success = false AND errormessage LIKE %s",
        ('%Pre-existing .orig%',)
    )
    print("Deleted %d wasted TranscodeAttempts rows." % Count)


def Main():
    Parser = argparse.ArgumentParser(description="Recover from remux re-queue loop bug")
    Group = Parser.add_mutually_exclusive_group(required=True)
    Group.add_argument('--dry-run', action='store_true', help='Preview all actions without making changes')
    Group.add_argument('--execute', action='store_true', help='Apply all changes')
    Args = Parser.parse_args()

    DryRun = Args.dry_run
    if DryRun:
        print("*** DRY-RUN MODE -- no changes will be made ***\n")
    else:
        print("*** EXECUTE MODE -- changes will be applied ***\n")
        Confirm = input("Type YES to confirm: ")
        if Confirm != 'YES':
            print("Aborted.")
            return

    DB = DatabaseService()

    CorruptDeleted, NeitherExists = Phase1_OrigDiskCleanup(DB, DryRun)
    Phase2_BulkRecompute(DB, DryRun)
    Phase3_QueueCleanup(DB, DryRun, CorruptDeleted, NeitherExists)
    Phase4_CleanWastedAttempts(DB, DryRun)

    print("\n=== DONE ===")
    if DryRun:
        print("Run with --execute to apply these changes.")


if __name__ == '__main__':
    Main()
