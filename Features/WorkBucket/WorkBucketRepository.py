from Core.Database.DatabaseService import DatabaseService


BUCKET_TO_PROCESSING_MODE = {
    'Transcode': 'Transcode',
    'Remux': 'Remux',
    'AudioFixOnly': 'AudioFix',
}


BUCKET_TO_URL_KEY = {
    'Transcode': 'Transcode',
    'Remux': 'Remux',
    'Audio': 'AudioFixOnly',
}


COUNT_BY_BUCKET_SQL = (
    "SELECT COUNT(*)::int AS Total, "
    "COUNT(*) FILTER (WHERE EXISTS ("
    "  SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
    "))::int AS AlreadyQueued "
    "FROM MediaFiles mf WHERE mf.WorkBucket = %s"
)


LIST_BY_BUCKET_SQL = (
    "SELECT mf.Id, mf.FileName, mf.Resolution, mf.AudioCodec, mf.AudioLanguages, "
    "mf.SourceIntegratedLufs, mf.SourceTruePeakDbtp, mf.WorkBucket, "
    "mf.VideoCompliantReason, mf.ContainerCompliantReason, mf.AudioCompliantReason, "
    "EXISTS ("
    "  SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
    ") AS InQueue "
    "FROM MediaFiles mf WHERE mf.WorkBucket = %s "
    "ORDER BY mf.Id "
    "LIMIT %s OFFSET %s"
)


EXISTING_PENDING_SQL = (
    "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1"
)


BULK_INSERT_QUEUE_SQL = (
    "INSERT INTO TranscodeQueue ("
    "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
    "  ProcessingMode, Status, Priority, DateAdded"
    ") "
    "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
    "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
    "FROM MediaFiles mf WHERE mf.WorkBucket = %s "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
    ") "
    "ORDER BY mf.Id LIMIT %s"
)


COUNT_BULK_INSERT_TARGETS_SQL = (
    "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
    "WHERE mf.WorkBucket = %s "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
    ")"
)


INSERT_QUEUE_SQL = (
    "INSERT INTO TranscodeQueue ("
    "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
    "  ProcessingMode, Status, Priority, DateAdded"
    ") "
    "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
    "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
    "FROM MediaFiles mf WHERE mf.Id = %s"
)


# directive: work-bucket-landing-pages | # see directive.md C1
class WorkBucketRepository:
    """Read MediaFiles filtered by WorkBucket; queue a single file with the matching ProcessingMode."""

    # directive: work-bucket-landing-pages | # see directive.md C1
    def CountByBucket(self, Bucket):
        """Return (Total, AlreadyQueued) for the given internal bucket name."""
        Rows = DatabaseService().ExecuteQuery(COUNT_BY_BUCKET_SQL, (Bucket,))
        if not Rows:
            return {'Total': 0, 'AlreadyQueued': 0}
        R = Rows[0]
        return {'Total': int(R['total']), 'AlreadyQueued': int(R['alreadyqueued'])}

    # directive: work-bucket-landing-pages | # see directive.md C1
    def ListByBucket(self, Bucket, Offset=0, Limit=50):
        """Return MediaFiles rows for the bucket, paged."""
        Offset = max(0, int(Offset))
        Limit = max(1, min(int(Limit), 200))
        Rows = DatabaseService().ExecuteQuery(LIST_BY_BUCKET_SQL, (Bucket, Limit, Offset))
        return Rows or []

    # directive: h1-operator-control | # see directive.md H1G3
    def QueueNext(self, Bucket, ProcessingMode, Limit=200):
        """Bulk-insert Pending rows for up to Limit idle MediaFiles in the bucket; idempotent via NOT EXISTS guard. Returns {Inserted: N, RemainingCandidates: M}."""
        Limit = max(1, min(int(Limit), 1000))
        Db = DatabaseService()
        Before = Db.ExecuteQuery(COUNT_BULK_INSERT_TARGETS_SQL, (Bucket,))
        BeforeCount = int(Before[0]['c']) if Before else 0
        if BeforeCount == 0:
            return {'Inserted': 0, 'RemainingCandidates': 0}
        Db.ExecuteNonQuery(BULK_INSERT_QUEUE_SQL, (ProcessingMode, Bucket, Limit))
        After = Db.ExecuteQuery(COUNT_BULK_INSERT_TARGETS_SQL, (Bucket,))
        AfterCount = int(After[0]['c']) if After else 0
        return {'Inserted': max(0, BeforeCount - AfterCount), 'RemainingCandidates': AfterCount}

    # directive: work-bucket-landing-pages | # see directive.md C2
    def QueueOne(self, MediaFileId, ProcessingMode):
        """Idempotently insert a Pending TranscodeQueue row; returns ('queued', id) or ('already_queued', id)."""
        Db = DatabaseService()
        Existing = Db.ExecuteQuery(EXISTING_PENDING_SQL, (int(MediaFileId),))
        if Existing:
            return ('already_queued', int(Existing[0]['id']))
        Db.ExecuteNonQuery(INSERT_QUEUE_SQL, (ProcessingMode, int(MediaFileId)))
        Inserted = Db.ExecuteQuery(EXISTING_PENDING_SQL, (int(MediaFileId),))
        NewId = int(Inserted[0]['id']) if Inserted else None
        return ('queued', NewId)
