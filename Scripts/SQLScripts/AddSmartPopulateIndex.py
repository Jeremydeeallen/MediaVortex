#!/usr/bin/env python3
"""
AddSmartPopulateIndex.py
Migration: add a partial index on MediaFiles to support SmartPopulate
WHERE+ORDER queries.

Owns: smart-populate.feature.md criterion 18.

Index shape:
    CREATE INDEX idx_mediafiles_smartpopulate ON MediaFiles
        (PriorityScore DESC NULLS LAST, SizeMB DESC)
        WHERE TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0

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
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex')
    )


def IndexExists(Cursor, IndexName):
    Cursor.execute("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = %s
    """, (IndexName.lower(),))
    return Cursor.fetchone() is not None


def RunMigration():
    Connection = GetConnection()
    Cursor = Connection.cursor()
    try:
        IndexName = 'idx_mediafiles_smartpopulate'
        if IndexExists(Cursor, IndexName):
            print(f"Index {IndexName} already exists -- skipping CREATE")
        else:
            print(f"Creating partial index {IndexName}...")
            # Cannot use CREATE INDEX CONCURRENTLY inside a transaction; use plain CREATE.
            Cursor.execute(f"""
                CREATE INDEX {IndexName}
                ON MediaFiles (PriorityScore DESC NULLS LAST, SizeMB DESC)
                WHERE TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0
            """)
            Connection.commit()
            print("  done.")

        # Show EXPLAIN ANALYZE for the SmartPopulate query shape.
        print("\nEXPLAIN ANALYZE for SmartPopulate (no Search):")
        Cursor.execute("""
            EXPLAIN ANALYZE
            SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
                   m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat,
                   m.PriorityScore
            FROM MediaFiles m
            WHERE TranscodedByMediaVortex IS NOT TRUE
              AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
              AND m.SizeMB > 0
            ORDER BY PriorityScore DESC NULLS LAST, SizeMB DESC
            LIMIT 100
        """)
        for Row in Cursor.fetchall():
            print(f"  {Row[0]}")
    finally:
        Cursor.close()
        Connection.close()


if __name__ == '__main__':
    RunMigration()
