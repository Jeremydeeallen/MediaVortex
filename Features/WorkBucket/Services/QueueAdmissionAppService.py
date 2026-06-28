from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.AdmissionResult import AdmissionResult
from Features.WorkBucket.Domain.AdmitOneResult import AdmitOneResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.QueueAdmissionRepository import QueueAdmissionRepository


# directive: work-transcode-unified | # see work-bucket.C4, work-bucket.C5
class QueueAdmissionAppService:

    # directive: work-transcode-unified | # see work-bucket.C4, work-bucket.C5
    def __init__(
        self,
        Db: Optional[DatabaseService] = None,
        Repo: Optional[QueueAdmissionRepository] = None,
    ):
        self.Db = Db or DatabaseService()
        self.Repo = Repo or QueueAdmissionRepository(self.Db)

    # directive: work-transcode-unified | # see work-bucket.C5
    def AdmitOne(self, MediaFileId: int, Bucket: BucketKey) -> AdmitOneResult:
        # see work-bucket.C5
        Result = self.Repo.AdmitOne(MediaFileId, Bucket.ProcessingMode)
        LoggingService.LogInfo(
            f"Admit one: media_file={MediaFileId} bucket={Bucket.BucketName} status={Result.Status}",
            "QueueAdmissionAppService",
            "AdmitOne",
        )
        return Result

    # directive: work-transcode-unified | # see work-bucket.C4
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        # see work-bucket.C4
        Result = self.Repo.AdmitSeries(Identity, Bucket)
        LoggingService.LogInfo(
            f"Admit series: {Identity.ToCompositeKey()} bucket={Bucket.BucketName} inserted={Result.Inserted} already={Result.AlreadyQueued}",
            "QueueAdmissionAppService",
            "AdmitSeries",
        )
        return Result
