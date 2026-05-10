"""Backfill MediaFiles.ResolutionCategory from Resolution. Idempotent."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Sql = """
        UPDATE MediaFiles
        SET ResolutionCategory = CASE
            WHEN Resolution IS NULL OR position('x' in Resolution) = 0 THEN NULL
            WHEN CAST(split_part(Resolution, 'x', 1) AS INTEGER) >= 3840 THEN '2160p'
            WHEN CAST(split_part(Resolution, 'x', 1) AS INTEGER) >= 1920 THEN '1080p'
            WHEN CAST(split_part(Resolution, 'x', 1) AS INTEGER) >= 1280 THEN '720p'
            WHEN CAST(split_part(Resolution, 'x', 1) AS INTEGER) >= 854  THEN '480p'
            ELSE '480p'
        END
        WHERE ResolutionCategory IS NULL
          AND Resolution IS NOT NULL
          AND position('x' in Resolution) > 0
    """
    Rows = Db.ExecuteNonQuery(Sql)
    print(f"Updated {Rows} rows.")

    # Verification: counts by category now
    print("\nResolutionCategory distribution post-backfill:")
    for R in Db.ExecuteQuery("SELECT ResolutionCategory, COUNT(*) AS N FROM MediaFiles GROUP BY ResolutionCategory ORDER BY N DESC"):
        Label = R['ResolutionCategory'] if R['ResolutionCategory'] else '(still NULL)'
        print(f"  {Label:15}  n={R['N']}")


if __name__ == "__main__":
    Main()
