import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


NULL_COUNT_SQL = "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE MediaFileId IS NULL"
IS_NULLABLE_SQL = (
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_name = 'transcodeattempts' AND column_name = 'mediafileid'"
)
SET_NOT_NULL_SQL = "ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId SET NOT NULL"


# directive: failure-accounting | # see failure-accounting.C3
def Main():
    """Idempotent NOT NULL migration on TranscodeAttempts.MediaFileId. Refuses if any NULL rows remain (run CleanupOrphanFailedAttempts.py first)."""
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(IS_NULLABLE_SQL)
    if Rows and str(Rows[0]['is_nullable']).upper() == 'NO':
        print("TranscodeAttempts.MediaFileId already NOT NULL -- no-op.")
        return 0

    NullCount = int(Db.ExecuteQuery(NULL_COUNT_SQL)[0]['n'])
    if NullCount:
        print("REFUSING to set NOT NULL -- " + str(NullCount) + " rows still have MediaFileId IS NULL.")
        print("Run: py Scripts/SQLScripts/CleanupOrphanFailedAttempts.py")
        return 1

    Db.ExecuteNonQuery(SET_NOT_NULL_SQL)
    print("TranscodeAttempts.MediaFileId is now NOT NULL.")
    print("Rollback (one statement): ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId DROP NOT NULL")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
