from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation


INSERT_QUEUE_SQL = (
    "INSERT INTO TranscodeQueue "
    "(StorageRootId, RelativePath, FileName, Directory, "
    "SizeBytes, SizeMB, Priority, Status, DateAdded, "
    "ProcessingMode, MediaFileId) "
    "SELECT m.StorageRootId, COALESCE(m.RelativePath, ''), m.FileName, "
    "regexp_replace(COALESCE(m.RelativePath, ''), '/[^/]+$', ''), "
    "(m.SizeMB * 1024 * 1024)::bigint, m.SizeMB, "
    "100, 'Pending', NOW() AT TIME ZONE 'UTC', "
    "'Transcode', m.Id "
    "FROM MediaFiles m "
    "WHERE m.Id = ANY(%s) "
    "ON CONFLICT (MediaFileId) WHERE Status = 'Pending' AND TestVariantSetId IS NULL DO NOTHING"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class EnqueueRetranscode(IAudioVerticalRemediation):
    """Inserts a Transcode queue row per offending MediaFile (skips files already Pending)."""

    Name = "EnqueueRetranscode"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        """Bulk-insert queue rows for the offending MediaFiles; rowcount reflects actual inserts."""
        if not RowIds:
            return 0
        try:
            Db = DatabaseService()
            Conn = Db.GetConnection()
            try:
                Cur = Conn.cursor()
                Cur.execute(INSERT_QUEUE_SQL, (list(RowIds),))
                Inserted = Cur.rowcount or 0
                Conn.commit()
                return Inserted
            finally:
                Db.CloseConnection(Conn)
        except Exception as Ex:
            LoggingService.LogException(
                "EnqueueRetranscode.Apply failed",
                Ex, self.Name, "Apply",
            )
            return 0
