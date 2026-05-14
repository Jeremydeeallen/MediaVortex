"""Add Enabled column to Workers table.

Allows workers to be disabled (hidden from UI, excluded from job routing)
without deleting their configuration. Idempotent -- safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService

def Run():
    DB = DatabaseService()

    # Add Enabled column (default TRUE so all existing workers remain visible)
    DB.ExecuteNonQuery("""
        ALTER TABLE Workers
        ADD COLUMN IF NOT EXISTS Enabled BOOLEAN NOT NULL DEFAULT TRUE
    """)
    print("Added Enabled column to Workers (default TRUE)")

if __name__ == '__main__':
    Run()
