#!/usr/bin/env python3
"""
AddIsCompliantColumn.py
Migration: add IsCompliant BOOLEAN column to MediaFiles.

Owns: transcode-vs-remux-routing.feature.md criterion 10.

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
        if ColumnExists(Cur, 'MediaFiles', 'IsCompliant'):
            print("MediaFiles.IsCompliant already exists -- skipping ADD COLUMN")
        else:
            print("Adding MediaFiles.IsCompliant BOOLEAN (nullable)...")
            Cur.execute("ALTER TABLE MediaFiles ADD COLUMN IsCompliant BOOLEAN")
            Conn.commit()
            print("  done.")
        Cur.execute("SELECT COUNT(*) FROM MediaFiles")
        Total = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*) FROM MediaFiles WHERE IsCompliant IS NOT NULL")
        Eval_ = Cur.fetchone()[0]
        print(f"\nMediaFiles total rows: {Total}")
        print(f"  IsCompliant evaluated: {Eval_}")
        print(f"  IsCompliant NULL: {Total - Eval_}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
