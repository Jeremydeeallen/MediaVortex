#!/usr/bin/env python3
"""
AddPostTranscodeDisposition.py
Migration: unified data-driven post-transcode disposition.

Owns: Features/QualityTesting/post-transcode-disposition.feature.md criteria 6, 7, 8.

Three changes:

1. NEW table `PostTranscodeGateConfig` (single-row, Id=1 CHECK, typed columns):
   - VmafAutoReplaceMinThreshold NUMERIC NOT NULL DEFAULT 88
   - VmafAutoReplaceMaxThreshold NUMERIC NOT NULL DEFAULT 98
   - WhenVmafUnavailable TEXT NOT NULL DEFAULT 'block'   (block | bypass)

2. ADD COLUMNs to TranscodeAttempts (audit trail):
   - Disposition          TEXT NULL
       CHECK in ('Pending','Replace','BypassReplace','NoReplace','Requeue','Discard')
   - DispositionReason    TEXT NULL
   - DispositionDecidedAt TIMESTAMP NULL
   Plus an index on (Disposition, DispositionDecidedAt) for the audit query.

3. DELETE legacy SystemSettings rows (no backwards-compat shim):
   - VMAFAutoReplaceMinThreshold
   - VMAFAutoReplaceMaxThreshold
   - QualityTestEnabled  (global flag; per-worker capability + new gate config replace it)
   The legacy values are migrated into PostTranscodeGateConfig before deletion if
   they exist (preserves the operator's tuning across the cutover).

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


def TableExists(Cursor, TableName):
    Cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = %s AND table_schema = current_schema()
        """,
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def IndexExists(Cursor, IndexName):
    Cursor.execute(
        "SELECT 1 FROM pg_indexes WHERE indexname = %s",
        (IndexName.lower(),),
    )
    return Cursor.fetchone() is not None


def GetSystemSetting(Cursor, Key):
    Cursor.execute("SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s", (Key,))
    Row = Cursor.fetchone()
    return Row[0] if Row else None


def CreatePostTranscodeGateConfig(Cursor):
    if TableExists(Cursor, 'PostTranscodeGateConfig'):
        print("Table 'PostTranscodeGateConfig' already exists -- skipping CREATE")
        return False
    print("Creating PostTranscodeGateConfig (single-row scalar config) ...")
    Cursor.execute("""
        CREATE TABLE PostTranscodeGateConfig (
            Id INT PRIMARY KEY DEFAULT 1,
            VmafAutoReplaceMinThreshold NUMERIC NOT NULL DEFAULT 88,
            VmafAutoReplaceMaxThreshold NUMERIC NOT NULL DEFAULT 98,
            WhenVmafUnavailable TEXT NOT NULL DEFAULT 'block',
            QualityTestEnabled BOOLEAN NOT NULL DEFAULT TRUE,
            LastUpdated TIMESTAMP DEFAULT NOW(),
            CONSTRAINT posttranscodegateconfig_singlerow CHECK (Id = 1),
            CONSTRAINT posttranscodegateconfig_min_le_max
                CHECK (VmafAutoReplaceMinThreshold <= VmafAutoReplaceMaxThreshold),
            CONSTRAINT posttranscodegateconfig_unavail_enum
                CHECK (WhenVmafUnavailable IN ('block','bypass'))
        )
    """)
    print("  table created.")
    return True


def SeedPostTranscodeGateConfig(Cursor):
    """Insert the Id=1 row, migrating values from legacy SystemSettings if present."""
    Cursor.execute("SELECT 1 FROM PostTranscodeGateConfig WHERE Id = 1")
    if Cursor.fetchone() is not None:
        print("PostTranscodeGateConfig row already seeded -- skipping")
        return

    LegacyMin = GetSystemSetting(Cursor, 'VMAFAutoReplaceMinThreshold')
    LegacyMax = GetSystemSetting(Cursor, 'VMAFAutoReplaceMaxThreshold')

    try:
        SeedMin = float(LegacyMin) if LegacyMin is not None else 88.0
    except (TypeError, ValueError):
        SeedMin = 88.0
    try:
        SeedMax = float(LegacyMax) if LegacyMax is not None else 98.0
    except (TypeError, ValueError):
        SeedMax = 98.0

    print(f"Seeding PostTranscodeGateConfig (Id=1, Min={SeedMin}, Max={SeedMax}, WhenVmafUnavailable='block') ...")
    if LegacyMin is not None or LegacyMax is not None:
        print(f"  (carried over from legacy SystemSettings: Min={LegacyMin!r}, Max={LegacyMax!r})")

    Cursor.execute("""
        INSERT INTO PostTranscodeGateConfig
            (Id, VmafAutoReplaceMinThreshold, VmafAutoReplaceMaxThreshold, WhenVmafUnavailable)
        VALUES (1, %s, %s, 'block')
    """, (SeedMin, SeedMax))
    print("  seeded.")


