# directive: videoslotstrategy-persisted | # see post-transcode-disposition.C42
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService


# directive: videoslotstrategy-persisted -- one-shot recovery: files whose Remux/AudioFix attempts were incorrectly Rejected under the pre-fix InsufficientSavings gate; re-INSERT TranscodeQueue rows so the fixed decider can process them.
def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT ta.MediaFileId, mf.WorkBucket "
        "FROM TranscodeAttempts ta "
        "JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
        "WHERE ta.DispositionReason LIKE 'InsufficientSavings%%' "
        "  AND ta.AttemptDate > NOW() - INTERVAL '72 hours' "
        "  AND mf.WorkBucket IN ('Remux', 'AudioFix') "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM TranscodeQueue tq "
        "    WHERE tq.MediaFileId = ta.MediaFileId "
        "      AND tq.Status IN ('Pending', 'Running')"
        "  )"
    )
    Candidates = [(int(R.get('mediafileid')), R.get('workbucket')) for R in Rows]
    print(f"Found {len(Candidates)} orphaned MediaFileIds to re-queue.")
    Admitted = 0
    Skipped = 0
    for MediaFileId, WorkBucket in Candidates:
        ProcessingMode = WorkBucket
        SrcRow = Db.ExecuteQuery(
            "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )
        if not SrcRow:
            Skipped += 1
            continue
        StorageRootId = SrcRow[0].get('storagerootid')
        RelativePath = SrcRow[0].get('relativepath')
        if StorageRootId is None or not RelativePath:
            Skipped += 1
            continue
        Affected = Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue "
            "(MediaFileId, StorageRootId, RelativePath, ProcessingMode, Status, DateAdded, AudioPolicyJson) "
            "VALUES (%s, %s, %s, %s, 'Pending', NOW(), NULL) "
            "ON CONFLICT (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL DO NOTHING",
            (MediaFileId, StorageRootId, RelativePath, ProcessingMode),
        )
        if Affected and int(Affected) > 0:
            Admitted += 1
        else:
            Skipped += 1
    print(f"Admitted: {Admitted}, Skipped (already queued or missing typed pair): {Skipped}")


if __name__ == '__main__':
    Main()
