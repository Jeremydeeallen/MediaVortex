"""Add ContentSignals columns to MediaFiles.

See Features/ContentSignals/content-signals.feature.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


def Run() -> int:
    Db = DatabaseService()
    for Stmt in [
        "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS MotionFraction DOUBLE PRECISION",
        "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS SceneChangeRatePerMin DOUBLE PRECISION",
        "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS LumaVariance DOUBLE PRECISION",
    ]:
        Db.ExecuteNonQuery(Stmt, ())
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mediafiles' "
        "AND column_name IN ('motionfraction','scenechangeratepermin','lumavariance') "
        "ORDER BY column_name",
        (),
    )
    print(f"Columns present: {[R.get('column_name') for R in Rows]}")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