def AddDispositionColumns(Cursor):
    Added = []
    if not ColumnExists(Cursor, 'TranscodeAttempts', 'Disposition'):
        print("Adding TranscodeAttempts.Disposition ...")
        Cursor.execute("""
            ALTER TABLE TranscodeAttempts
            ADD COLUMN Disposition TEXT NULL
            CONSTRAINT transcodeattempts_disposition_enum
                CHECK (Disposition IS NULL OR Disposition IN
                       ('Pending','Replace','BypassReplace','NoReplace','Requeue','Discard'))
        """)
        Added.append('Disposition')

    if not ColumnExists(Cursor, 'TranscodeAttempts', 'DispositionReason'):
        print("Adding TranscodeAttempts.DispositionReason ...")
        Cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN DispositionReason TEXT NULL")
        Added.append('DispositionReason')

    if not ColumnExists(Cursor, 'TranscodeAttempts', 'DispositionDecidedAt'):
        print("Adding TranscodeAttempts.DispositionDecidedAt ...")
        Cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN DispositionDecidedAt TIMESTAMP NULL")
        Added.append('DispositionDecidedAt')

    if not Added:
        print("All disposition columns already present -- skipping ADD COLUMN")

    if not IndexExists(Cursor, 'idx_transcodeattempts_disposition'):
        print("Creating index idx_transcodeattempts_disposition ...")
        Cursor.execute("""
            CREATE INDEX idx_transcodeattempts_disposition
            ON TranscodeAttempts (Disposition, DispositionDecidedAt)
        """)
    else:
        print("Index idx_transcodeattempts_disposition already exists -- skipping")


def DeleteLegacySystemSettings(Cursor):
    """Delete the three legacy KV rows once their values are safely migrated.

    Per criterion 8: VMAFAutoReplaceMinThreshold, VMAFAutoReplaceMaxThreshold,
    QualityTestEnabled. The first two were carried into PostTranscodeGateConfig
    above; QualityTestEnabled global was always shadowed by per-worker
    Workers.QualityTestEnabled and is now redundant.
    """
    LegacyKeys = ('VMAFAutoReplaceMinThreshold', 'VMAFAutoReplaceMaxThreshold', 'QualityTestEnabled')
    for Key in LegacyKeys:
        Cursor.execute("DELETE FROM SystemSettings WHERE SettingKey = %s", (Key,))
        if Cursor.rowcount:
            print(f"Deleted legacy SystemSettings row '{Key}'")
        else:
            print(f"Legacy SystemSettings row '{Key}' already absent")


def Summary(Cursor):
    print("\n--- Summary ---")
    Cursor.execute("SELECT COUNT(*) FROM PostTranscodeGateConfig")
    print(f"  PostTranscodeGateConfig rows: {Cursor.fetchone()[0]}")
    Cursor.execute("""
        SELECT VmafAutoReplaceMinThreshold, VmafAutoReplaceMaxThreshold, WhenVmafUnavailable
        FROM PostTranscodeGateConfig WHERE Id = 1
    """)
    Row = Cursor.fetchone()
    if Row:
        print(f"  Gate config: Min={Row[0]}, Max={Row[1]}, WhenVmafUnavailable='{Row[2]}'")
    Cursor.execute("""
        SELECT COUNT(*) FROM SystemSettings
        WHERE SettingKey IN ('VMAFAutoReplaceMinThreshold','VMAFAutoReplaceMaxThreshold','QualityTestEnabled')
    """)
    print(f"  Legacy SystemSettings KV rows remaining: {Cursor.fetchone()[0]} (expected 0)")
    Cursor.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'transcodeattempts'
          AND column_name IN ('disposition','dispositionreason','dispositiondecidedat')
    """)
    print(f"  TranscodeAttempts disposition columns present: {Cursor.fetchone()[0]} / 3")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        CreatePostTranscodeGateConfig(Cur)
        AddDispositionColumns(Cur)
        Conn.commit()

        SeedPostTranscodeGateConfig(Cur)
        DeleteLegacySystemSettings(Cur)
        Conn.commit()

        Summary(Cur)
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
