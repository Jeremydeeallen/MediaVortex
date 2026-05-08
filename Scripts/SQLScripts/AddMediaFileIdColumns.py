#!/usr/bin/env python3
"""
AddMediaFileIdColumns.py
Database migration: add MediaFileId BIGINT column and index to all child tables
that currently join to MediaFiles via FilePath.

Tables: TranscodeFiles, TranscodeAttempts, TranscodeQueue, CompliantFiles, ProblemFiles

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


def TableExists(Cursor, TableName):
    """Check if a table exists."""
    Cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """, (TableName.lower(),))
    return Cursor.fetchone() is not None


CHILD_TABLES = [
    'TranscodeFiles',
    'TranscodeAttempts',
    'TranscodeQueue',
    'CompliantFiles',
    'ProblemFiles',
]


def RunMigration():
    """Add MediaFileId column and index to all child tables."""
    Connection = GetConnection()
    Cursor = Connection.cursor()

    try:
        for Table in CHILD_TABLES:
            if not TableExists(Cursor, Table):
                print(f"[SKIP] {Table} table does not exist")
                continue

            # Add MediaFileId column
            if not ColumnExists(Cursor, Table, 'mediafileid'):
                Cursor.execute(f"ALTER TABLE {Table} ADD COLUMN MediaFileId BIGINT")
                Connection.commit()
                print(f"[OK] Added MediaFileId column to {Table}")
            else:
                print(f"[SKIP] {Table}.MediaFileId already exists")

            # Add index on MediaFileId
            IndexName = f"idx_{Table.lower()}_mediafileid"
            Cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = %s AND indexname = %s
            """, (Table.lower(), IndexName))
            if not Cursor.fetchone():
                Cursor.execute(f"CREATE INDEX {IndexName} ON {Table} (MediaFileId)")
                Connection.commit()
                print(f"[OK] Created index {IndexName} on {Table}")
            else:
                print(f"[SKIP] Index {IndexName} already exists")

        print("\nMigration completed successfully.")

    except Exception as e:
        Connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        Cursor.close()
        Connection.close()


if __name__ == "__main__":
    print("MediaVortex Surrogate Key Migration - Add MediaFileId Columns")
    print("=" * 60)
    RunMigration()
