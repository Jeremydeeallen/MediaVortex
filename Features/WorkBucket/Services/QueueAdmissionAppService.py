from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.AdmissionResult import AdmissionResult
from Features.WorkBucket.Domain.AdmitOneResult import AdmitOneResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: transcode-worker-unification | # see work-bucket.C4, work-bucket.C5
class QueueAdmissionAppService:

    # directive: transcode-worker-unification | # see work-bucket.C4, work-bucket.C5
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-worker-unification | # see work-bucket.C5
    def AdmitOne(self, MediaFileId: int, Bucket: BucketKey) -> AdmitOneResult:
        # see work-bucket.C5
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Result = QueueManagementBusinessService().AddJobToQueue(
            MediaFileId=MediaFileId,
            ProcessingMode=Bucket.ProcessingMode,
            ForceAdd=True,
        )
        if Result.get('AlreadyQueued'):
            Status = 'already_queued'
            QueueId = int(Result.get('ItemId', 0))
        elif Result.get('Skipped'):
            Status = 'skipped'
            QueueId = 0
        elif Result.get('Success'):
            Status = 'queued'
            QueueId = int(Result.get('ItemId', 0))
        else:
            Status = 'error'
            QueueId = 0
        Reason = Result.get('Message') or Result.get('ErrorMessage') or ''
        LogLine = f"Admit one: media_file={MediaFileId} bucket={Bucket.BucketName} status={Status}"
        if Reason:
            LogLine += f" reason={Reason}"
        LoggingService.LogInfo(LogLine, "QueueAdmissionAppService", "AdmitOne")
        return AdmitOneResult(Status=Status, QueueId=QueueId)

    # directive: transcode-worker-unification | # see work-bucket.C4
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        # see work-bucket.C4
        Rows = self.Db.ExecuteQuery(
            "SELECT mf.Id FROM MediaFiles mf "
            "WHERE mf.WorkBucket = %s "
            "  AND mf.StorageRootId = %s "
            "  AND split_part(mf.RelativePath, '/', 1) = %s",
            (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
        )
        Total = len(Rows)
        Inserted = 0
        AlreadyQueued = 0
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Svc = QueueManagementBusinessService()
        for Row in Rows:
            MediaFileId = int(Row['id'])
            R = Svc.AddJobToQueue(MediaFileId=MediaFileId, ProcessingMode=Bucket.ProcessingMode, ForceAdd=True)
            if R.get('AlreadyQueued'):
                AlreadyQueued += 1
            elif R.get('Success') and not R.get('Skipped'):
                Inserted += 1
            else:
                AlreadyQueued += 1
        LoggingService.LogInfo(
            f"Admit series: {Identity.ToCompositeKey()} bucket={Bucket.BucketName} inserted={Inserted} already={AlreadyQueued}",
            "QueueAdmissionAppService",
            "AdmitSeries",
        )
        return AdmissionResult(Inserted=Inserted, AlreadyQueued=AlreadyQueued, Total=Total)
