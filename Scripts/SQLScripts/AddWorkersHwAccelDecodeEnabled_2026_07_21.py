# directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS HwAccelDecodeEnabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    Rows = Db.ExecuteQuery(
        "SELECT WorkerName, HwAccelDecodeEnabled FROM Workers ORDER BY WorkerName"
    )
    print("Applied. Worker rows carrying HwAccelDecodeEnabled:")
    for R in Rows:
        Name = R.get('workername')
        Val = R.get('hwacceldecodeenabled')
        print(f"  {Name}: {Val}")


if __name__ == '__main__':
    Main()
