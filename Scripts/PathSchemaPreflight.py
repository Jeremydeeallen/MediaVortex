import sys
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parents[1]))

from Core.Database.DatabaseService import DatabaseService


# directive: path-schema-migration | # see path.S8
PAIRS = [
    ("MediaFiles", "StorageRootId", "RelativePath", "FilePath", True),
    ("MediaFilesArchive", "StorageRootId", "RelativePath", "FilePath", False),
    ("TranscodeQueue", "StorageRootId", "RelativePath", "FilePath", True),
    ("TranscodeAttempts", "StorageRootId", "RelativePath", "FilePath", True),
]


# directive: path-schema-migration | # see path.S8
def _ColumnExists(Db, Table: str, Column: str) -> bool:
    Row = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) AND LOWER(column_name) = LOWER(%s) LIMIT 1",
        (Table, Column),
    )
    return bool(Row)


# directive: path-schema-migration | # see path.S8
def _CountUnfilledPair(Db, Table: str, SidCol: str, RelCol: str, LegacyCol: str) -> int:
    """Rows where the legacy column is populated but typed pair is missing -- blockers."""
    Sql = (
        f"SELECT COUNT(*) AS C FROM {Table} "
        f"WHERE {LegacyCol} IS NOT NULL "
        f"  AND ({SidCol} IS NULL OR {RelCol} IS NULL)"
    )
    Row = Db.ExecuteQuery(Sql)
    return int(Row[0]["c"] if "c" in Row[0] else Row[0].get("C", 0))


# directive: path-schema-migration | # see path.S8
def _CountTempFilePathsLegacyButNoTypedPair(Db) -> int:
    """TemporaryFilePaths rows with legacy source/output paths populated but typed pair missing."""
    LegacyColsPresent = all(
        _ColumnExists(Db, "TemporaryFilePaths", C)
        for C in ("OriginalPath", "LocalSourcePath")
    )
    if not LegacyColsPresent:
        return 0
    if not _ColumnExists(Db, "TemporaryFilePaths", "SourceStorageRootId"):
        return -1
    Row = Db.ExecuteQuery(
        "SELECT COUNT(*) AS C FROM TemporaryFilePaths "
        "WHERE (OriginalPath IS NOT NULL OR LocalSourcePath IS NOT NULL) "
        "  AND (SourceStorageRootId IS NULL OR SourceRelativePath IS NULL)"
    )
    return int(Row[0]["c"] if "c" in Row[0] else Row[0].get("C", 0))


# directive: path-schema-migration | # see path.S8
def Run() -> int:
    """Validate that every row's typed pair is populated before column drops. Exit 1 on blockers."""
    Db = DatabaseService()
    print("=== PathSchemaPreflight 2026-06-04 ===")
    Blockers = 0
    for Table, SidCol, RelCol, LegacyCol, Strict in PAIRS:
        LegacyPresent = _ColumnExists(Db, Table, LegacyCol)
        SidPresent = _ColumnExists(Db, Table, SidCol)
        RelPresent = _ColumnExists(Db, Table, RelCol)
        if not LegacyPresent:
            print(f"  {Table}.{LegacyCol}: column already absent -- skip")
            continue
        if not (SidPresent and RelPresent):
            print(f"  {Table}: BLOCKER -- typed-pair columns missing")
            Blockers += 1
            continue
        Unfilled = _CountUnfilledPair(Db, Table, SidCol, RelCol, LegacyCol)
        Tag = "BLOCKER" if (Strict and Unfilled > 0) else ("non-strict warn" if Unfilled > 0 else "clean")
        print(f"  {Table}: unfilled rows = {Unfilled} ({Tag})")
        if Strict and Unfilled > 0:
            Blockers += 1
    TempUnfilled = _CountTempFilePathsLegacyButNoTypedPair(Db)
    if TempUnfilled < 0:
        print("  TemporaryFilePaths: typed-pair columns missing -- BLOCKER")
        Blockers += 1
    elif TempUnfilled > 0:
        print(f"  TemporaryFilePaths: rows with legacy paths but no typed pair = {TempUnfilled} (non-strict warn -- pending in-flight jobs)")
    else:
        print("  TemporaryFilePaths: clean")
    if Blockers:
        print(f"FAIL: {Blockers} blocker(s). Backfill before migrating.")
        return 1
    print("PASS: preflight clear. Safe to run PathSchemaMigration_2026_06_04.py.")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
