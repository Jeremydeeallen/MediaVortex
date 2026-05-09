#!/usr/bin/env python3
"""
AddFFmpegPidColumn.py
Migration: add FFmpegPid BIGINT NULL column to ActiveJobs.

Owns: stuck-job-detection.feature.md criterion 5.

Stuck-detection cleanup must kill the FFmpeg child PID, not the worker
PID. The existing ActiveJobs.ProcessId field is documented (in
StuckJobDetectionService.IsProcessAlive) as the worker's Python PID.
This column tracks the FFmpeg subprocess PID separately so cleanup
targets the right process.

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


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if ColumnExists(Cur, 'ActiveJobs', 'FFmpegPid'):
            print("ActiveJobs.FFmpegPid already exists -- skipping ADD COLUMN")
        else:
            print("Adding ActiveJobs.FFmpegPid BIGINT (nullable)...")
            Cur.execute("ALTER TABLE ActiveJobs ADD COLUMN FFmpegPid BIGINT")
            Conn.commit()
            print("  done.")

        Cur.execute("SELECT COUNT(*) FROM ActiveJobs")
        Total = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM ActiveJobs WHERE FFmpegPid IS NOT NULL")
        Set_ = Cur.fetchone()[0]
        print(f"\nActiveJobs total rows: {Total}")
        print(f"  FFmpegPid populated: {Set_}")
        print(f"  FFmpegPid NULL: {Total - Set_}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
