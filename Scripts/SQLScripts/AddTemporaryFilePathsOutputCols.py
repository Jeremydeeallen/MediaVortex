"""Extends Phase 1: TemporaryFilePaths needs a SECOND (StorageRootId,
RelativePath) pair to represent the OUTPUT side, not just source.

Rename:
  StorageRootId -> SourceStorageRootId
  RelativePath  -> SourceRelativePath

Add:
  OutputStorageRootId BIGINT REFERENCES StorageRoots(Id)
  OutputRelativePath  TEXT

Then backfill OutputStorageRootId+OutputRelativePath by parsing existing
LocalOutputPath against StorageRoots prefixes. Wonky legacy staging-path
values (`\\staging\\<worker>\\T:\\Show\\<filename>`) won't match -- those
land as NULL orphans. Operator review before Phase 5 cleanup.

For ALL OTHER path-bearing tables, the single (StorageRootId, RelativePath)
pair from Phase 1 is sufficient -- those tables represent one file each.
TemporaryFilePaths is the only one that needs two pairs because it
carries both source and output for a TranscodeAttempt.

Idempotent.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService
from Core.PathStorage import Parse, LoadStorageRoots


def ColumnExists(Cur, Table, Col):
    Cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s AND table_schema = current_schema()",
        (Table.lower(), Col.lower()),
    )
    return Cur.fetchone() is not None


def Main():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        # Rename source columns if not already done
        if ColumnExists(Cur, 'TemporaryFilePaths', 'StorageRootId') and not ColumnExists(Cur, 'TemporaryFilePaths', 'SourceStorageRootId'):
            print("  RENAME TemporaryFilePaths.StorageRootId -> SourceStorageRootId")
            Cur.execute("ALTER TABLE TemporaryFilePaths RENAME COLUMN StorageRootId TO SourceStorageRootId")
            Conn.commit()
        else:
            print("  EXISTS  TemporaryFilePaths.SourceStorageRootId (or no rename needed)")

        if ColumnExists(Cur, 'TemporaryFilePaths', 'RelativePath') and not ColumnExists(Cur, 'TemporaryFilePaths', 'SourceRelativePath'):
            print("  RENAME TemporaryFilePaths.RelativePath -> SourceRelativePath")
            Cur.execute("ALTER TABLE TemporaryFilePaths RENAME COLUMN RelativePath TO SourceRelativePath")
            Conn.commit()
        else:
            print("  EXISTS  TemporaryFilePaths.SourceRelativePath (or no rename needed)")

        # Add output columns
        if not ColumnExists(Cur, 'TemporaryFilePaths', 'OutputStorageRootId'):
            print("  ADD     TemporaryFilePaths.OutputStorageRootId")
            Cur.execute("ALTER TABLE TemporaryFilePaths ADD COLUMN OutputStorageRootId BIGINT REFERENCES StorageRoots(Id)")
            Conn.commit()
        else:
            print("  EXISTS  TemporaryFilePaths.OutputStorageRootId")

        if not ColumnExists(Cur, 'TemporaryFilePaths', 'OutputRelativePath'):
            print("  ADD     TemporaryFilePaths.OutputRelativePath")
            Cur.execute("ALTER TABLE TemporaryFilePaths ADD COLUMN OutputRelativePath TEXT")
            Conn.commit()
        else:
            print("  EXISTS  TemporaryFilePaths.OutputRelativePath")

        # Backfill OutputStorageRootId+OutputRelativePath from LocalOutputPath
        # using normal Parse(). Wonky staging paths will end up NULL.
        StorageRoots = LoadStorageRoots(Db)
        Cur.execute(
            "SELECT Id, LocalOutputPath FROM TemporaryFilePaths WHERE OutputStorageRootId IS NULL AND LocalOutputPath IS NOT NULL"
        )
        Rows = Cur.fetchall()
        print(f"\nBackfilling Output columns for {len(Rows)} TemporaryFilePaths rows...")
        Matched = 0
        Orphan = 0
        Samples = []
        for RowId, LocalOutputPath in Rows:
            SrId, Rel = Parse(LocalOutputPath, StorageRoots)
            if SrId is None:
                Orphan += 1
                if len(Samples) < 5:
                    Samples.append((RowId, LocalOutputPath))
                continue
            Cur.execute(
                "UPDATE TemporaryFilePaths SET OutputStorageRootId = %s, OutputRelativePath = %s WHERE Id = %s",
                (SrId, Rel, RowId),
            )
            Matched += 1
        Conn.commit()
        print(f"  matched={Matched}  orphans={Orphan}")
        if Samples:
            print("\n  Orphan output-path samples (legacy staging paths, will not be resolvable):")
            for Pk, Path_ in Samples:
                print(f"    {Pk}  {Path_!r}")
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    Main()
