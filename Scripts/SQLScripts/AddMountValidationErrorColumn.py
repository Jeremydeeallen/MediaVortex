"""Add MountValidationError column to Workers table.

Stores the last mount-validation failure reason so the Activity page can
show why a worker is stuck in Paused. NULL = no failure on last check.
Idempotent -- safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService

def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("""
        ALTER TABLE Workers
        ADD COLUMN IF NOT EXISTS MountValidationError TEXT
    """)
    print("Added MountValidationError column to Workers (nullable TEXT)")

if __name__ == '__main__':
    Run()
