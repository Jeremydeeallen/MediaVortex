# see probe-worker-decoupled.C2 -- adds Workers.ProbeEnabled; idempotent.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS ProbeEnabled BOOLEAN")
    print("Added Workers.ProbeEnabled (nullable BOOLEAN)")


if __name__ == '__main__':
    Run()
