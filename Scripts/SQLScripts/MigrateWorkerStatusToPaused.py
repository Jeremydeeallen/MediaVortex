"""
Migrate Workers.Status from 'Offline' to 'Paused'.

Part of the worker-status-model feature: the Offline value is retired from
the operational-state enum.  Liveness (container running / dead) is now
derived from heartbeat freshness, not from Workers.Status.

Idempotent -- safe to run multiple times.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService

def Main():
    DB = DatabaseService()

    # Check how many rows have Offline
    Rows = DB.ExecuteQuery("SELECT WorkerName FROM Workers WHERE Status = 'Offline'")
    Count = len(Rows) if Rows else 0

    if Count == 0:
        print("No workers with Status='Offline' -- nothing to migrate.")
        return

    print(f"Migrating {Count} worker(s) from Status='Offline' to 'Paused':")
    for Row in Rows:
        print(f"  - {Row['workername']}")

    DB.ExecuteNonQuery("UPDATE Workers SET Status = 'Paused' WHERE Status = 'Offline'")
    print("Done.")

if __name__ == "__main__":
    Main()
