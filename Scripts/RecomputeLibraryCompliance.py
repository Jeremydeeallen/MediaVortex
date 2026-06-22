import argparse
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: compliance-recompute-tools
BATCH_SIZE = 500


# directive: compliance-recompute-tools
def _FetchIds(DB, ProfileName, StorageRootId, Limit):
    Wheres = []
    Args = []
    if ProfileName:
        Wheres.append("AssignedProfile = %s")
        Args.append(ProfileName)
    if StorageRootId is not None:
        Wheres.append("StorageRootId = %s")
        Args.append(StorageRootId)
    WhereClause = ("WHERE " + " AND ".join(Wheres)) if Wheres else ""
    LimitClause = f"LIMIT {int(Limit)}" if Limit else ""
    Sql = f"SELECT Id FROM MediaFiles {WhereClause} ORDER BY Id ASC {LimitClause}"
    Rows = DB.ExecuteQuery(Sql, tuple(Args))
    return [int(R['id']) for R in Rows]


# directive: compliance-recompute-tools
def _SnapshotBuckets(DB, Ids):
    if not Ids:
        return {}
    Placeholders = ",".join(["%s"] * len(Ids))
    Rows = DB.ExecuteQuery(
        f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({Placeholders})",
        tuple(Ids),
    )
    return {int(R['id']): R['workbucket'] for R in Rows}


# directive: compliance-recompute-tools
def Run(ProfileName=None, StorageRootId=None, Limit=None, DryRun=False):
    DB = DatabaseService()
    Qmbs = QueueManagementBusinessService()
    Ids = _FetchIds(DB, ProfileName, StorageRootId, Limit)
    Total = len(Ids)
    print(f"Targets: {Total} MediaFile rows", end='')
    if ProfileName:
        print(f" (profile={ProfileName!r})", end='')
    if StorageRootId is not None:
        print(f" (storage_root={StorageRootId})", end='')
    print()
    if DryRun:
        print("DRY-RUN -- no writes will occur. Listing first 10 ids:")
        for I in Ids[:10]:
            print(f"  {I}")
        return

    BucketChanges = {}
    Started = time.time()
    Processed = 0
    for Start in range(0, Total, BATCH_SIZE):
        Batch = Ids[Start:Start + BATCH_SIZE]
        PreBuckets = _SnapshotBuckets(DB, Batch)
        Qmbs.RecomputeForFiles(Batch)
        PostBuckets = _SnapshotBuckets(DB, Batch)
        for Mid in Batch:
            Pre = PreBuckets.get(Mid)
            Post = PostBuckets.get(Mid)
            if Pre != Post:
                Key = f"{Pre} -> {Post}"
                BucketChanges[Key] = BucketChanges.get(Key, 0) + 1
        Processed += len(Batch)
        Elapsed = time.time() - Started
        Rate = Processed / Elapsed if Elapsed > 0 else 0
        Remaining = (Total - Processed) / Rate if Rate > 0 else 0
        print(f"  Batch {Start // BATCH_SIZE + 1}: processed {Processed}/{Total} "
              f"({Processed * 100.0 / max(1, Total):.1f}%) | rate {Rate:.0f} rows/s | "
              f"~{Remaining:.0f}s remaining")

    print(f"\nDone. Processed {Processed} rows in {time.time() - Started:.1f}s.")
    if BucketChanges:
        print("Bucket transitions:")
        for K in sorted(BucketChanges, key=lambda K: -BucketChanges[K]):
            print(f"  {K:<32} {BucketChanges[K]:>6}")
    else:
        print("No bucket changes (every file's verdict was unchanged).")


# directive: compliance-recompute-tools
def Main():
    Ap = argparse.ArgumentParser(description="Library-wide compliance recompute. Refreshes the three vertical booleans + AssignedProfile + PriorityScore against the current bar.")
    Ap.add_argument('--profile', help='Restrict to MediaFiles whose AssignedProfile matches this name')
    Ap.add_argument('--storage-root', type=int, help='Restrict to MediaFiles under this StorageRootId')
    Ap.add_argument('--limit', type=int, help='Cap target count (for testing)')
    Ap.add_argument('--dry-run', action='store_true', help='List first 10 targets without writing')
    Args = Ap.parse_args()
    Run(ProfileName=Args.profile, StorageRootId=Args.storage_root, Limit=Args.limit, DryRun=Args.dry_run)


if __name__ == '__main__':
    Main()
