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

    # directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
    def AdmitOne(self, MediaFileId: int, Bucket: BucketKey, QualityLabel: str = None, QualityTier: int = None) -> AdmitOneResult:
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Result = QueueManagementBusinessService().AddJobToQueue(
            MediaFileId=MediaFileId,
            ProcessingMode=Bucket.ProcessingMode,
            ForceAdd=True,
            QualityLabel=QualityLabel,
            QualityTier=QualityTier,
        )
        Status = self._ClassifyAddJobResult(Result)
        QueueId = int(Result.get('ItemId', 0)) if Status in ('queued', 'already_queued') else 0
        Reason = Result.get('Message') or Result.get('ErrorMessage') or ''
        LogLine = f"Admit one: media_file={MediaFileId} bucket={Bucket.BucketName} status={Status}"
        if Reason:
            LogLine += f" reason={Reason}"
        LoggingService.LogInfo(LogLine, "QueueAdmissionAppService", "AdmitOne")
        return AdmitOneResult(Status=Status, QueueId=QueueId)

    # directive: transcode-flow-canonical | # see work-bucket.C4 -- tally EVERY per-file outcome distinctly; do not collapse admission-deferred / skipped / errored into AlreadyQueued (that hid 386 files behind a misleading count)
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        Rows = self.Db.ExecuteQuery(
            "SELECT mf.Id FROM MediaFiles mf "
            "WHERE mf.WorkBucket = %s "
            "  AND mf.StorageRootId = %s "
            "  AND split_part(mf.RelativePath, '/', 1) = %s",
            (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
        )
        Total = len(Rows)
        Counts = {'queued': 0, 'already_queued': 0, 'skipped': 0, 'admission_deferred': 0, 'error': 0}
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Svc = QueueManagementBusinessService()
        for Row in Rows:
            MediaFileId = int(Row['id'])
            R = Svc.AddJobToQueue(MediaFileId=MediaFileId, ProcessingMode=Bucket.ProcessingMode, ForceAdd=True)
            Status = self._ClassifyAddJobResult(R)
            Counts[Status] += 1
        LoggingService.LogInfo(
            f"Admit series: {Identity.ToCompositeKey()} bucket={Bucket.BucketName} total={Total} queued={Counts['queued']} already={Counts['already_queued']} skipped={Counts['skipped']} deferred={Counts['admission_deferred']} error={Counts['error']}",
            "QueueAdmissionAppService",
            "AdmitSeries",
        )
        return AdmissionResult(
            Inserted=Counts['queued'],
            AlreadyQueued=Counts['already_queued'],
            Total=Total,
            Skipped=Counts['skipped'],
            AdmissionDeferred=Counts['admission_deferred'],
            Errored=Counts['error'],
        )

    # directive: transcode-flow-canonical -- SSOT for AddJobToQueue result -> outcome bucket mapping; reused by AdmitOne + AdmitSeries
    def _ClassifyAddJobResult(self, R: dict) -> str:
        if R.get('AlreadyQueued'):
            return 'already_queued'
        if R.get('AdmissionDeferred'):
            return 'admission_deferred'
        if R.get('Skipped'):
            return 'skipped'
        if R.get('Success'):
            return 'queued'
        return 'error'
