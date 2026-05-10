#!/usr/bin/env python3
"""
AddScanAffinityColumns.py
Migration: scan host-affinity + move-detection configurability.

Owns: FileScanning.feature.md criteria 11 and 12.

Adds:
  - RootFolders.PreferredWorkerName text NULL
        NULL = any ScanEnabled worker may scan this rootfolder.
        Set = only the named worker may scan this rootfolder.
  - ScanJobs.WorkerName text NULL
        Records which worker performed the scan, for observability.
  - SystemSettings('MoveDetectionMaxFiles', '100000', 'integer')
        Replaces the hardcoded 10000 in DetectMovedFiles. Default 100000.

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


def SettingExists(Cursor, SettingKey):
    Cursor.execute(
        "SELECT 1 FROM SystemSettings WHERE SettingKey = %s",
        (SettingKey,),
    )
    return Cursor.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if ColumnExists(Cur, 'RootFolders', 'PreferredWorkerName'):
            print("RootFolders.PreferredWorkerName already exists -- skipping ADD COLUMN")
        else:
            print("Adding RootFolders.PreferredWorkerName text (nullable)...")
            Cur.execute("ALTER TABLE RootFolders ADD COLUMN PreferredWorkerName text")
            Conn.commit()
            print("  done.")

        if ColumnExists(Cur, 'ScanJobs', 'WorkerName'):
            print("ScanJobs.WorkerName already exists -- skipping ADD COLUMN")
        else:
            print("Adding ScanJobs.WorkerName text (nullable)...")
            Cur.execute("ALTER TABLE ScanJobs ADD COLUMN WorkerName text")
            Conn.commit()
            print("  done.")

        if SettingExists(Cur, 'MoveDetectionMaxFiles'):
            print("SystemSetting 'MoveDetectionMaxFiles' already exists -- skipping seed")
        else:
            print("Seeding SystemSetting MoveDetectionMaxFiles = 100000 ...")
            Cur.execute(
                """
                INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    'MoveDetectionMaxFiles',
                    '100000',
                    'Maximum MediaFiles row count below which DetectMovedFiles will run. Above this, move detection is skipped (renamed files become delete+create).',
                    'integer',
                ),
            )
            Conn.commit()
            print("  done.")

        Cur.execute("SELECT COUNT(*) FROM RootFolders")
        TotalRoot = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM RootFolders WHERE PreferredWorkerName IS NOT NULL")
        Pinned = Cur.fetchone()[0]
        print(f"\nRootFolders total rows: {TotalRoot}")
        print(f"  PreferredWorkerName set: {Pinned}")
        print(f"  PreferredWorkerName NULL (any worker): {TotalRoot - Pinned}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
