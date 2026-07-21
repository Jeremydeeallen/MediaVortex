# directive: e2e-bug-fixes | # see e2e-bug-fixes.C28
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE MediaFiles DROP COLUMN IF EXISTS LoudnessMeasurementFailureReason"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'loudnessmeasurementfailurereason'"
    )
    if Rows:
        raise SystemExit("Migration failed: column still present")
    print("Applied. MediaFiles.LoudnessMeasurementFailureReason dropped.")


if __name__ == '__main__':
    Main()
