# directive: tv-tier1-classifier-pin
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.MediaFiles.ProfileAssignmentService import ProfileAssignmentService


TV_STORAGE_ROOT_ID = 1
TARGET_PROFILE = 'AV1 Tier 1 Efficient'
BATCH_SIZE = 500


# directive: tv-tier1-classifier-pin
def _RetierTvToTier1(Db, Writer):
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND (AssignedProfile IS NULL OR AssignedProfile <> %s)",
        (TV_STORAGE_ROOT_ID, TARGET_PROFILE),
    )
    Ids = [int(R['Id']) for R in (Rows or [])]
    if not Ids:
        print(f"[TV retier] No TV rows needed retiering.")
        return 0
    print(f"[TV retier] {len(Ids)} TV rows -> {TARGET_PROFILE!r} (batches of {BATCH_SIZE}).")
    Written = 0
    for I in range(0, len(Ids), BATCH_SIZE):
        Batch = Ids[I:I + BATCH_SIZE]
        WrittenIds = Writer.Assign(Batch, TARGET_PROFILE, 'backfill_tv_tier1_2026_08_25', IfUnsetOnly=False)
        Written += len(WrittenIds)
        print(f"  batch {I // BATCH_SIZE + 1}: wrote {len(WrittenIds)}/{len(Batch)}")
    print(f"[TV retier] Wrote {Written}/{len(Ids)} total.")
    return Written


# directive: tv-tier1-classifier-pin
def _ReconcileStaleReasons(Db, Writer):
    Rows = Db.ExecuteQuery(
        "SELECT Id, AssignedProfile FROM MediaFiles "
        "WHERE VideoCompliantReason LIKE 'source_%%_ceiling%%' "
        "  AND SUBSTRING(VideoCompliantReason FROM 'profile=([^:]+):') IS DISTINCT FROM AssignedProfile"
    )
    Ids = [int(R['Id']) for R in (Rows or [])]
    if not Ids:
        print(f"[stale-reason reconcile] No rows with profile drift.")
        return 0
    print(f"[stale-reason reconcile] {len(Ids)} rows need recompute (batches of {BATCH_SIZE}).")
    # Direct RecomputeForFiles avoids rewriting AssignedProfile; verticals re-evaluate + rewrite reason.
    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    Qmbs = QueueManagementBusinessService()
    Total = 0
    for I in range(0, len(Ids), BATCH_SIZE):
        Batch = Ids[I:I + BATCH_SIZE]
        Qmbs.RecomputeForFiles(Batch)
        Total += len(Batch)
        print(f"  batch {I // BATCH_SIZE + 1}: recomputed {len(Batch)}")
    print(f"[stale-reason reconcile] Recomputed {Total} rows total.")
    return Total


# directive: tv-tier1-classifier-pin
def Run():
    Db = DatabaseService()
    Writer = ProfileAssignmentService(Db=Db)
    _RetierTvToTier1(Db, Writer)
    _ReconcileStaleReasons(Db, Writer)

    Residual = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Cnt FROM MediaFiles WHERE StorageRootId = %s AND AssignedProfile <> %s",
        (TV_STORAGE_ROOT_ID, TARGET_PROFILE),
    )
    ResidualStale = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Cnt FROM MediaFiles "
        "WHERE VideoCompliantReason LIKE 'source_%%_ceiling%%' "
        "  AND SUBSTRING(VideoCompliantReason FROM 'profile=([^:]+):') IS DISTINCT FROM AssignedProfile"
    )
    print(f"[post-run] TV non-Tier1 residual: {int(Residual[0]['Cnt'])}")
    print(f"[post-run] Stale-reason residual: {int(ResidualStale[0]['Cnt'])}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
