#!/usr/bin/env python3
"""
AddSeriesProfilesAssignedProfile.py
Migration: add AssignedProfile VARCHAR(100) column to SeriesProfiles.

Owns: transcode-vs-remux-routing.feature.md criterion 2.

NULL means "inherit from SystemSettings.DefaultProfileName". Per-show
overrides set this to a specific profile name from Profiles.ProfileName.

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
        if ColumnExists(Cur, 'SeriesProfiles', 'AssignedProfile'):
            print("SeriesProfiles.AssignedProfile already exists -- skipping ADD COLUMN")
        else:
            print("Adding SeriesProfiles.AssignedProfile VARCHAR(100) (nullable)...")
            Cur.execute("ALTER TABLE SeriesProfiles ADD COLUMN AssignedProfile VARCHAR(100)")
            Conn.commit()
            print("  done.")
        Cur.execute("SELECT COUNT(*) FROM SeriesProfiles")
        Total = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM SeriesProfiles WHERE AssignedProfile IS NOT NULL")
        Set_ = Cur.fetchone()[0]
        print(f"\nShowSettings total rows: {Total}")
        print(f"  AssignedProfile set: {Set_}")
        print(f"  AssignedProfile NULL (inherits default): {Total - Set_}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
