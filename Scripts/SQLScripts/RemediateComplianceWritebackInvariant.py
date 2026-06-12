import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CONTRADICTION_COUNT_SQL = (
    "SELECT COUNT(*) AS n FROM MediaFiles WHERE NOT ("
    "(IsCompliant = TRUE AND WorkBucket IS NULL "
    "AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv = '')) "
    "OR (IsCompliant = FALSE AND WorkBucket IS NOT NULL "
    "AND OperationsNeededCsv IS NOT NULL AND OperationsNeededCsv != '') "
    "OR (IsCompliant IS NULL AND ComplianceGateBlocked IS NOT NULL) "
    "OR (IsCompliant IS NULL AND WorkBucket IS NULL "
    "AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv = '') "
    "AND ComplianceGateBlocked IS NULL)"
    ")"
)

NARROW_BUG_COUNT_SQL = (
    "SELECT COUNT(*) AS n FROM MediaFiles "
    "WHERE IsCompliant = TRUE AND WorkBucket IS NOT NULL"
)

ALL_IDS_SQL = "SELECT Id FROM MediaFiles ORDER BY Id"

BATCH_SIZE = 500


# directive: compliance-writeback-invariant | # see compliance.C7
def CountContradictions(Db):
    """Return count of MediaFiles rows that violate the C6 three-way disjunction (strict AC1 predicate)."""
    return int(Db.ExecuteQuery(CONTRADICTION_COUNT_SQL)[0]['n'])


# directive: compliance-writeback-invariant | # see compliance.C7
def CountNarrowBug(Db):
    """Return count of the specific BUG-0062 contradictory shape (IsCompliant=TRUE alongside non-null WorkBucket)."""
    return int(Db.ExecuteQuery(NARROW_BUG_COUNT_SQL)[0]['n'])


# directive: compliance-writeback-invariant | # see compliance.C7
def Main():
    """Idempotent BUG-0062 remediation: count contradictions, recompute every MediaFile in batches via the validated writeback path, verify post-count, report pre/post/status."""
    Db = DatabaseService()

    PreNarrow = CountNarrowBug(Db)
    PreStrict = CountContradictions(Db)
    print("PRE  -- narrow bug (IsCompliant=TRUE + WorkBucket non-null): " + str(PreNarrow))
    print("PRE  -- strict AC1 predicate                                  : " + str(PreStrict))

    Ids = [R['Id'] for R in Db.ExecuteQuery(ALL_IDS_SQL)]
    print("Recomputing " + str(len(Ids)) + " MediaFiles in batches of " + str(BATCH_SIZE) + " via QueueManagementBusinessService.RecomputeForFiles...")

    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    QM = QueueManagementBusinessService()

    Written = 0
    Failed = 0
    BatchCount = 0
    for I in range(0, len(Ids), BATCH_SIZE):
        Batch = Ids[I:I + BATCH_SIZE]
        BatchCount += 1
        try:
            N = QM.RecomputeForFiles(Batch)
            Written += int(N or 0)
            if BatchCount % 20 == 0 or I + BATCH_SIZE >= len(Ids):
                print("  batch " + str(BatchCount) + ": " + str(I + len(Batch)) + "/" + str(len(Ids)) + " (cumulative written=" + str(Written) + ")")
        except Exception as Ex:
            Failed += len(Batch)
            print("  BATCH " + str(BatchCount) + " FAILED: " + str(Ex))

    PostNarrow = CountNarrowBug(Db)
    PostStrict = CountContradictions(Db)
    print("POST -- narrow bug (IsCompliant=TRUE + WorkBucket non-null): " + str(PostNarrow))
    print("POST -- strict AC1 predicate                                  : " + str(PostStrict))
    print("Written total: " + str(Written) + " | Failed batches: " + str(Failed))

    Status = "OK" if (PostNarrow == 0) else "FAIL"
    print("status=" + Status)
    return 0 if Status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(Main())
