#!/usr/bin/env python3
"""
AddDistributedColumns.py
Database migration for distributed TranscodeService support.
Creates Workers table and adds distributed columns to existing tables.
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

def TableExists(cursor, table_name):
    """Check if a table exists."""
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """, (table_name.lower(),))
    return cursor.fetchone() is not None

def RunMigration():
    """Run all distributed transcoding migrations."""
    connection = GetConnection()
    cursor = connection.cursor()

    try:
        # 1. Create Workers table
        if not TableExists(cursor, 'workers'):
            cursor.execute("""
                CREATE TABLE Workers (
                    Id BIGSERIAL PRIMARY KEY,
                    WorkerName TEXT NOT NULL UNIQUE,
                    Platform TEXT DEFAULT 'windows',
                    FFmpegPath TEXT,
                    FFprobePath TEXT,
                    StagingDirectory TEXT,
                    ShareMountPrefix TEXT,
                    ShareCanonicalPrefix TEXT DEFAULT 'T:\\',
                    MaxConcurrentJobs INT DEFAULT 1,
                    Status TEXT DEFAULT 'Online',
                    LastHeartbeat TIMESTAMP,
                    RegisteredAt TIMESTAMP DEFAULT NOW()
                )
            """)
            connection.commit()
            print("[OK] Created Workers table")
        else:
            print("[SKIP] Workers table already exists")

        # 2. Add ClaimedBy column to TranscodeQueue
        if not ColumnExists(cursor, 'transcodequeue', 'claimedby'):
            cursor.execute("ALTER TABLE TranscodeQueue ADD COLUMN ClaimedBy TEXT")
            connection.commit()
            print("[OK] Added ClaimedBy column to TranscodeQueue")
        else:
            print("[SKIP] TranscodeQueue.ClaimedBy already exists")

        # 3. Add ClaimedAt column to TranscodeQueue
        if not ColumnExists(cursor, 'transcodequeue', 'claimedat'):
            cursor.execute("ALTER TABLE TranscodeQueue ADD COLUMN ClaimedAt TIMESTAMP")
            connection.commit()
            print("[OK] Added ClaimedAt column to TranscodeQueue")
        else:
            print("[SKIP] TranscodeQueue.ClaimedAt already exists")

        # 4. Add WorkerName column to ActiveJobs
        if not ColumnExists(cursor, 'activejobs', 'workername'):
            cursor.execute("ALTER TABLE ActiveJobs ADD COLUMN WorkerName TEXT")
            connection.commit()
            print("[OK] Added WorkerName column to ActiveJobs")
        else:
            print("[SKIP] ActiveJobs.WorkerName already exists")

        # 5. Create WorkerShareMappings table (multi-prefix path translation)
        if not TableExists(cursor, 'workersharemappings'):
            cursor.execute("""
                CREATE TABLE WorkerShareMappings (
                    Id BIGSERIAL PRIMARY KEY,
                    WorkerName TEXT NOT NULL,
                    CanonicalPrefix TEXT NOT NULL,
                    LocalMountPrefix TEXT NOT NULL,
                    UNIQUE(WorkerName, CanonicalPrefix)
                )
            """)
            connection.commit()
            print("[OK] Created WorkerShareMappings table")
        else:
            print("[SKIP] WorkerShareMappings table already exists")

        print("\nMigration completed successfully.")

    except Exception as e:
        connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    print("MediaVortex Distributed Transcoding Migration")
    print("=" * 50)
    RunMigration()
