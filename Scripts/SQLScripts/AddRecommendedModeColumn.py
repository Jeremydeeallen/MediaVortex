#!/usr/bin/env python3
"""
AddRecommendedModeColumn.py
Migration: add RecommendedMode VARCHAR(16) column to MediaFiles.

Owns: transcode-vs-remux-routing.feature.md (declared in Files table).

Values: NULL (no decision), 'Transcode', 'Remux'. Future-extensible to
'Skip' or 'AudioNormalize' if those become distinct from 'Remux'.

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
        if ColumnExists(Cur, 'MediaFiles', 'RecommendedMode'):
            print("MediaFiles.RecommendedMode already exists -- skipping ADD COLUMN")
        else:
            print("Adding MediaFiles.RecommendedMode VARCHAR(16) (nullable)...")
            Cur.execute("ALTER TABLE MediaFiles ADD COLUMN RecommendedMode VARCHAR(16)")
            Conn.commit()
            print("  done.")
        Cur.execute(
            """
            SELECT COALESCE(RecommendedMode, '<NULL>') AS Mode, COUNT(*) AS Cnt
            FROM MediaFiles GROUP BY 1 ORDER BY 2 DESC
            """
        )
        for Mode, Cnt in Cur.fetchall():
            print(f"  RecommendedMode={Mode}: {Cnt}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
