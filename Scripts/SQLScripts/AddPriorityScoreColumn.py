#!/usr/bin/env python3
"""
AddPriorityScoreColumn.py
Migration: add PriorityScore INTEGER column to MediaFiles.

Owns: priority-materialization.feature.md criterion 1.

Safe to run multiple times (idempotent). Does not add an index --
the partial index used by SmartPopulate is owned by AddSmartPopulateIndex.py
under smart-populate.feature.md.
"""

import os
import sys
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex')
    )


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (TableName.lower(), ColumnName.lower()))
    return Cursor.fetchone() is not None


def RunMigration():
    Connection = GetConnection()
    Cursor = Connection.cursor()
    try:
        if ColumnExists(Cursor, 'MediaFiles', 'PriorityScore'):
            print("MediaFiles.PriorityScore already exists -- skipping ADD COLUMN")
        else:
            print("Adding MediaFiles.PriorityScore INTEGER (nullable)...")
            Cursor.execute("ALTER TABLE MediaFiles ADD COLUMN PriorityScore INTEGER")
            Connection.commit()
            print("  done.")

        Cursor.execute("SELECT COUNT(*) FROM MediaFiles")
        Total = Cursor.fetchone()[0]
        Cursor.execute("SELECT COUNT(*) FROM MediaFiles WHERE PriorityScore IS NULL")
        NullCount = Cursor.fetchone()[0]
        print(f"\nMediaFiles total rows: {Total}")
        print(f"  PriorityScore IS NULL: {NullCount}")
        print(f"  PriorityScore populated: {Total - NullCount}")
        if NullCount > 0:
            print("\nRun Scripts/SQLScripts/BackfillPriorityScores.py to populate the NULL rows.")
    finally:
        Cursor.close()
        Connection.close()


if __name__ == '__main__':
    RunMigration()
