# directive: target-policy-1a-tables | # see policy.S3 -- a worker's encoder is a function of its two deploy-probed capability flags, nothing else
from typing import Optional

from Core.Database.DatabaseService import DatabaseService

AV1_NVENC = 'av1_nvenc'
AV1_QSV = 'av1_qsv'
LIBSVTAV1 = 'libsvtav1'


# directive: target-policy-1a-tables | # see policy.S3
class EncoderSelector:

    # directive: target-policy-1a-tables | # see policy.S3
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.S3
    def ForWorker(self, WorkerName: str) -> str:
        Rows = self.Db.ExecuteQuery("SELECT nvenccapable, qsvcapable FROM Workers WHERE WorkerName = %s", (WorkerName,))
        if not Rows:
            raise LookupError(f"Workers has no row for WorkerName={WorkerName!r}")
        return self.ForCapabilities(Rows[0]['nvenccapable'], Rows[0]['qsvcapable'])

    @staticmethod
    # directive: target-policy-1a-tables | # see policy.S3
    def ForCapabilities(NvencCapable, QsvCapable) -> str:
        if NvencCapable is True:
            return AV1_NVENC
        if QsvCapable is True:
            return AV1_QSV
        return LIBSVTAV1
