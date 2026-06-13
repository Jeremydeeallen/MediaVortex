from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Features.FailureAccounting.Repositories.FailureBudgetConfigRepository import FailureBudgetConfigRepository


# directive: failure-accounting | # see failure-accounting.C1
class FailureBudgetService:
    """Single source of truth for 'may this MediaFile fail again' -- counts consecutive Success=FALSE attempts since the most recent Success=TRUE OR MediaFiles.LastFailureResetAt."""

    # directive: failure-accounting | # see failure-accounting.C1
    def __init__(self, Db: Optional[DatabaseService] = None, ConfigRepo: Optional[FailureBudgetConfigRepository] = None):
        """Constructor injection (DIP). All reads fresh per call -- no caching (db-is-authority)."""
        self.Db = Db or DatabaseService()
        self.ConfigRepo = ConfigRepo or FailureBudgetConfigRepository()

    # directive: failure-accounting | # see failure-accounting.C1
    def CountConsecutiveFailures(self, MediaFileId: int) -> int:
        """Return the consecutive Success=FALSE TranscodeAttempts count since the most recent Success=TRUE OR LastFailureResetAt (whichever is more recent)."""
        Rows = self.Db.ExecuteQuery(
            "SELECT GREATEST("
            "COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = TRUE), 'epoch'::timestamp), "
            "COALESCE((SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s), 'epoch'::timestamp)"
            ") AS cutoff",
            (MediaFileId, MediaFileId),
        )
        Cutoff = Rows[0]['Cutoff'] if Rows else None
        Result = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM TranscodeAttempts "
            "WHERE MediaFileId = %s AND Success = FALSE AND AttemptDate > %s",
            (MediaFileId, Cutoff),
        )
        return int(Result[0]['n']) if Result else 0

    # directive: failure-accounting | # see failure-accounting.C1
    def HasBudgetRemaining(self, MediaFileId: int) -> bool:
        """True when consecutive failures < MaxEncodeFailures. Reads config fresh per call."""
        Cfg = self.ConfigRepo.Get()
        return self.CountConsecutiveFailures(MediaFileId) < Cfg.MaxEncodeFailures
