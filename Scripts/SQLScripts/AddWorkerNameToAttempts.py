#!/usr/bin/env python3
"""
AddWorkerNameToAttempts.py
Database migration: adds WorkerName column to TranscodeAttempts.
Preserves per-worker attribution after queue rows are deleted.
Safe to run multiple times (idempotent).
"""

import os
import sys
import psycopg2


def GetConnection():
    """Get database connection using same env vars as Core/Database/DatabaseService.py."""
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex')
    )


def ColumnExists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name.lower(), column_name.lower()))
    return cursor.fetchone() is not None


def RunMigration():
    """Add WorkerName column to TranscodeAttempts."""
    connection = GetConnection()
    cursor = connection.cursor()

    try:
        if not ColumnExists(cursor, 'transcodeattempts', 'workername'):
            cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN WorkerName TEXT")
            connection.commit()
            print("[OK] Added WorkerName column to TranscodeAttempts")
        else:
            print("[SKIP] TranscodeAttempts.WorkerName already exists")

        print("\nMigration completed successfully.")

    except Exception as e:
        connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    print("MediaVortex: Add WorkerName to TranscodeAttempts")
    print("=" * 50)
    RunMigration()
