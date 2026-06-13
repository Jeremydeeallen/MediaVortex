#!/usr/bin/env python3
"""
AddOrphanCleanupAndUniqueProgress.py
Migration: schema piece of stuck-item cleanup gaps.

Owns: Features/FileReplacement/post-transcode-pipeline.feature.md criterion 18.

Two changes:

1. Dedupe existing TranscodeProgress rows: when multiple rows exist for the same
   TranscodeAttemptId (no UNIQUE constraint historically, duplicates observed in
   prod), keep the most-recently-updated row and delete the rest.

2. Add UNIQUE constraint on TranscodeProgress.TranscodeAttemptId so duplicates
   are impossible at the schema level going forward.

Idempotent. Safe to run multiple times.

The recurring orphan-sweep code-side fix is in WorkerService/_OrphanCleanupLoop;
this migration is only the schema piece.
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


def ConstraintExists(Cursor, TableName, ConstraintName):
    Cursor.execute(
        """
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = %s AND constraint_name = %s
        """,
        (TableName.lower(), ConstraintName.lower()),
    )
    return Cursor.fetchone() is not None


def CountDuplicateProgressRows(Cursor):
    Cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT TranscodeAttemptId
            FROM TranscodeProgress
            GROUP BY TranscodeAttemptId
            HAVING COUNT(*) > 1
        ) Dupes
    """)
    return Cursor.fetchone()[0]


def DedupeTranscodeProgress(Cursor):
    DupeAttempts = CountDuplicateProgressRows(Cursor)
    if DupeAttempts == 0:
        print("No TranscodeProgress duplicates to remove -- skipping dedupe")
        return 0

    print(f"Found {DupeAttempts} TranscodeAttemptId values with duplicate TranscodeProgress rows")
    Cursor.execute("""
        DELETE FROM TranscodeProgress p
        USING (
            SELECT Id,
                   ROW_NUMBER() OVER (
                       PARTITION BY TranscodeAttemptId
                       ORDER BY COALESCE(LastFrameAdvance, TimeStamp, NOW()) DESC, Id DESC
                   ) AS Rn
            FROM TranscodeProgress
        ) Ranked
        WHERE p.Id = Ranked.Id AND Ranked.Rn > 1
    """)
    Removed = Cursor.rowcount
    print(f"  Removed {Removed} duplicate TranscodeProgress rows (kept latest per TranscodeAttemptId)")
    return Removed


def AddUniqueConstraint(Cursor):
    ConstraintName = 'transcodeprogress_attemptid_unique'
    if ConstraintExists(Cursor, 'TranscodeProgress', ConstraintName):
        print(f"Constraint '{ConstraintName}' already exists -- skipping ADD")
        return False

    print(f"Adding UNIQUE constraint '{ConstraintName}' on TranscodeProgress.TranscodeAttemptId ...")
    Cursor.execute(f"""
        ALTER TABLE TranscodeProgress
        ADD CONSTRAINT {ConstraintName}
        UNIQUE (TranscodeAttemptId)
    """)
    print("  constraint added.")
    return True


def Summary(Cursor):
    print("\n--- Summary ---")
    Remaining = CountDuplicateProgressRows(Cursor)
    print(f"  TranscodeAttemptIds with duplicate progress rows: {Remaining} (expected 0)")
    Cursor.execute("""
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'transcodeprogress'
          AND constraint_name = 'transcodeprogress_attemptid_unique'
    """)
    Present = Cursor.fetchone() is not None
    print(f"  UNIQUE constraint present: {Present}")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        DedupeTranscodeProgress(Cur)
        Conn.commit()

        AddUniqueConstraint(Cur)
        Conn.commit()

        Summary(Cur)
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
