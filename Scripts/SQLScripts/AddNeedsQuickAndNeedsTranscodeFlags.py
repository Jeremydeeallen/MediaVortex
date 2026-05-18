#!/usr/bin/env python3
"""
AddNeedsQuickAndNeedsTranscodeFlags.py
Phase 2.11 migration for media-tabs-and-loudness.feature.md (criteria 15-19, revised).

Replaces the mutually-exclusive RecommendedMode trichotomy
(Transcode/Remux/AudioFix) with two independent eligibility flags so a single
file can appear in BOTH the Quick Fix tab AND the Transcode tab when both
operations apply.

Adds:
  - MediaFiles.NeedsQuick BOOLEAN NOT NULL DEFAULT FALSE
    True when AudioComplete=false OR container is not MP4-family.
    Drives the Quick Fix tab population.
  - MediaFiles.NeedsTranscode BOOLEAN NOT NULL DEFAULT FALSE
    True when video codec wrong, downscale needed, or savings >= threshold
    (subject to bitrate-floor short-circuit).
    Drives the Transcode tab population.

Plus two partial indexes for sub-millisecond tab queries:
  idx_mediafiles_needs_quick      ON MediaFiles (PriorityScore DESC, Id) WHERE NeedsQuick = TRUE
  idx_mediafiles_needs_transcode  ON MediaFiles (PriorityScore DESC, Id) WHERE NeedsTranscode = TRUE

RecommendedMode is retained as a single "primary" mode for badge/display
purposes (set to 'Transcode' when NeedsTranscode, else 'Quick' when NeedsQuick).

Idempotent.
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
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def IndexExists(Cursor, IndexName):
    Cursor.execute("SELECT indexname FROM pg_indexes WHERE indexname = %s", (IndexName.lower(),))
    return Cursor.fetchone() is not None


def AddColumn(Cur, Conn, Tbl, Col, Def):
    if ColumnExists(Cur, Tbl, Col):
        print(f"{Tbl}.{Col} already exists -- skipping")
        return
    print(f"Adding {Tbl}.{Col} {Def}...")
    Cur.execute(f"ALTER TABLE {Tbl} ADD COLUMN {Col} {Def}")
    Conn.commit()
    print("  done.")


def AddIndex(Cur, Conn, Name, Sql):
    if IndexExists(Cur, Name):
        print(f"Index {Name} already exists -- skipping")
        return
    print(f"Creating index {Name}...")
    Cur.execute(Sql)
    Conn.commit()
    print("  done.")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'MediaFiles', 'NeedsQuick', 'BOOLEAN NOT NULL DEFAULT FALSE')
        AddColumn(Cur, Conn, 'MediaFiles', 'NeedsTranscode', 'BOOLEAN NOT NULL DEFAULT FALSE')

        AddIndex(Cur, Conn, 'idx_mediafiles_needs_quick',
                 "CREATE INDEX idx_mediafiles_needs_quick ON MediaFiles (PriorityScore DESC, Id) WHERE NeedsQuick = TRUE")
        AddIndex(Cur, Conn, 'idx_mediafiles_needs_transcode',
                 "CREATE INDEX idx_mediafiles_needs_transcode ON MediaFiles (PriorityScore DESC, Id) WHERE NeedsTranscode = TRUE")

        Cur.execute("""
            SELECT
              SUM(CASE WHEN NeedsQuick THEN 1 ELSE 0 END) AS quick,
              SUM(CASE WHEN NeedsTranscode THEN 1 ELSE 0 END) AS xc,
              SUM(CASE WHEN NeedsQuick AND NeedsTranscode THEN 1 ELSE 0 END) AS both
            FROM MediaFiles
        """)
        Q, X, B = Cur.fetchone()
        print(f"\nMediaFiles: NeedsQuick={Q}  NeedsTranscode={X}  Both={B}")
        print("(All zero until RecomputeForFiles runs -- the cascade sets these.)")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
