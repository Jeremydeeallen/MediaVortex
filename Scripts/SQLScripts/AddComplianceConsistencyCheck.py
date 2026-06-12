import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CONSTRAINT_NAME = 'chk_compliance_consistency'

CHECK_SQL = (
    "ALTER TABLE MediaFiles ADD CONSTRAINT " + CONSTRAINT_NAME + " CHECK ("
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

EXISTS_SQL = (
    "SELECT 1 FROM pg_constraint WHERE conname = '" + CONSTRAINT_NAME + "'"
)

DROP_SQL = "ALTER TABLE MediaFiles DROP CONSTRAINT IF EXISTS " + CONSTRAINT_NAME

VIOLATOR_COUNT_SQL = (
    "SELECT COUNT(*) AS N FROM MediaFiles WHERE NOT ("
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


# directive: compliance-writeback-invariant | # see compliance.C9
def Main():
    """Idempotently add CHECK chk_compliance_consistency to MediaFiles. Refuses if existing rows would violate -- run RemediateComplianceWritebackInvariant.py first."""
    Db = DatabaseService()
    Existing = Db.ExecuteQuery(EXISTS_SQL)
    if Existing:
        print("CHECK constraint " + CONSTRAINT_NAME + " already present -- no-op.")
        return 0

    Violators = Db.ExecuteQuery(VIOLATOR_COUNT_SQL)[0]['n']
    if Violators:
        print(
            "REFUSING to add CHECK " + CONSTRAINT_NAME + " -- "
            + str(Violators)
            + " existing rows violate the C6 three-way disjunction.\n"
            "Run: py Scripts/SQLScripts/RemediateComplianceWritebackInvariant.py"
        )
        return 1

    Db.ExecuteNonQuery(CHECK_SQL)
    print("Added CHECK constraint " + CONSTRAINT_NAME + " on MediaFiles.")
    print("Rollback (one statement): " + DROP_SQL)
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
