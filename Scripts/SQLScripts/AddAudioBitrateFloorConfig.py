#!/usr/bin/env python3
"""
AddAudioBitrateFloorConfig.py
Migration: per-channel-count audio bitrate floor on QueueAdmissionConfig.

Owns: audio-completion.feature.md criterion 5.

Adds three INT columns to the single-row QueueAdmissionConfig table:
  - MinAudioBitrateKbpsMono     DEFAULT 64
  - MinAudioBitrateKbpsStereo   DEFAULT 96
  - MinAudioBitrateKbpsSurround DEFAULT 128 (3+ channels)

Files with AudioBitrateKbps at or below the floor for their channel count
are marked AudioComplete=true with reason 'below_bitrate_floor' so they
never run through the loudnorm/acompressor chain (a second generation
pass would damage already-low-bitrate sources).

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
        AddColumn(Cur, Conn, 'QueueAdmissionConfig', 'MinAudioBitrateKbpsMono',
                  'INTEGER NOT NULL DEFAULT 64')
        AddColumn(Cur, Conn, 'QueueAdmissionConfig', 'MinAudioBitrateKbpsStereo',
                  'INTEGER NOT NULL DEFAULT 96')
        AddColumn(Cur, Conn, 'QueueAdmissionConfig', 'MinAudioBitrateKbpsSurround',
                  'INTEGER NOT NULL DEFAULT 128')

        Cur.execute(
            "SELECT MinAudioBitrateKbpsMono, MinAudioBitrateKbpsStereo, "
            "MinAudioBitrateKbpsSurround FROM QueueAdmissionConfig WHERE Id=1"
        )
        Row = Cur.fetchone()
        if Row:
            print(f"\nQueueAdmissionConfig row: mono={Row[0]}, stereo={Row[1]}, surround={Row[2]}")
        else:
            print("\nWARNING: QueueAdmissionConfig row Id=1 missing -- "
                  "run AddQueueAdmissionTables.py first")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
