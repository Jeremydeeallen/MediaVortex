#!/usr/bin/env python3
"""Retire the 'BypassReplace' Disposition enum value. See directive transcode-flow-canonical C6."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


NEW_CONSTRAINT = 'transcodeattempts_disposition_enum'
BACKUP_CONSTRAINT = 'transcodeattempts_disposition_enum_bak_2026_07_03'


# directive: transcode-flow-canonical | # see transcode.ST7
def ConstraintExists(Db: DatabaseService, ConstraintName: str) -> bool:
    """True if a pg_constraint row named ConstraintName exists (lowercased)."""
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        (ConstraintName.lower(),),
    )
    return bool(Rows)


# directive: transcode-flow-canonical | # see transcode.ST7
def RewriteBypassReplaceRows(Db: DatabaseService) -> None:
    """Convert pre-cutover BypassReplace rows to Replace; DispositionReason carries the audit context."""
    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE Disposition = 'BypassReplace'")
    Count = int(Rows[0]['n'])
    if Count == 0:
        print("No pre-cutover BypassReplace rows found; skipping rewrite")
        return
    print(f"Rewriting {Count} pre-cutover BypassReplace rows -> Replace (DispositionReason preserved for audit)")
    Affected = Db.ExecuteNonQuery(
        "UPDATE TranscodeAttempts SET Disposition = 'Replace' WHERE Disposition = 'BypassReplace'"
    )
    print(f"  updated: {Affected}")


# directive: transcode-flow-canonical | # see transcode.ST7
def SwapConstraint(Db: DatabaseService) -> None:
    """Rename existing enum constraint to backup, rewrite legacy rows, install new enum, drop backup."""
    if ConstraintExists(Db, NEW_CONSTRAINT):
        print(f"Existing constraint '{NEW_CONSTRAINT}' found; renaming to backup")
        Db.ExecuteNonQuery(
            f"ALTER TABLE TranscodeAttempts RENAME CONSTRAINT {NEW_CONSTRAINT} TO {BACKUP_CONSTRAINT}"
        )
    RewriteBypassReplaceRows(Db)
    print(f"Adding new CHECK constraint '{NEW_CONSTRAINT}' (Reject in; BypassReplace out)")
    Db.ExecuteNonQuery(
        f"ALTER TABLE TranscodeAttempts "
        f"ADD CONSTRAINT {NEW_CONSTRAINT} "
        f"CHECK (Disposition IS NULL OR Disposition IN "
        f"('Pending','Replace','Reject','NoReplace','Requeue','Discard'))"
    )
    if ConstraintExists(Db, BACKUP_CONSTRAINT):
        print(f"Dropping backup constraint '{BACKUP_CONSTRAINT}'")
        Db.ExecuteNonQuery(f"ALTER TABLE TranscodeAttempts DROP CONSTRAINT {BACKUP_CONSTRAINT}")


# directive: transcode-flow-canonical | # see transcode.ST7
def Summary(Db: DatabaseService) -> None:
    """Print post-migration invariants for operator verification."""
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE Disposition = 'BypassReplace'"
    )
    print(f"  Rows with Disposition='BypassReplace': {Rows[0]['n']} (expected 0)")
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
