#!/usr/bin/env python3
"""
AddPerCapabilityConcurrency.py
Database migration: replaces the single MaxConcurrentJobs column with
per-capability concurrency columns on the Workers table.

New columns:
  - MaxConcurrentTranscodeJobs (default 1, CPU-bound)
  - MaxConcurrentQualityTestJobs (default 2, I/O-bound)
  - MaxConcurrentRemuxJobs (default 2, I/O-bound)

Existing MaxConcurrentJobs is preserved for backward compatibility but
no longer read by WorkerService. New columns are seeded from its value
where sensible.

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
    """Run per-capability concurrency migration."""
    Connection = GetConnection()
    Cursor = Connection.cursor()

    try:
        # 1. MaxConcurrentTranscodeJobs (default 1 -- CPU-bound, one job saturates cores)
        if not ColumnExists(Cursor, 'workers', 'maxconcurrenttranscodejobs'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN MaxConcurrentTranscodeJobs INT DEFAULT 1")
            Connection.commit()
            # Seed from existing MaxConcurrentJobs for workers that already had it set
            Cursor.execute("""
                UPDATE Workers
                SET MaxConcurrentTranscodeJobs = COALESCE(MaxConcurrentJobs, 1)
                WHERE MaxConcurrentTranscodeJobs IS NULL OR MaxConcurrentTranscodeJobs = 1
            """)
            Connection.commit()
            print("[OK] Added MaxConcurrentTranscodeJobs column (seeded from MaxConcurrentJobs)")
        else:
            print("[SKIP] Workers.MaxConcurrentTranscodeJobs already exists")

        # 2. MaxConcurrentQualityTestJobs (default 2 -- I/O-bound VMAF)
        if not ColumnExists(Cursor, 'workers', 'maxconcurrentqualitytestjobs'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN MaxConcurrentQualityTestJobs INT DEFAULT 2")
            Connection.commit()
            print("[OK] Added MaxConcurrentQualityTestJobs column (default: 2)")
        else:
            print("[SKIP] Workers.MaxConcurrentQualityTestJobs already exists")

        # 3. MaxConcurrentRemuxJobs (default 2 -- I/O-bound container copy)
        if not ColumnExists(Cursor, 'workers', 'maxconcurrentremuxjobs'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN MaxConcurrentRemuxJobs INT DEFAULT 2")
            Connection.commit()
            print("[OK] Added MaxConcurrentRemuxJobs column (default: 2)")
        else:
            print("[SKIP] Workers.MaxConcurrentRemuxJobs already exists")

        # 4. Add RemuxEnabled capability flag (defaults to TRUE -- if you can transcode, you can remux)
        if not ColumnExists(Cursor, 'workers', 'remuxenabled'):
            Cursor.execute("ALTER TABLE Workers ADD COLUMN RemuxEnabled BOOLEAN DEFAULT TRUE")
            Connection.commit()
            print("[OK] Added RemuxEnabled column (default: TRUE)")
        else:
            print("[SKIP] Workers.RemuxEnabled already exists")

        print("\nPer-capability concurrency migration completed successfully.")

    except Exception as e:
        Connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        Cursor.close()
        Connection.close()


if __name__ == "__main__":
    print("MediaVortex Per-Capability Concurrency Migration")
    print("=" * 50)
    RunMigration()
