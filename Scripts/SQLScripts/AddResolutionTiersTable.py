import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS ResolutionTiers ("
    "Id BIGSERIAL PRIMARY KEY, "
    "Name TEXT NOT NULL, "
    "MinLongEdge INTEGER NOT NULL, "
    "CanonicalWidth INTEGER NOT NULL, "
    "CanonicalHeight INTEGER NOT NULL, "
    "Rank INTEGER NOT NULL, "
    "LastUpdated TIMESTAMP DEFAULT NOW()"
    ")"
)

CREATE_UNIQUE_NAME = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_resolutiontiers_name ON ResolutionTiers (Name)"
)


SEEDS = [
    ('T480p',  600,  854,  480,  1),
    ('T720p',  1100, 1280, 720,  2),
    ('T1080p', 1700, 1920, 1080, 3),
    ('T2160p', 3000, 3840, 2160, 4),
]

INSERT_SQL = (
    "INSERT INTO ResolutionTiers (Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank) "
    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (Name) DO NOTHING"
)


# directive: resolution-types | # see resolution-types.C2
def Main():
    """Idempotent migration: ResolutionTiers table + UNIQUE index + 4 seeded tiers."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_SQL)
    Db.ExecuteNonQuery(CREATE_UNIQUE_NAME)
    for Row in SEEDS:
        Db.ExecuteNonQuery(INSERT_SQL, Row)
    print("ResolutionTiers table + 4 seeded tiers present.")
    print("Rollback (1 statement): DROP TABLE IF EXISTS ResolutionTiers;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
