# directive: video-compliance-multiplier | # see video-encoding.C1
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: video-compliance-multiplier
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS VideoComplianceThresholds ("
        "  Id SERIAL PRIMARY KEY,"
        "  ResolutionCategory TEXT NOT NULL UNIQUE,"
        "  Multiplier NUMERIC(4,2) NOT NULL CHECK (Multiplier > 0),"
        "  LastUpdated TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    )
    # from: DOMAIN.md 2026-07-26 "Per-resolution multiplier defaults" table
    Seed = [
        ('480p', 1.5),
        ('720p', 2.0),
        ('1080p', 2.0),
        ('2160p', 3.0),
    ]
    for ResolutionCategory, Multiplier in Seed:
        Db.ExecuteNonQuery(
            "INSERT INTO VideoComplianceThresholds (ResolutionCategory, Multiplier) "
            "VALUES (%s, %s) "
            "ON CONFLICT (ResolutionCategory) DO NOTHING",
            (ResolutionCategory, Multiplier),
        )
    Rows = Db.ExecuteQuery(
        "SELECT ResolutionCategory, Multiplier FROM VideoComplianceThresholds ORDER BY ResolutionCategory"
    )
    print("Applied. VideoComplianceThresholds rows:")
    for R in Rows:
        Res = R.get('resolutioncategory')
        Mult = R.get('multiplier')
        print(f"  {Res}: {Mult}x")


if __name__ == '__main__':
    Main()
