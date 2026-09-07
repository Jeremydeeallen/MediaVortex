import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


IS_NULLABLE_SQL = (
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_name = 'transcodeattempts' AND column_name = 'mediafileid'"
)
DROP_NOT_NULL_SQL = "ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId DROP NOT NULL"


# directive: bug-0096-scan-delete-restore-archival | # see scan.C15
def Main():
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(IS_NULLABLE_SQL)
    if Rows and str(Rows[0]['is_nullable']).upper() == 'YES':
        print("TranscodeAttempts.MediaFileId already nullable -- no-op.")
        return 0

    Db.ExecuteNonQuery(DROP_NOT_NULL_SQL)
    print("TranscodeAttempts.MediaFileId is now nullable. Archival cascade path (FK ON DELETE SET NULL) restored.")
    print("Rollback (only after CleanupOrphanFailedAttempts.py): ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId SET NOT NULL")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
