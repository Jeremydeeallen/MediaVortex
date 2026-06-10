import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C1
def ColumnExists():
    """Return True if PostTranscodeGateConfig.MaxRequeueAttempts already exists."""
    DB = DatabaseService()
    Query = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s"
    )
    Rows = DB.ExecuteQuery(Query, ('posttranscodegateconfig', 'maxrequeueattempts'))
    return len(Rows) > 0


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C1
def Run():
    """Add PostTranscodeGateConfig.MaxRequeueAttempts INTEGER NOT NULL DEFAULT 3 (idempotent)."""
    AlreadyPresent = ColumnExists()
    DB = DatabaseService()
    Sql = (
        "ALTER TABLE PostTranscodeGateConfig "
        "ADD COLUMN IF NOT EXISTS MaxRequeueAttempts INTEGER NOT NULL DEFAULT 3"
    )
    DB.ExecuteNonQuery(Sql)
    if AlreadyPresent:
        print("SKIPPED (column exists)")
    else:
        print("OK")


if __name__ == '__main__':
    Run()
