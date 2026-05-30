"""Add rate-anchored mode columns to Profiles + ProfileThresholds.

See Features/Profiles/nvenc-rate-anchored.feature.md criteria 1-6.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


def Run() -> int:
    Db = DatabaseService()

    Db.ExecuteNonQuery(
        "ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS RateControlMode TEXT NOT NULL DEFAULT 'cq'",
        (),
    )

    HasCheck = Db.ExecuteQuery(
        "SELECT conname FROM pg_constraint WHERE conname = 'profiles_ratecontrolmode_check'",
        (),
    )
    if not HasCheck:
        Db.ExecuteNonQuery(
            "ALTER TABLE Profiles ADD CONSTRAINT profiles_ratecontrolmode_check "
            "CHECK (RateControlMode IN ('cq', 'vbr'))",
            (),
        )

    for Stmt in [
        "ALTER TABLE ProfileThresholds ADD COLUMN IF NOT EXISTS SourceBitratePercent INTEGER",
        "ALTER TABLE ProfileThresholds ADD COLUMN IF NOT EXISTS MinBitrateKbps INTEGER",
        "ALTER TABLE ProfileThresholds ADD COLUMN IF NOT EXISTS MaxBitrateKbps INTEGER",
        "ALTER TABLE ProfileThresholds ADD COLUMN IF NOT EXISTS Gop INTEGER",
    ]:
        Db.ExecuteNonQuery(Stmt, ())

    print("Profiles columns:")
    for R in Db.ExecuteQuery(
        "SELECT column_name, data_type, column_default FROM information_schema.columns "
        "WHERE table_name='profiles' AND column_name='ratecontrolmode'",
        (),
    ):
        print(f"  {R}")
    print("ProfileThresholds new columns:")
    for R in Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='profilethresholds' "
        "AND column_name IN ('sourcebitratepercent','minbitratekbps','maxbitratekbps','gop') "
        "ORDER BY column_name",
        (),
    ):
        print(f"  {R.get('column_name')}")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
