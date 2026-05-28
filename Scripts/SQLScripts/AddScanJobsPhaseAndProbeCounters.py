#!/usr/bin/env python3
"""
AddScanJobsPhaseAndProbeCounters.py
Migration: scan-phase visibility + per-probe progress on ScanJobs.

Owns: directive 2026-05-27 criteria 12-14 (active-scan visibility on /Activity).

Adds (all nullable, no defaults so existing rows stay NULL):
  - ScanJobs.Phase text
        Producer writes one of: 'Walking' | 'Reconciling' | 'Probing' | 'Completing'.
        NULL on legacy rows and after Status flips to Completed.
        Free-text column (not enum) -- producer controls the value set; UI renders unknown values literally.
  - ScanJobs.FilesNeedingProbe integer
        Set at Probing-phase entry to the count of files queued for FFprobe+ebur128.
        Reused by the Activity-page progress bar during Probing.
  - ScanJobs.ProbedFiles integer
        Incremented inside the probe loop per completion.

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


def AddColumn(Cur, Conn, TableName, ColumnName, ColumnType):
    if ColumnExists(Cur, TableName, ColumnName):
        print(f"{TableName}.{ColumnName} already exists -- skipping ADD COLUMN")
        return
    print(f"Adding {TableName}.{ColumnName} {ColumnType} (nullable)...")
    Cur.execute(f"ALTER TABLE {TableName} ADD COLUMN {ColumnName} {ColumnType}")
    Conn.commit()
    print("  done.")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'ScanJobs', 'Phase', 'text')
        AddColumn(Cur, Conn, 'ScanJobs', 'FilesNeedingProbe', 'integer')
        AddColumn(Cur, Conn, 'ScanJobs', 'ProbedFiles', 'integer')

        Cur.execute("SELECT COUNT(*) FROM ScanJobs")
        Total = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM ScanJobs WHERE Phase IS NOT NULL")
        WithPhase = Cur.fetchone()[0]
        print(f"\nScanJobs total rows: {Total}")
        print(f"  Phase populated: {WithPhase}")
        print(f"  Phase NULL (legacy / completed / not yet written): {Total - WithPhase}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
