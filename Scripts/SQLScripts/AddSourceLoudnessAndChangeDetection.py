#!/usr/bin/env python3
"""
AddSourceLoudnessAndChangeDetection.py
Phase 1 migration for media-tabs-and-loudness.feature.md.

Adds six nullable columns to MediaFiles:
  - SourceIntegratedLufs FLOAT      -- EBU R128 integrated loudness (LUFS).
                                       Distance from -23 LUFS predicts whether
                                       this file will make the operator reach
                                       for the TV remote.
  - SourceLoudnessRangeLU FLOAT     -- EBU R128 loudness range (LU). > 18 LU =
                                       theatrical wide-dynamics; compressor will
                                       hit hard.
  - SourceTruePeakDbtp FLOAT        -- EBU R128 true peak (dBTP). Anything > 0
                                       will clip on some DACs.
  - LoudnessMeasuredAt TIMESTAMP    -- When the three measurements were captured
                                       (or last attempted). NULL = never tried;
                                       non-NULL + NULL measurements = tried and
                                       failed.
  - LastProbedFileSize BIGINT       -- File size at last successful probe.
                                       Combined with mtime, enables short-circuit
                                       skip on unchanged files during reprobe.
  - LastProbedFileMtime TIMESTAMP   -- File mtime at last successful probe.

Plus one partial index that makes the backfill driver query sub-millisecond:
  idx_mediafiles_loudness_unmeasured ON MediaFiles (Id)
    WHERE SourceIntegratedLufs IS NULL AND AudioCorruptSuspect = FALSE

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
    Cursor.execute(
        """
        SELECT indexname FROM pg_indexes WHERE indexname = %s
        """,
        (IndexName.lower(),),
    )
    return Cursor.fetchone() is not None


def AddColumn(Cursor, Conn, TableName, ColumnName, ColumnDef):
    if ColumnExists(Cursor, TableName, ColumnName):
        print(f"{TableName}.{ColumnName} already exists -- skipping")
        return
    print(f"Adding {TableName}.{ColumnName} {ColumnDef}...")
    Cursor.execute(f"ALTER TABLE {TableName} ADD COLUMN {ColumnName} {ColumnDef}")
    Conn.commit()
    print("  done.")


def CreatePartialIndex(Cursor, Conn):
    IndexName = 'idx_mediafiles_loudness_unmeasured'
    if IndexExists(Cursor, IndexName):
        print(f"Index {IndexName} already exists -- skipping")
        return
    print(f"Creating partial index {IndexName}...")
    Cursor.execute(
        f"""
        CREATE INDEX {IndexName}
        ON MediaFiles (Id)
        WHERE SourceIntegratedLufs IS NULL
          AND AudioCorruptSuspect = FALSE
        """
    )
    Conn.commit()
    print("  done.")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'MediaFiles', 'SourceIntegratedLufs', 'FLOAT')
        AddColumn(Cur, Conn, 'MediaFiles', 'SourceLoudnessRangeLU', 'FLOAT')
        AddColumn(Cur, Conn, 'MediaFiles', 'SourceTruePeakDbtp', 'FLOAT')
        AddColumn(Cur, Conn, 'MediaFiles', 'LoudnessMeasuredAt', 'TIMESTAMP')
        AddColumn(Cur, Conn, 'MediaFiles', 'LastProbedFileSize', 'BIGINT')
        AddColumn(Cur, Conn, 'MediaFiles', 'LastProbedFileMtime', 'TIMESTAMP')

        CreatePartialIndex(Cur, Conn)

        Cur.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN SourceIntegratedLufs IS NOT NULL THEN 1 ELSE 0 END) AS measured,
                   SUM(CASE WHEN LoudnessMeasuredAt IS NOT NULL AND SourceIntegratedLufs IS NULL THEN 1 ELSE 0 END) AS tried_failed,
                   SUM(CASE WHEN LoudnessMeasuredAt IS NULL AND AudioCorruptSuspect = FALSE THEN 1 ELSE 0 END) AS unmeasured_eligible
            FROM MediaFiles
            """
        )
        Total, Measured, TriedFailed, UnmeasuredEligible = Cur.fetchone()
        print()
        print(f"MediaFiles total rows:           {Total}")
        print(f"  SourceIntegratedLufs measured: {Measured}")
        print(f"  Tried + failed (NULL values):  {TriedFailed}")
        print(f"  Unmeasured + eligible:         {UnmeasuredEligible}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
