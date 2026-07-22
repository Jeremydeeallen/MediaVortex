import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: transcode-flow-canonical -- C33 backfill after profile-independent verticals ship
def Run():
    DB = DatabaseService()

    Stuck = DB.ExecuteQuery(
        "SELECT Id FROM MediaFiles "
        "WHERE VideoCompliantReason = 'no_effective_profile' "
        "   OR ContainerCompliantReason = 'no_effective_profile' "
        "   OR ContainerCompliantReason = 'no_profile_container' "
        "ORDER BY Id"
    )
    Ids = [R['id'] for R in Stuck]
    print(f"Stuck rows to backfill: {len(Ids)}")

    if not Ids:
        print("Nothing to do.")
        return

    Svc = QueueManagementBusinessService()
    Batch = 500
    for I in range(0, len(Ids), Batch):
        Chunk = Ids[I:I + Batch]
        Svc.RecomputeForFiles(Chunk)
        print(f"  Recomputed {min(I + Batch, len(Ids))}/{len(Ids)}")

    Remaining = DB.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM MediaFiles "
        "WHERE VideoCompliantReason = 'no_effective_profile' "
        "   OR ContainerCompliantReason = 'no_effective_profile' "
        "   OR ContainerCompliantReason = 'no_profile_container'"
    )
    print(f"Remaining 'no_effective_profile' rows post-backfill: {Remaining[0]['n']}")

    Distribution = DB.ExecuteQuery(
        "SELECT WorkBucket, COUNT(*) AS n FROM MediaFiles GROUP BY WorkBucket ORDER BY n DESC"
    )
    print("\nPost-backfill bucket distribution:")
    for R in Distribution:
        print(f"  {R.get('workbucket') or '<null>'}: {R['n']}")


if __name__ == '__main__':
    Run()
