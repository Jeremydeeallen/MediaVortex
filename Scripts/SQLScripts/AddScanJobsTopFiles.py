#!/usr/bin/env python3
"""
AddScanJobsTopFiles.py
Migration: SizeSurvey scan phase -- per-scan top-N largest files.

Owns: directive 2026-05-27 "scan -- largest files first" criteria 4, 5.

Adds (nullable, no defaults; legacy rows stay NULL):
  - ScanJobs.TopFiles jsonb
        JSON array of {path, sizeMB, modifiedAt} written once at SizeSurvey
        completion. Read by TeamStatusController._BuildActiveScans to surface
        the top-5 largest files inline under each /Activity scan row.

Seeds SystemSettings('SizeSurveyTopN', '100', 'integer') if absent.

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
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def SettingExists(Cursor, Key):
    Cursor.execute("SELECT 1 FROM SystemSettings WHERE SettingKey = %s", (Key,))
    return Cursor.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if ColumnExists(Cur, 'ScanJobs', 'TopFiles'):
            print("ScanJobs.TopFiles already exists -- skipping ADD COLUMN")
        else:
            print("Adding ScanJobs.TopFiles jsonb (nullable)...")
            Cur.execute("ALTER TABLE ScanJobs ADD COLUMN TopFiles jsonb")
            Conn.commit()
            print("  done.")

        if SettingExists(Cur, 'SizeSurveyTopN'):
            print("SystemSetting 'SizeSurveyTopN' already exists -- skipping seed")
        else:
            print("Seeding SystemSetting SizeSurveyTopN = 100 ...")
            Cur.execute(
                """
                INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    'SizeSurveyTopN',
                    '100',
                    'Top-N largest files surfaced by the SizeSurvey scan phase. Front-loads biggest savings opportunities on /Activity within ~30s of scan start. Soft cap 500.',
                    'integer',
                ),
            )
            Conn.commit()
            print("  done.")

        Cur.execute("SELECT COUNT(*) FROM ScanJobs WHERE TopFiles IS NOT NULL")
        WithTop = Cur.fetchone()[0]
        Cur.execute("SELECT SettingValue FROM SystemSettings WHERE SettingKey='SizeSurveyTopN'")
        TopN = Cur.fetchone()
        print(f"\nScanJobs with TopFiles populated: {WithTop}")
        print(f"SizeSurveyTopN setting: {TopN[0] if TopN else '(missing)'}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
