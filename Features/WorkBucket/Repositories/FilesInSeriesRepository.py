from typing import List
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.MediaFileRow import MediaFileRow
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see work-bucket.C2
class FilesInSeriesRepository:

    # directive: work-transcode-unified | # see work-bucket.C2
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see work-bucket.C2
    def ListFilesInSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> List[MediaFileRow]:
        # see work-bucket.C2
        Sql = (
            "SELECT mf.Id, mf.FileName, "
            "       ROUND(mf.SizeMB::numeric / 1024, 2)::float AS SizeGB, "
            "       mf.Resolution, mf.AudioCodec, mf.AudioLanguages, "
            "       mf.VideoCompliantReason, mf.ContainerCompliantReason, mf.AudioCompliantReason, "
            "       EXISTS ("
            "         SELECT 1 FROM TranscodeQueue tq "
            "          WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
            "       ) AS InQueue "
            "  FROM MediaFiles mf "
            " WHERE mf.WorkBucket = %s "
            "   AND mf.StorageRootId = %s "
            "   AND split_part(mf.RelativePath, '/', 1) = %s "
            " ORDER BY mf.SizeMB DESC NULLS LAST"
        )
        Rows = self.Db.ExecuteQuery(Sql, (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath))
        return [
            MediaFileRow(
                Id=int(R['id']),
                FileName=R['filename'],
                SizeGB=float(R['sizegb']) if R['sizegb'] is not None else 0.0,
                Resolution=R.get('resolution'),
                AudioCodec=R.get('audiocodec'),
                AudioLanguages=R.get('audiolanguages'),
                VideoCompliantReason=R.get('videocompliantreason'),
                ContainerCompliantReason=R.get('containercompliantreason'),
                AudioCompliantReason=R.get('audiocompliantreason'),
                InQueue=bool(R.get('inqueue')),
            )
            for R in Rows
        ]
