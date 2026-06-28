from typing import Tuple
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.AdmissionResult import AdmissionResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see work-bucket.C4, work-bucket.C5
class QueueAdmissionRepository:

    # directive: work-transcode-unified | # see work-bucket.C4, work-bucket.C5
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see work-bucket.C5
    def AdmitOne(self, MediaFileId: int, ProcessingMode: str) -> Tuple[str, int]:
        # see work-bucket.C5
        Existing = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1",
            (int(MediaFileId),),
        )
        if Existing:
            return ('already_queued', int(Existing[0]['id']))
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue ("
            "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
            "  ProcessingMode, Status, Priority, DateAdded"
            ") "
            "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
            "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
            "FROM MediaFiles mf WHERE mf.Id = %s",
            (ProcessingMode, int(MediaFileId)),
        )
        Inserted = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1",
            (int(MediaFileId),),
        )
        return ('queued', int(Inserted[0]['id']) if Inserted else 0)

    # directive: work-transcode-unified | # see work-bucket.C4
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        # see work-bucket.C4
        Total = int(
            self.Db.ExecuteQuery(
                "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
                "WHERE mf.WorkBucket = %s "
                "  AND mf.StorageRootId = %s "
                "  AND split_part(mf.RelativePath, '/', 1) = %s",
                (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
            )[0]['c']
        )
        BeforeCandidates = int(
            self.Db.ExecuteQuery(
                "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
                "WHERE mf.WorkBucket = %s "
                "  AND mf.StorageRootId = %s "
                "  AND split_part(mf.RelativePath, '/', 1) = %s "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM TranscodeQueue tq "
                "     WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
                "  )",
                (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
            )[0]['c']
        )
        if BeforeCandidates == 0:
            return AdmissionResult(Inserted=0, AlreadyQueued=Total, Total=Total)
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue ("
            "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
            "  ProcessingMode, Status, Priority, DateAdded"
            ") "
            "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
            "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
            "FROM MediaFiles mf "
            " WHERE mf.WorkBucket = %s "
            "   AND mf.StorageRootId = %s "
            "   AND split_part(mf.RelativePath, '/', 1) = %s "
            "   AND NOT EXISTS ("
            "     SELECT 1 FROM TranscodeQueue tq "
            "      WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
            "   )",
            (Bucket.ProcessingMode, Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
        )
        AfterCandidates = int(
            self.Db.ExecuteQuery(
                "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
                "WHERE mf.WorkBucket = %s "
                "  AND mf.StorageRootId = %s "
                "  AND split_part(mf.RelativePath, '/', 1) = %s "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM TranscodeQueue tq "
                "     WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
                "  )",
                (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
            )[0]['c']
        )
        Inserted = max(0, BeforeCandidates - AfterCandidates)
        return AdmissionResult(Inserted=Inserted, AlreadyQueued=Total - Inserted, Total=Total)
