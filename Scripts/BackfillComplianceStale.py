# see probe-worker-decoupled -- backfill stale silent-True Compliant rows. Only targets suspects (WorkBucket='Compliant' AND VideoBitrateKbps > 1500) since silent-True false-positives can only land in Compliant, and files with bitrate <= 1500 kbps are genuinely under every tier target so cannot be false positives.
import sys, os, time
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

import platform
from Core.WorkerContext import WorkerContext
from Core.Database.DatabaseService import DatabaseService


BATCH_SIZE = 200


def Run(MinBitrateKbps=1500):
    if not WorkerContext.TryCurrent():
        try:
            WorkerContext.Initialize(WorkerName='I9-2024', Platform=platform.system())
        except RuntimeError:
            pass
        WorkerContext.Bind()

    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

    Db = DatabaseService()
    Q = QueueManagementBusinessService()

    Ids = [int(R['id']) for R in Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles WHERE WorkBucket='Compliant' AND VideoBitrateKbps > %s ORDER BY Id ASC",
        (MinBitrateKbps,),
    )]
    Total = len(Ids)
    print(f"Suspect Compliant rows with VideoBitrateKbps > {MinBitrateKbps}: {Total}")

    if not Total:
        return

    Changes = {}
    T0 = time.time()
    for Start in range(0, Total, BATCH_SIZE):
        Batch = Ids[Start:Start + BATCH_SIZE]
        Placeholders = ','.join(['%s'] * len(Batch))
        Pre = {int(R['id']): R['workbucket'] for R in Db.ExecuteQuery(
            f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({Placeholders})", tuple(Batch)
        )}
        Q.RecomputeForFiles(Batch)
        Post = {int(R['id']): R['workbucket'] for R in Db.ExecuteQuery(
            f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({Placeholders})", tuple(Batch)
        )}
        for Mid in Batch:
            P0, P1 = Pre.get(Mid), Post.get(Mid)
            if P0 != P1:
                K = f"{P0} -> {P1}"
                Changes[K] = Changes.get(K, 0) + 1
        Done = Start + len(Batch)
        Elapsed = time.time() - T0
        Rate = Done / Elapsed if Elapsed > 0 else 0
        Eta = (Total - Done) / Rate if Rate > 0 else 0
        print(f"  {Done}/{Total} ({100*Done//Total}%) rate={Rate:.1f} files/s eta={Eta:.0f}s changes={Changes}")

    print("\n=== FINAL ===")
    for K, V in sorted(Changes.items(), key=lambda X: -X[1]):
        print(f"  {V:6d}  {K}")


if __name__ == '__main__':
    import argparse
    Ap = argparse.ArgumentParser()
    Ap.add_argument('--min-kbps', type=int, default=1500)
    A = Ap.parse_args()
    Run(A.min_kbps)
