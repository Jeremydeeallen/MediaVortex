from typing import Tuple


# directive: failure-accounting | # see failure-accounting.C6
def BuildCapPredicate(MediaFileIdColumn: str = "mf.Id") -> Tuple[str, tuple]:
    """Emit the SQL fragment + params that exclude rows whose MediaFile exceeds MaxEncodeFailures consecutive failures. One source of truth for the cap clause; every Claim*, RecomputeForFiles, and NextBatch path calls this. Reads FailureBudgetConfig at SQL evaluation time -- mid-flight config changes apply on next claim."""
    SqlFragment = (
        "(SELECT COUNT(*) FROM TranscodeAttempts ta "
        " WHERE ta.MediaFileId = " + MediaFileIdColumn + " AND ta.Success = FALSE "
        "   AND ta.AttemptDate > GREATEST("
        "     COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = " + MediaFileIdColumn + " AND Success = TRUE), 'epoch'::timestamp), "
        "     COALESCE((SELECT LastFailureResetAt FROM MediaFiles WHERE Id = " + MediaFileIdColumn + "), 'epoch'::timestamp)"
        "   )"
        ") < COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3)"
    )
    return SqlFragment, ()
