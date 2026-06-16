import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_POLICY_JSON_SQL = (
    "ALTER TABLE TranscodeAttempts "
    "ADD COLUMN IF NOT EXISTS AudioPolicyJson JSONB"
)

ADD_TRACKS_EMITTED_SQL = (
    "ALTER TABLE TranscodeAttempts "
    "ADD COLUMN IF NOT EXISTS AudioTracksEmittedJson JSONB"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
def Main():
    """Idempotent migration: add TranscodeAttempts.AudioPolicyJson + AudioTracksEmittedJson."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_POLICY_JSON_SQL)
    Db.ExecuteNonQuery(ADD_TRACKS_EMITTED_SQL)
    print("TranscodeAttempts.AudioPolicyJson + AudioTracksEmittedJson present.")
    print("Rollback: ALTER TABLE TranscodeAttempts DROP COLUMN AudioPolicyJson, DROP COLUMN AudioTracksEmittedJson;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
