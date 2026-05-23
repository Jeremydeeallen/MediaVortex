#!/usr/bin/env python3
"""
AddLoudnessThresholdColumn.py
Adds MediaFiles.SourceIntegratedThresholdLufs for linear-loudnorm.feature.md.

Owns: linear-loudnorm.feature.md criterion 1.

The relative gating threshold from EBU R128 is the fourth measurement
loudnorm's linear mode requires. We already capture I/LRA/TP; this
column completes the set.

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
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def AddColumn(Cursor, Conn, TableName, ColumnName, ColumnDef):
    if ColumnExists(Cursor, TableName, ColumnName):
        print(f"{TableName}.{ColumnName} already exists -- skipping")
        return
    print(f"Adding {TableName}.{ColumnName} {ColumnDef}...")
    Cursor.execute(f"ALTER TABLE {TableName} ADD COLUMN {ColumnName} {ColumnDef}")
    Conn.commit()
    print("  done.")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'MediaFiles', 'SourceIntegratedThresholdLufs', 'FLOAT')

        Cur.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN SourceIntegratedLufs IS NOT NULL
                            AND SourceIntegratedThresholdLufs IS NULL
                            THEN 1 ELSE 0 END) AS measured_but_no_threshold
            FROM MediaFiles
            """
        )
        Total, NeedsBackfill = Cur.fetchone()
        print()
        print(f"MediaFiles total rows:                            {Total}")
        print(f"  Have I/LRA/TP but missing Threshold (backfill): {NeedsBackfill}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
