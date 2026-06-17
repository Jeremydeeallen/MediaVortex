import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS AudioVerticalHealthRuns ("
    "Id BIGSERIAL PRIMARY KEY, "
    "Timestamp TIMESTAMP DEFAULT NOW(), "
    "InvariantName TEXT NOT NULL, "
    "DetectedCount INTEGER NOT NULL DEFAULT 0, "
    "RemediatedCount INTEGER NOT NULL DEFAULT 0, "
    "DurationMs INTEGER NOT NULL DEFAULT 0, "
    "Notes TEXT"
    ")"
)


CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_audioverticalhealthruns_ts "
    "ON AudioVerticalHealthRuns (Timestamp DESC)"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
def Main():
    """Idempotent migration: AudioVerticalHealthRuns audit table for H1."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_TABLE_SQL)
    Db.ExecuteNonQuery(CREATE_INDEX_SQL)
    print("AudioVerticalHealthRuns table + ts index present.")
    print("Rollback: DROP TABLE IF EXISTS AudioVerticalHealthRuns;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
