# Adds Workers.qsvcapable bool (parallel to nvenccapable). Idempotent; safe to re-run.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    print("Adding Workers.qsvcapable column (idempotent)...")
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS qsvcapable boolean DEFAULT FALSE"
    )
    Row = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM information_schema.columns "
        "WHERE table_name='workers' AND column_name='qsvcapable'"
    )
    if Row and Row[0].get('n') == 1:
        print("  OK -- Workers.qsvcapable present.")
    else:
        print("  ERROR -- column not present after ALTER.")
        sys.exit(1)


if __name__ == "__main__":
    Main()
