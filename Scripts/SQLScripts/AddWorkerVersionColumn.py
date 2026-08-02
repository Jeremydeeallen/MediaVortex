# see .claude/rules/worker-lifecycle-invariants.md I3 -- adds Version + BuildInfo columns to Workers; idempotent
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS Version VARCHAR(64)")
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS BuildInfo TEXT")
    print("Added Version (VARCHAR(64)) and BuildInfo (TEXT) columns to Workers")


if __name__ == '__main__':
    Run()
