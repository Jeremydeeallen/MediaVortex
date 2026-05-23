#!/usr/bin/env python3
"""
AddAdmissionDeferReason.py
Adds MediaFiles.AdmissionDeferReason + LoudnessMeasurementFailureReason for
linear-loudnorm.feature.md.

Owns: linear-loudnorm.feature.md criteria 2 and 2b.

AdmissionDeferReason names *why* the admission gate is holding a file
out of the queue. Two values today:
  - 'awaiting_loudness_measurement'  -- probe co-trigger has not run yet;
                                        will auto-clear
  - 'loudness_measurement_failed'    -- ebur128 ran and produced nothing
                                        usable; needs operator review

LoudnessMeasurementFailureReason persists the short failure code
returned by LoudnessAnalysisService.MeasureLoudness when the underlying
ffmpeg invocation cannot produce numbers ('ffmpeg_not_found', 'timeout',
'ffmpeg_exit_<N>', 'parse_failed', 'parse_incomplete', 'silent_stream').

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
        AddColumn(Cur, Conn, 'MediaFiles', 'AdmissionDeferReason', 'VARCHAR(64)')
        AddColumn(Cur, Conn, 'MediaFiles', 'LoudnessMeasurementFailureReason', 'VARCHAR(64)')
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
