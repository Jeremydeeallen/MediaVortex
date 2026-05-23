#!/usr/bin/env python3
"""
AddAudioNormalizationMode.py
Adds MediaFiles.AudioNormalizationMode for linear-loudnorm.feature.md.

Owns: linear-loudnorm.feature.md criterion 1b.

Records the loudnorm mode chosen at encode time per file:
  - 'linear'   -- fixed-gain pass; dynamics preserved
  - 'dynamic'  -- range-compression pass; used when fixed gain would
                  push peaks above the TP ceiling
  - NULL       -- file has not been re-encoded under linear-loudnorm yet

Surfaced on the Activity panel so the operator can see how often the
ungainable-peak path is firing. Populated by the post-flight hook in
FileReplacementBusinessService in the same transaction as
MarkAudioComplete.

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
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioNormalizationMode', 'VARCHAR(16)')
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
