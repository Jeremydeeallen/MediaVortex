# directive: dialog-boost-marker-unify | # see dialog-boost-marker-unify.C8
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: dialog-boost-marker-unify
def Main():
    Db = DatabaseService()
    FlipCount = Db.ExecuteNonQuery(
        "UPDATE MediaFiles mf SET HasDialogBoostTrack = TRUE "
        "WHERE mf.HasDialogBoostTrack = FALSE "
        "  AND EXISTS ("
        "    SELECT 1 FROM TranscodeAttempts ta "
        "    WHERE ta.MediaFileId = mf.Id "
        "      AND ta.Success = TRUE "
        "      AND ta.DialogBoostEmitted = TRUE "
        "  )"
    )
    print(f"Flipped HasDialogBoostTrack=TRUE on {FlipCount} MediaFiles")
    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT ta.MediaFileId "
        "FROM TranscodeAttempts ta "
        "JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
        "WHERE ta.DialogBoostEmitted = TRUE "
        "  AND ta.Success = TRUE "
        "  AND mf.HasDialogBoostTrack = TRUE "
        "  AND mf.WorkBucket <> 'Compliant'"
    )
    Ids = [int(Row.get('mediafileid') if 'mediafileid' in Row else Row.get('MediaFileId'))
           for Row in Rows if (Row.get('mediafileid') or Row.get('MediaFileId')) is not None]
    print(f"Recomputing WorkBucket for {len(Ids)} MediaFiles now flag-true but non-Compliant bucket")
    if not Ids:
        return
    Svc = QueueManagementBusinessService()
    Batch = 500
    Total = 0
    for Start in range(0, len(Ids), Batch):
        Chunk = Ids[Start:Start + Batch]
        Svc.RecomputeForFiles(Chunk)
        Total += len(Chunk)
        print(f"Recomputed {Total}/{len(Ids)}")
    print(f"Done.")


if __name__ == '__main__':
    Main()
