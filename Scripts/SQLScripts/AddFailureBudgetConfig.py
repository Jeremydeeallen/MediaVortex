import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_CONFIG_TABLE = (
    "CREATE TABLE IF NOT EXISTS FailureBudgetConfig ("
    "Id INT PRIMARY KEY DEFAULT 1, "
    "MaxEncodeFailures INTEGER NOT NULL DEFAULT 3, "
    "ResetWindowDays INTEGER, "
    "LastUpdated TIMESTAMP DEFAULT NOW(), "
    "CHECK (Id = 1)"
    ")"
)

SEED_CONFIG = (
    "INSERT INTO FailureBudgetConfig (Id, MaxEncodeFailures, ResetWindowDays) "
    "VALUES (1, 3, NULL) ON CONFLICT (Id) DO NOTHING"
)

CREATE_RESETS_TABLE = (
    "CREATE TABLE IF NOT EXISTS FailureBudgetResets ("
    "Id BIGSERIAL PRIMARY KEY, "
    "MediaFileId BIGINT NOT NULL, "
    "OperatorName TEXT NOT NULL, "
    "ResetAt TIMESTAMP NOT NULL DEFAULT NOW(), "
    "PriorFailureCount INTEGER"
    ")"
)

CREATE_RESETS_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_failurebudgetresets_mediafileid ON FailureBudgetResets (MediaFileId, ResetAt DESC)"
)

ADD_LAST_RESET_COL = (
    "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS LastFailureResetAt TIMESTAMP"
)


# directive: failure-accounting | # see failure-accounting.C2
def Main():
    """Idempotent migration: FailureBudgetConfig (single-row), FailureBudgetResets (audit log), MediaFiles.LastFailureResetAt (escape hatch)."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_CONFIG_TABLE)
    Db.ExecuteNonQuery(SEED_CONFIG)
    Db.ExecuteNonQuery(CREATE_RESETS_TABLE)
    Db.ExecuteNonQuery(CREATE_RESETS_IDX)
    Db.ExecuteNonQuery(ADD_LAST_RESET_COL)
    print("FailureBudgetConfig + FailureBudgetResets + MediaFiles.LastFailureResetAt are present.")
    print("Rollback (3 statements):")
    print("  ALTER TABLE MediaFiles DROP COLUMN IF EXISTS LastFailureResetAt;")
    print("  DROP TABLE IF EXISTS FailureBudgetResets;")
    print("  DROP TABLE IF EXISTS FailureBudgetConfig;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
