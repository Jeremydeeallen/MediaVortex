# Surfaces previously-hardcoded NVENC knobs as Profile columns. Idempotent.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


NEW_COLUMNS = [
    ("spatialaq",    "int"),
    ("temporalaq",   "int"),
    ("weightedpred", "int"),
]


def Main():
    Db = DatabaseService()
    for ColName, ColType in NEW_COLUMNS:
        print(f"ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS {ColName} {ColType}")
        Db.ExecuteNonQuery(
            f"ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS {ColName} {ColType}"
        )
    Check = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='profiles' AND column_name IN "
        "('spatialaq','temporalaq','weightedpred') ORDER BY column_name"
    )
    Present = sorted([R['column_name'] for R in Check])
    Expected = sorted([N for N, _ in NEW_COLUMNS])
    if Present == Expected:
        print(f"  OK -- {len(Present)} columns present: {Present}")
    else:
        print(f"  ERROR -- expected {Expected}, got {Present}")
        sys.exit(1)


if __name__ == "__main__":
    Main()
