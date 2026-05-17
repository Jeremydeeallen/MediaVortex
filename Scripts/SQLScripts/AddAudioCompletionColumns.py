#!/usr/bin/env python3
"""
AddAudioCompletionColumns.py
Migration: add per-file audio-completion state columns to MediaFiles.

Owns: audio-completion.feature.md criteria 1-4.

Adds:
  - AudioComplete BOOLEAN (NULL = not yet evaluated, true = stream-copy
    forever, false = eligible for one-shot normalize on next encode)
  - AudioCompletedAt TIMESTAMP (when AudioComplete transitioned to true)
  - AudioCorruptSuspect BOOLEAN DEFAULT FALSE (hard-block from queue)
  - AudioCorruptReason VARCHAR(64) (one of: 'no_audio_stream',
    'below_bitrate_floor', 'incompatible_codec_unsupported')

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


def AddColumn(Cursor, Conn, TableName, ColumnName, ColumnDef):
    if ColumnExists(Cursor, TableName, ColumnName):
        print(f"{TableName}.{ColumnName} already exists -- skipping")
        return
    print(f"Adding {TableName}.{ColumnName} {ColumnDef}...")
    Cursor.execute(f"ALTER TABLE {TableName} ADD COLUMN {ColumnName} {ColumnDef}")
    Conn.commit()
    print("  done.")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioComplete', 'BOOLEAN')
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioCompletedAt', 'TIMESTAMP')
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioCorruptSuspect',
                  'BOOLEAN NOT NULL DEFAULT FALSE')
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioCorruptReason', 'VARCHAR(64)')

        Cur.execute("SELECT COUNT(*) FROM MediaFiles")
        Total = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM MediaFiles WHERE AudioComplete IS NOT NULL")
        Eval_ = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM MediaFiles WHERE AudioCorruptSuspect = TRUE")
        Suspect = Cur.fetchone()[0]
        print(f"\nMediaFiles total rows: {Total}")
        print(f"  AudioComplete evaluated: {Eval_}")
        print(f"  AudioComplete NULL: {Total - Eval_}")
        print(f"  AudioCorruptSuspect TRUE: {Suspect}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
