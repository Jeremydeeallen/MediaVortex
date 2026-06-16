import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_COLUMN_SQL = (
    "ALTER TABLE TranscodeQueue "
    "ADD COLUMN IF NOT EXISTS AudioPolicyJson JSONB"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
def Main():
    """Idempotent migration: add TranscodeQueue.AudioPolicyJson for the admission gate snapshot."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_COLUMN_SQL)
    print("TranscodeQueue.AudioPolicyJson present.")
    print("Rollback: ALTER TABLE TranscodeQueue DROP COLUMN AudioPolicyJson;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
