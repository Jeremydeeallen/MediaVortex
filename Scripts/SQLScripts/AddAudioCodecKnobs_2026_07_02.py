import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


NEW_COLUMNS = [
    ("Track0Codec", "TEXT NOT NULL DEFAULT 'opus'"),
    ("Track1Codec", "TEXT NOT NULL DEFAULT 'opus'"),
]


def Main():
    Db = DatabaseService()
    for Name, Ddl in NEW_COLUMNS:
        Db.ExecuteNonQuery(
            f"ALTER TABLE AudioComplianceRules ADD COLUMN IF NOT EXISTS {Name} {Ddl}"
        )
    print(f'AudioComplianceRules: {len(NEW_COLUMNS)} codec columns added (default opus).')
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
