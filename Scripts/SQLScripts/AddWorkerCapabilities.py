#!/usr/bin/env python3
"""
AddWorkerCapabilities.py
Database migration for unified WorkerService capability columns.
Adds TranscodeEnabled and ScanEnabled to Workers table.
QualityTestEnabled already exists from AddDistributedColumns.py.
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


def ColumnExists(Cursor, TableName, ColumnName):
    """Check if a column exists in a table."""
    Cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (TableName.lower(), ColumnName.lower()))
    return Cursor.fetchone() is not None


def RunMigration():
    """Run worker capabilities migration."""
    Connection = GetConnection()
    Cursor = Connection.cursor()

    try:
        # 1. Add TranscodeEnabled column to Workers (default TRUE for existing workers)
        if not ColumnExists(Cursor, 'workers', 'transcodeenabled'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN TranscodeEnabled BOOLEAN DEFAULT TRUE")
            Connection.commit()
            print("[OK] Added TranscodeEnabled column to Workers (default: TRUE)")
        else:
            print("[SKIP] Workers.TranscodeEnabled already exists")

        # 2. Add ScanEnabled column to Workers (default FALSE for existing workers)
        if not ColumnExists(Cursor, 'workers', 'scanenabled'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN ScanEnabled BOOLEAN DEFAULT FALSE")
            Connection.commit()
            print("[OK] Added ScanEnabled column to Workers (default: FALSE)")
        else:
            print("[SKIP] Workers.ScanEnabled already exists")

        # 3. Backfill existing workers: ensure all have explicit values
        Cursor.execute("""
            UPDATE Workers
            SET TranscodeEnabled = COALESCE(TranscodeEnabled, TRUE),
                ScanEnabled = COALESCE(ScanEnabled, FALSE),
                QualityTestEnabled = COALESCE(QualityTestEnabled, FALSE)
            WHERE TranscodeEnabled IS NULL
               OR ScanEnabled IS NULL
               OR QualityTestEnabled IS NULL
        """)
        RowsUpdated = Cursor.rowcount
        Connection.commit()
        if RowsUpdated > 0:
            print(f"[OK] Backfilled {RowsUpdated} workers with default capability values")
        else:
            print("[SKIP] All workers already have capability values set")

        print("\nWorker capabilities migration completed successfully.")

    except Exception as e:
        Connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        Cursor.close()
        Connection.close()


if __name__ == "__main__":
    print("MediaVortex Worker Capabilities Migration")
    print("=" * 50)
    RunMigration()
