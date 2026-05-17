#!/usr/bin/env python3
"""
AddNeedsReprobeColumn.py
Phase 2.5 migration for media-tabs-and-loudness.feature.md (criteria 11-14).

Adds one nullable column to MediaFiles:
  - NeedsReprobe BOOLEAN DEFAULT FALSE -- when TRUE, the MediaProbe batch
    loop picks this row up regardless of whether existing metadata columns
    are populated. Cleared back to FALSE on successful probe.

Plus one partial index for fast operator visibility queries:
  idx_mediafiles_needs_reprobe ON MediaFiles (Id)
    WHERE NeedsReprobe = TRUE

Idempotent. Safe to run multiple times.
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def IndexExists(Cursor, IndexName):
    Cursor.execute("SELECT indexname FROM pg_indexes WHERE indexname = %s", (IndexName.lower(),))
    return Cursor.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if ColumnExists(Cur, 'MediaFiles', 'NeedsReprobe'):
            print("MediaFiles.NeedsReprobe already exists -- skipping")
        else:
            print("Adding MediaFiles.NeedsReprobe BOOLEAN NOT NULL DEFAULT FALSE...")
            Cur.execute("ALTER TABLE MediaFiles ADD COLUMN NeedsReprobe BOOLEAN NOT NULL DEFAULT FALSE")
            Conn.commit()
            print("  done.")

        if IndexExists(Cur, 'idx_mediafiles_needs_reprobe'):
            print("Index idx_mediafiles_needs_reprobe already exists -- skipping")
        else:
            print("Creating partial index idx_mediafiles_needs_reprobe...")
            Cur.execute(
                "CREATE INDEX idx_mediafiles_needs_reprobe ON MediaFiles (Id) WHERE NeedsReprobe = TRUE"
            )
            Conn.commit()
            print("  done.")

        Cur.execute("SELECT COUNT(*) FROM MediaFiles WHERE NeedsReprobe = TRUE")
        print(f"\nMediaFiles flagged for reprobe: {Cur.fetchone()[0]}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
