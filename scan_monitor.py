import sys
from pathlib import Path as PyPath
sys.path.insert(0, str(PyPath(__file__).resolve().parent))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern


def Snapshot(Db):
    LikePattern = EscapeLikePattern("_Testing/") + "%"
    Mf = Db.ExecuteQuery(
        "SELECT COUNT(*) AS C FROM MediaFiles WHERE StorageRootId=1 AND RelativePath LIKE %s ESCAPE %s",
        (LikePattern, "!"),
    )
    Tq = Db.ExecuteQuery("SELECT COUNT(*) AS C FROM TranscodeQueue WHERE Status=%s", ("Pending",))
    Sj = Db.ExecuteQuery(
        "SELECT Id, RootFolderPath, Status, ProcessedFiles, TotalFiles, NewFiles, UpdatedFiles, EncodingErrors, "
        "EXTRACT(EPOCH FROM (NOW() - LastUpdated))::int AS UpdateAgeSec, "
        "EXTRACT(EPOCH FROM (NOW() - StartTime))::int AS RunSec, "
        "WorkerName "
        "FROM ScanJobs WHERE Status IN ('Pending','Running') ORDER BY StartTime DESC"
    )
    def Val(R, K): return R[K] if K in R else R.get(K.upper(), R.get(K.lower(), 0))
    MfCount = Val(Mf[0], "C")
    TqCount = Val(Tq[0], "C")
    return {
        "mediafiles_testing": MfCount,
        "queue_pending": TqCount,
        "active_scans": [{k.lower(): Val(R, k) for k in (
            "Id","RootFolderPath","Status","ProcessedFiles","TotalFiles","NewFiles","UpdatedFiles","EncodingErrors","UpdateAgeSec","RunSec","WorkerName"
        )} for R in Sj],
    }


if __name__ == "__main__":
    Db = DatabaseService()
    S = Snapshot(Db)
    print(f"  MediaFiles under T:/_Testing/: {S['mediafiles_testing']}")
    print(f"  TranscodeQueue Pending:        {S['queue_pending']}")
    print(f"  Active scan jobs:              {len(S['active_scans'])}")
    for J in S['active_scans']:
        print(f"    id={J['id']} status={J['status']} processed={J['processedfiles']}/{J['totalfiles']} "
              f"new={J['newfiles']} updated={J['updatedfiles']} errors={J['encodingerrors']} "
              f"updateAge={J['updateagesec']}s runSec={J['runsec']}s worker={J['workername']}")
