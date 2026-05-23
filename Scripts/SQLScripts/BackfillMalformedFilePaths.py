"""Backfill malformed MediaFiles.FilePath values produced by the BUG-0012 scanner
defect (doubled separator after share root). Runs every row through
Core.PathNormalize.NormalizeCanonical.

Two operations per malformed row:
  - If a clean-FilePath sibling already exists for the same file, the
    malformed row is DELETED (the clean one is the keeper). Aborts if
    the malformed row carries any FK references the clean one would lose.
  - Otherwise the row's FilePath is UPDATEd in place.

Idempotent.

Usage:
    py Scripts/SQLScripts/BackfillMalformedFilePaths.py [--dry-run]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Core.PathNormalize import NormalizeCanonical


BATCH_SIZE = 500


FK_TABLES = [
    ('TranscodeAttempts', 'MediaFileId'),
    ('TranscodeQueue',    'MediaFileId'),
    ('TranscodeFiles',    'MediaFileId'),
]


def _HasReferences(Db, RowId):
    for Table, Col in FK_TABLES:
        Rows = Db.ExecuteQuery(
            f"SELECT 1 FROM {Table} WHERE {Col} = %s LIMIT 1",
            (RowId,),
        )
        if Rows:
            return True
    return False


def Main():
    DryRun = '--dry-run' in sys.argv
    Db = DatabaseService()

    Total = Db.ExecuteQuery("SELECT COUNT(*) AS N FROM MediaFiles")[0]['N']
    print(f"MediaFiles total rows: {Total:,}")

    Offset = 0
    Inspected = 0
    Updated = 0
    Deleted = 0
    Skipped = 0
    while True:
        Rows = Db.ExecuteQuery(
            "SELECT Id, FilePath FROM MediaFiles ORDER BY Id LIMIT %s OFFSET %s",
            (BATCH_SIZE, Offset),
        )
        if not Rows:
            break

        for Row in Rows:
            Inspected += 1
            Current = Row.get('FilePath') or ''
            Normalized = NormalizeCanonical(Current)
            if Normalized == Current:
                continue

            Sibling = Db.ExecuteQuery(
                "SELECT Id FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s) AND Id <> %s LIMIT 1",
                (Normalized, Row['Id']),
            )
            if Sibling:
                if _HasReferences(Db, Row['Id']):
                    print(f"  [SKIP] Id={Row['Id']}: collides with Id={Sibling[0]['Id']} AND has FK refs -- manual merge needed")
                    Skipped += 1
                    continue
                if DryRun:
                    print(f"  [dry-run] Id={Row['Id']}: would DELETE (collides with clean Id={Sibling[0]['Id']})")
                else:
                    Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (Row['Id'],))
                Deleted += 1
            else:
                if DryRun:
                    if Updated < 5:
                        print(f"  [dry-run] Id={Row['Id']}: would UPDATE FilePath -> {Normalized!r}")
                else:
                    Db.ExecuteNonQuery(
                        "UPDATE MediaFiles SET FilePath = %s WHERE Id = %s",
                        (Normalized, Row['Id']),
                    )
                Updated += 1

        Offset += BATCH_SIZE
        if Inspected % 5000 == 0:
            print(f"  inspected {Inspected:,}/{Total:,}  updated {Updated:,}  deleted {Deleted:,}  skipped {Skipped:,}")

    Mode = "DRY-RUN" if DryRun else "APPLIED"
    print(f"\n[{Mode}] Inspected {Inspected:,}  updated {Updated:,}  deleted {Deleted:,}  skipped {Skipped:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
