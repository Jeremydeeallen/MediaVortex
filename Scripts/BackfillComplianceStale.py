# see probe-worker-decoupled -- one-shot backfill for stale WorkBucket rows created before probe-integrated classification landed. Batches through MediaFiles in Id chunks; delta-reports bucket transitions.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

import platform
from Core.WorkerContext import WorkerContext
from Core.Database.DatabaseService import DatabaseService


BATCH_SIZE = 200


def Run(ProfileName=None, StorageRootId=None, Limit=None):
    if not WorkerContext.TryCurrent():
        try:
            WorkerContext.Initialize(WorkerName='I9-2024', Platform=platform.system())
        except RuntimeError:
            pass
        WorkerContext.Bind()

    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

    Db = DatabaseService()
    Q = QueueManagementBusinessService()

    Wheres, Args = [], []
    if ProfileName:
        Wheres.append("AssignedProfile = %s")
        Args.append(ProfileName)
    if StorageRootId is not None:
        Wheres.append("StorageRootId = %s")
        Args.append(int(StorageRootId))
    WhereSql = ("WHERE " + " AND ".join(Wheres)) if Wheres else ""
    LimitSql = f"LIMIT {int(Limit)}" if Limit else ""

    Ids = [int(R['id']) for R in Db.ExecuteQuery(
        f"SELECT Id FROM MediaFiles {WhereSql} ORDER BY Id ASC {LimitSql}", tuple(Args)
    )]
    Total = len(Ids)
    print(f"Recomputing {Total} files (batch={BATCH_SIZE})")

    Changes = {}
    for Start in range(0, Total, BATCH_SIZE):
        Batch = Ids[Start:Start + BATCH_SIZE]
        Pre = {int(R['id']): R['workbucket'] for R in Db.ExecuteQuery(
            f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({','.join(['%s']*len(Batch))})",
            tuple(Batch),
        )}
        Q.RecomputeForFiles(Batch)
        Post = {int(R['id']): R['workbucket'] for R in Db.ExecuteQuery(
            f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({','.join(['%s']*len(Batch))})",
            tuple(Batch),
        )}
        for Mid in Batch:
            P0, P1 = Pre.get(Mid), Post.get(Mid)
            if P0 != P1:
                K = f"{P0} -> {P1}"
                Changes[K] = Changes.get(K, 0) + 1
        Done = Start + len(Batch)
        print(f"  {Done}/{Total} ({100*Done//Total}%) transitions so far: {Changes}")

    print("\n=== FINAL DELTA ===")
    for K, V in sorted(Changes.items(), key=lambda X: -X[1]):
        print(f"  {V:6d}  {K}")


if __name__ == '__main__':
    import argparse
    Ap = argparse.ArgumentParser()
    Ap.add_argument('--profile', default=None)
    Ap.add_argument('--sid', type=int, default=None)
    Ap.add_argument('--limit', type=int, default=None)
    A = Ap.parse_args()
    Run(A.profile, A.sid, A.limit)
