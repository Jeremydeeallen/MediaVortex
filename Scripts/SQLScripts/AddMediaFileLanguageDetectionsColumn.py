import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_COLUMN_SQL = (
    "ALTER TABLE MediaFiles "
    "ADD COLUMN IF NOT EXISTS AudioStreamLanguageDetectionsJson JSONB"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
def Main():
    """Idempotent migration: add MediaFiles.AudioStreamLanguageDetectionsJson speech-detection cache."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_COLUMN_SQL)
    print("MediaFiles.AudioStreamLanguageDetectionsJson present.")
    print("Rollback: ALTER TABLE MediaFiles DROP COLUMN AudioStreamLanguageDetectionsJson;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
