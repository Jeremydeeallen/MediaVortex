#!/usr/bin/env python3
"""
AddQualityTestEnabledGlobal.py
Migration: operator-facing master switch to globally bypass VMAF.

Owns: Features/QualityTesting/post-transcode-disposition.feature.md criterion 26.

Adds:
- PostTranscodeGateConfig.QualityTestEnabled BOOLEAN NOT NULL DEFAULT TRUE

When FALSE, PostTranscodeDispositionService._DecideFromInputs short-circuits
post-success transcodes to (BypassReplace, QualityTestingGloballyDisabled),
sending every successful transcode straight to FileReplacement. Read fresh per
disposition call -- no caching, mid-flight toggle is safe.

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
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def AddQualityTestEnabledColumn(Cursor):
    if ColumnExists(Cursor, 'PostTranscodeGateConfig', 'QualityTestEnabled'):
        print("PostTranscodeGateConfig.QualityTestEnabled already exists -- skipping")
        return False
    print("Adding PostTranscodeGateConfig.QualityTestEnabled (default TRUE) ...")
    Cursor.execute("""
        ALTER TABLE PostTranscodeGateConfig
        ADD COLUMN QualityTestEnabled BOOLEAN NOT NULL DEFAULT TRUE
    """)
    print("  column added.")
    return True


def Summary(Cursor):
    print("\n--- Summary ---")
    Cursor.execute("""
        SELECT QualityTestEnabled, VmafAutoReplaceMinThreshold,
               VmafAutoReplaceMaxThreshold, WhenVmafUnavailable
        FROM PostTranscodeGateConfig WHERE Id = 1
    """)
    Row = Cursor.fetchone()
    if Row:
        print(f"  Gate config: QualityTestEnabled={Row[0]}, Min={Row[1]}, "
              f"Max={Row[2]}, WhenVmafUnavailable='{Row[3]}'")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        AddQualityTestEnabledColumn(Cur)
        Conn.commit()
        Summary(Cur)
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
