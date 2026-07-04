#!/usr/bin/env python3
"""Fold NoReplace + Discard into Reject; enum becomes {Pending, Replace, Reject, Requeue}. See directive transcode-flow-canonical C6."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


NEW_CONSTRAINT = 'transcodeattempts_disposition_enum'
BACKUP_CONSTRAINT = 'transcodeattempts_disposition_enum_bak_2026_07_03_fold'


# directive: transcode-flow-canonical | # see transcode.ST7
def ConstraintExists(Db: DatabaseService, ConstraintName: str) -> bool:
    """True if a pg_constraint row named ConstraintName exists (lowercased)."""
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        (ConstraintName.lower(),),
    )
    return bool(Rows)


# directive: transcode-flow-canonical | # see transcode.ST7
def RewriteRows(Db: DatabaseService) -> None:
    """Rewrite historical NoReplace + Discard rows to Reject; DispositionReason preserved for audit."""
    for OldValue in ('NoReplace', 'Discard'):
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE Disposition = %s",
            (OldValue,),
        )
        Count = int(Rows[0]['n'])
        if Count == 0:
            print(f"No pre-fold {OldValue} rows found; skipping rewrite")
            continue
        print(f"Rewriting {Count} pre-fold {OldValue} rows -> Reject (DispositionReason preserved)")
        Affected = Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET Disposition = 'Reject' WHERE Disposition = %s",
            (OldValue,),
        )
        print(f"  updated: {Affected}")


# directive: transcode-flow-canonical | # see transcode.ST7
def SwapConstraint(Db: DatabaseService) -> None:
    """Rename existing enum constraint to backup, rewrite legacy rows, install tightened enum, drop backup."""
    if ConstraintExists(Db, NEW_CONSTRAINT):
        print(f"Existing constraint '{NEW_CONSTRAINT}' found; renaming to backup")
        Db.ExecuteNonQuery(
            f"ALTER TABLE TranscodeAttempts RENAME CONSTRAINT {NEW_CONSTRAINT} TO {BACKUP_CONSTRAINT}"
        )
    RewriteRows(Db)
    print(f"Adding tightened CHECK constraint '{NEW_CONSTRAINT}' (Pending, Replace, Reject, Requeue)")
    Db.ExecuteNonQuery(
        f"ALTER TABLE TranscodeAttempts "
        f"ADD CONSTRAINT {NEW_CONSTRAINT} "
        f"CHECK (Disposition IS NULL OR Disposition IN "
        f"('Pending','Replace','Reject','Requeue'))"
    )
    if ConstraintExists(Db, BACKUP_CONSTRAINT):
        print(f"Dropping backup constraint '{BACKUP_CONSTRAINT}'")
        Db.ExecuteNonQuery(f"ALTER TABLE TranscodeAttempts DROP CONSTRAINT {BACKUP_CONSTRAINT}")


# directive: transcode-flow-canonical | # see transcode.ST7
def Summary(Db: DatabaseService) -> None:
    """Print post-migration invariants for operator verification."""
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE Disposition IN ('NoReplace','Discard')"
    )
    print(f"  Rows with Disposition IN ('NoReplace','Discard'): {Rows[0]['n']} (expected 0)")
    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT Disposition FROM TranscodeAttempts WHERE Disposition IS NOT NULL ORDER BY 1"
    )
    Values = [Row['disposition'] for Row in Rows]
    print(f"  Distinct Disposition values: {Values}")


# directive: transcode-flow-canonical | # see transcode.ST7
def RunMigration() -> None:
    """Entry point."""
    Db = DatabaseService()
    SwapConstraint(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
