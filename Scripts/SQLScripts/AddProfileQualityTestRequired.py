#!/usr/bin/env python3
"""AddProfileQualityTestRequired.py -- migration; see per-profile-vmaf-skip directive."""

import os
import psycopg2


# directive: per-profile-vmaf-skip
def GetConnection():
    """DB connection; see per-profile-vmaf-skip."""
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),  # allow: R4 migration bootstrap (matches sibling scripts AddAudioCompletionColumns.py etc.)
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),  # allow: R4 migration bootstrap
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),  # allow: R4 migration bootstrap
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),  # allow: R4 migration bootstrap
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),  # allow: R4 migration bootstrap
    )


# directive: per-profile-vmaf-skip
def ColumnExists(Cursor, TableName, ColumnName):
    """Check column presence; see per-profile-vmaf-skip."""
    Cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


# directive: per-profile-vmaf-skip
def Main():
    """Idempotent ADD COLUMN; see per-profile-vmaf-skip.C1, C2."""
    Conn = GetConnection()
    Cursor = Conn.cursor()
    try:
        if ColumnExists(Cursor, 'profiles', 'qualitytestrequired'):
            print("profiles.qualitytestrequired already exists -- skipping")
            return
        print("Adding profiles.qualitytestrequired BOOLEAN NOT NULL DEFAULT TRUE...")
        Cursor.execute(
            "ALTER TABLE profiles ADD COLUMN qualitytestrequired BOOLEAN NOT NULL DEFAULT TRUE"
        )
        Conn.commit()
        print("Done.")
    finally:
        Cursor.close()
        Conn.close()


if __name__ == '__main__':
    Main()
