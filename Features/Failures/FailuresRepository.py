from typing import List, Dict, Any

from Core.Database.DatabaseService import DatabaseService


_HOUSEKEEPING_SUBSTRINGS = [
    'Application restarted',
    'Zombie',
    'pre-redeploy',
    'Stuck scan cleaned by StuckJobDetectionService',
    'post-deploy mass clear',
    'cleared post-restart',
    'cleared post-deploy',
    'Stopped pre-redeploy',
]


def _IsHousekeepingMessage(Message) -> bool:
    if not Message:
        return False
    Msg = str(Message)
    for S in _HOUSEKEEPING_SUBSTRINGS:
        if S in Msg:
            return True
    return False


# directive: ingest-pipeline-kiss
class FailuresRepository:

    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: probe-fail-loud-no-retry-cap -- surface every row with a recorded probe failure; no cap threshold
    def GetProbeFailures(self, Limit: int = 500) -> List[Dict[str, Any]]:
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, FileName, StorageRootId, RelativePath, "
            "       FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate "
            "FROM MediaFiles "
            "WHERE LastFFprobeError IS NOT NULL "
            "ORDER BY LastFFprobeAttemptDate DESC NULLS LAST "
            "LIMIT %s",
            (int(Limit),),
        )
        return Rows or []

    def GetScanFailures(self, Limit: int = 200) -> List[Dict[str, Any]]:
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, JobId, StorageRootId, RelativePath, WorkerName, "
            "       ErrorMessage, EndTime, LastUpdated "
            "FROM ScanJobs "
            "WHERE Status = 'Failed' "
            "ORDER BY COALESCE(EndTime, LastUpdated) DESC "
            "LIMIT %s",
            (int(Limit) * 3,),
        )
        Filtered = [R for R in (Rows or []) if not _IsHousekeepingMessage(R.get('ErrorMessage') or R.get('errormessage'))]
        return Filtered[: int(Limit)]

    def GetCanonicalPathForScanJob(self, JobId: str) -> str:
        Rows = self.Db.ExecuteQuery(
            "SELECT sj.StorageRootId, sj.RelativePath, sr.CanonicalPrefix "
            "FROM ScanJobs sj "
            "LEFT JOIN StorageRoots sr ON sr.Id = sj.StorageRootId "
            "WHERE sj.JobId = %s LIMIT 1",
            (JobId,),
        )
        if not Rows:
            return ''
        R = Rows[0]
        Prefix = R.get('CanonicalPrefix') or R.get('canonicalprefix') or ''
        Rel = R.get('RelativePath') or R.get('relativepath') or ''
        if not Prefix:
            return Rel
        Sep = '' if Prefix.endswith(('/', '\\')) else '\\'
        return f"{Prefix}{Sep}{Rel}" if Rel else Prefix
