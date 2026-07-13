import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- Reset 28 item 9 -- capability flags drive routing; per-worker allowlist retired.
def Main():
    """Idempotent: drop Workers.AllowedProfiles column."""
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE Workers DROP COLUMN IF EXISTS AllowedProfiles")
    print("Dropped Workers.AllowedProfiles column (retired per Reset 28 item 9).")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
