import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ORPHAN_COUNT_SQL = "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE MediaFileId IS NULL"

SELECT_ORPHANS_SQL = (
    "SELECT Id, AttemptDate, StorageRootId, RelativePath, ErrorMessage, "
    "ProfileName, WorkerName, Success, Quality, "
    "OldSizeBytes, NewSizeBytes "
    "FROM TranscodeAttempts WHERE MediaFileId IS NULL ORDER BY Id"
)

BACKFILL_FROM_STORAGE_PAIR_SQL = (
    "UPDATE TranscodeAttempts ta "
    "SET MediaFileId = mf.Id "
    "FROM MediaFiles mf "
    "WHERE ta.MediaFileId IS NULL "
    "AND ta.StorageRootId IS NOT NULL AND ta.RelativePath IS NOT NULL "
    "AND mf.StorageRootId = ta.StorageRootId AND mf.RelativePath = ta.RelativePath"
)

DELETE_ORPHANS_SQL = "DELETE FROM TranscodeAttempts WHERE MediaFileId IS NULL"


# directive: failure-accounting | # see failure-accounting.C4
def Main():
    """Idempotent one-shot orphan cleanup: best-effort backfill via (StorageRootId, RelativePath); archive remainder to CSV; delete archived rows."""
    Db = DatabaseService()

    PreCount = int(Db.ExecuteQuery(ORPHAN_COUNT_SQL)[0]['n'])
    print("PRE: TranscodeAttempts with MediaFileId IS NULL = " + str(PreCount))
    if PreCount == 0:
        print("no orphans -- nothing to do.")
        return 0

    Backfilled = Db.ExecuteNonQuery(BACKFILL_FROM_STORAGE_PAIR_SQL)
    MidCount = int(Db.ExecuteQuery(ORPHAN_COUNT_SQL)[0]['n'])
    print("Best-effort backfill via (StorageRootId, RelativePath) -> MediaFileId: "
          + str(PreCount - MidCount) + " rows recovered; " + str(MidCount) + " remain orphan.")

    if MidCount == 0:
        print("All orphans backfilled. No CSV archive needed.")
        return 0

    Stamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    CsvPath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'Reports',
        'OrphanFailedAttempts-' + Stamp + '.csv',
    )

    Rows = Db.ExecuteQuery(SELECT_ORPHANS_SQL)
    with open(CsvPath, 'w', newline='', encoding='utf-8') as Fh:
        Writer = csv.writer(Fh)
        Writer.writerow([
            'Id', 'AttemptDate', 'StorageRootId', 'RelativePath',
            'ErrorMessage', 'ProfileName', 'WorkerName', 'Success',
            'Quality', 'OldSizeBytes', 'NewSizeBytes',
        ])
        for R in Rows:
            Writer.writerow([
                R['Id'], R['AttemptDate'], R['StorageRootId'], R['RelativePath'],
                R['ErrorMessage'], R['ProfileName'], R['WorkerName'], R['Success'],
                R['Quality'], R['OldSizeBytes'], R['NewSizeBytes'],
            ])
    print("Archived " + str(len(Rows)) + " orphan rows to " + CsvPath)

    Db.ExecuteNonQuery(DELETE_ORPHANS_SQL)
    PostCount = int(Db.ExecuteQuery(ORPHAN_COUNT_SQL)[0]['n'])
    print("POST: TranscodeAttempts with MediaFileId IS NULL = " + str(PostCount))
    if PostCount != 0:
        print("FAIL: orphan count nonzero after delete.")
        return 2
    print("status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
