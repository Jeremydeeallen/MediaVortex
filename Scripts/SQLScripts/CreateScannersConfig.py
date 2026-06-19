import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS Scanners ("
    "ScannerName TEXT PRIMARY KEY, "
    "Enabled BOOLEAN NOT NULL DEFAULT FALSE, "
    "IntervalSec INTEGER NOT NULL DEFAULT 300, "
    "BatchSize INTEGER NOT NULL DEFAULT 100, "
    "DryRun BOOLEAN NOT NULL DEFAULT FALSE, "
    "LastRunAt TIMESTAMP, "
    "LastUpdated TIMESTAMP DEFAULT NOW()"
    ")"
)


SEED_NAMES = (
    'AudioVerticalHealth',
    'ContinuousScan',
)


SEED_SQL = (
    "INSERT INTO Scanners (ScannerName, Enabled, IntervalSec, BatchSize, DryRun) "
    "VALUES (%s, FALSE, 300, 100, FALSE) "
    "ON CONFLICT (ScannerName) DO NOTHING"
)


# directive: audio-vertical-phase-1-completion | # see directive.md P3
def Main():
    """Idempotent migration: Scanners orchestrator config table; one row per periodic scan service; defaults Enabled=FALSE."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_SQL)
    for Name in SEED_NAMES:
        Db.ExecuteNonQuery(SEED_SQL, (Name,))
    print(f"Scanners table present; seeded {len(SEED_NAMES)} rows; defaults Enabled=FALSE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
