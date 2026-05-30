"""Add RemuxedByMediaVortex + RemuxedByMediaVortexDate columns to MediaFiles.

See Features/FileReplacement/remuxed-flag.feature.md.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


def Run() -> int:
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS RemuxedByMediaVortex BOOLEAN DEFAULT FALSE",
        (),
    )
    Db.ExecuteNonQuery(
        "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS RemuxedByMediaVortexDate TIMESTAMP",
        (),
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mediafiles' AND column_name IN ('remuxedbymediavortex','remuxedbymediavortexdate') "
        "ORDER BY column_name",
        (),
    )
    print(f"Columns present: {[R.get('column_name') for R in Rows]}")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
