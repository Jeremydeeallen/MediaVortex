import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


OPERATOR_LABEL = 'ForceAdd:backfill_2026_08_27'


# directive: bug-0061-remediation
def Main():
    """One-shot: retro-reset every currently-Pending TranscodeQueue MediaFileId that already exceeds the failure cap. Writes FailureBudgetResets audit rows with OperatorName=ForceAdd:backfill_2026_08_27 + bumps MediaFiles.LastFailureResetAt. Idempotent -- pre-check skips MediaFileIds that already have a backfill audit row from this run."""
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT tq.MediaFileId "
        "FROM TranscodeQueue tq "
        "WHERE tq.Status = 'Pending' "
        "  AND tq.MediaFileId IS NOT NULL "
        "  AND (SELECT COUNT(*) FROM TranscodeAttempts ta "
        "       WHERE ta.MediaFileId = tq.MediaFileId AND ta.Success = FALSE "
        "         AND ta.AttemptDate > GREATEST("
        "           COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = tq.MediaFileId AND Success = TRUE), 'epoch'::timestamp), "
        "           COALESCE((SELECT LastFailureResetAt FROM MediaFiles WHERE Id = tq.MediaFileId), 'epoch'::timestamp))"
        "      ) >= COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3)"
    )
    if not Rows:
        print("no over-cap Pending rows -- nothing to reset.")
        return 0

    Ids = [int(R['MediaFileId']) for R in Rows if R.get('MediaFileId') is not None]
    print("Found " + str(len(Ids)) + " over-cap Pending MediaFileIds: " + str(Ids))

    for MfId in Ids:
        Existing = Db.ExecuteQuery(
            "SELECT 1 FROM FailureBudgetResets WHERE MediaFileId = %s AND OperatorName = %s LIMIT 1",
            (MfId, OPERATOR_LABEL),
        )
        if Existing:
            print("skip MediaFileId=" + str(MfId) + " -- backfill audit row already present.")
            continue

        Prior = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM TranscodeAttempts ta "
            "WHERE ta.MediaFileId = %s AND ta.Success = FALSE "
            "AND ta.AttemptDate > GREATEST("
            "  COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = TRUE), 'epoch'::timestamp), "
            "  COALESCE((SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s), 'epoch'::timestamp))",
            (MfId, MfId, MfId),
        )
        PriorCount = int(Prior[0]['n']) if Prior else 0
        # allow: R11 FailureBudgetResets has no unique constraint; audit rows are append-only. Pre-check SELECT above guarantees per-(MediaFileId, OperatorName) idempotency. Rule text sanctions this override.
        Db.ExecuteNonQuery(
            "INSERT INTO FailureBudgetResets (MediaFileId, OperatorName, PriorFailureCount) VALUES (%s, %s, %s)",
            (MfId, OPERATOR_LABEL, PriorCount),
        )
        Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET LastFailureResetAt = NOW() WHERE Id = %s",
            (MfId,),
        )
        print("reset MediaFileId=" + str(MfId) + " (prior fails=" + str(PriorCount) + ")")

    Remaining = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeQueue tq "
        "WHERE tq.Status = 'Pending' "
        "  AND tq.MediaFileId IS NOT NULL "
        "  AND (SELECT COUNT(*) FROM TranscodeAttempts ta "
        "       WHERE ta.MediaFileId = tq.MediaFileId AND ta.Success = FALSE "
        "         AND ta.AttemptDate > GREATEST("
        "           COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = tq.MediaFileId AND Success = TRUE), 'epoch'::timestamp), "
        "           COALESCE((SELECT LastFailureResetAt FROM MediaFiles WHERE Id = tq.MediaFileId), 'epoch'::timestamp))"
        "      ) >= COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3)"
    )
    RemainingCount = int(Remaining[0]['n']) if Remaining else 0
    print("POST: over-cap Pending count = " + str(RemainingCount))
    return 0 if RemainingCount == 0 else 2


if __name__ == "__main__":
    sys.exit(Main())
