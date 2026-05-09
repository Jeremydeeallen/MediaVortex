#!/usr/bin/env python3
"""
DropCompliantFilesTable.py
Drop the legacy CompliantFiles table.

Owns: transcode-vs-remux-routing.feature.md criterion 23.

The CompliantFiles table was last written 2025-09-08 (verified via
MAX(DateAdded) on 2026-05-09); a code grep confirmed zero live readers.
Its replacement is the materialized MediaFiles.IsCompliant column.

Idempotent (`DROP TABLE IF EXISTS`). Logs row count before drop.
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


def TableExists(Cursor, TableName):
    Cursor.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if not TableExists(Cur, 'CompliantFiles'):
            print("CompliantFiles already gone -- nothing to drop")
            return
        Cur.execute("SELECT COUNT(*) FROM CompliantFiles")
        Cnt = Cur.fetchone()[0]
        Cur.execute("SELECT MAX(DateAdded)::date FROM CompliantFiles")
        Last = Cur.fetchone()[0]
        print(f"CompliantFiles has {Cnt} rows, last write {Last}.")
        print("Dropping CompliantFiles (replaced by MediaFiles.IsCompliant)...")
        Cur.execute("DROP TABLE IF EXISTS CompliantFiles CASCADE")
        Conn.commit()
        print("  done.")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
