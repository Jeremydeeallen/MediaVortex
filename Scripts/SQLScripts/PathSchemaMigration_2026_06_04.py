import sys
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: path-schema-migration | # see path.S8 -- each row: (Table, LegacyColumn); rename target is "_legacy_<col_lower>"
TARGETS = [
    ("MediaFiles", "FilePath"),
    ("MediaFilesArchive", "FilePath"),
    ("TranscodeQueue", "FilePath"),
    ("TranscodeAttempts", "FilePath"),
    ("TemporaryFilePaths", "OriginalPath"),
    ("TemporaryFilePaths", "LocalSourcePath"),
    ("TemporaryFilePaths", "LocalOutputPath"),
    ("ShowSettings", "ShowFolder"),
]


# directive: path-schema-migration | # see path.S8
def _LegacyName(Column: str) -> str:
    """Rename target: prefix _legacy_ to flag the column as deprecated."""
    return f"_legacy_{Column.lower()}"


# directive: path-schema-migration | # see path.S8
def _ColumnExists(Db, Table: str, Column: str) -> bool:
    """True iff the column currently exists on the table (case-insensitive match)."""
    Row = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) AND LOWER(column_name) = LOWER(%s) LIMIT 1",
        (Table, Column),
    )
    return bool(Row)


# directive: path-schema-migration | # see path.S8
def _DropNotNullIfPresent(Db, Table: str, Column: str) -> bool:
    """Drop NOT NULL on the renamed column if it still carries the constraint; idempotent."""
    Row = Db.ExecuteQuery(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) AND LOWER(column_name) = LOWER(%s) LIMIT 1",
        (Table, Column),
    )
    if not Row:
        return False
    NullableValue = Row[0]["is_nullable"] if "is_nullable" in Row[0] else Row[0].get("IS_NULLABLE")
    if (NullableValue or "").upper() == "NO":
        Db.ExecuteNonQuery(f"ALTER TABLE {Table} ALTER COLUMN {Column} DROP NOT NULL")
        return True
    return False


# directive: path-schema-migration | # see path.S8
def Run() -> int:
    """Idempotently RENAME legacy path columns to _legacy_<name> + drop their NOT NULL; rollback is one RENAME away."""
    Db = DatabaseService()
    print("=== PathSchemaMigration 2026-06-04 (RENAME mode) ===")
    print("Before:")
    Plan = []
    for Table, LegacyCol in TARGETS:
        NewName = _LegacyName(LegacyCol)
        HasLegacy = _ColumnExists(Db, Table, LegacyCol)
        HasNew = _ColumnExists(Db, Table, NewName)
        if HasLegacy and not HasNew:
            Status = f"present -> will rename to {NewName}"
            Plan.append((Table, LegacyCol, NewName, "rename"))
        elif HasNew and not HasLegacy:
            Status = "already renamed (skip)"
            Plan.append((Table, LegacyCol, NewName, "skip"))
        elif not HasLegacy and not HasNew:
            Status = "absent on both names (skip)"
            Plan.append((Table, LegacyCol, NewName, "absent"))
        else:
            Status = "BOTH names present -- manual intervention required"
            Plan.append((Table, LegacyCol, NewName, "ambiguous"))
        print(f"  {Table}.{LegacyCol}: {Status}")
    Renamed = 0
    Skipped = 0
    Ambiguous = 0
    for Table, LegacyCol, NewName, Action in Plan:
        if Action == "rename":
            Stmt = f"ALTER TABLE {Table} RENAME COLUMN {LegacyCol} TO {NewName}"
            Db.ExecuteNonQuery(Stmt)
            print(f"RENAMED: {Table}.{LegacyCol} -> {NewName}")
            Renamed += 1
        elif Action == "ambiguous":
            print(f"REFUSED: {Table}.{LegacyCol} and {Table}.{NewName} both exist -- skipping; resolve manually")
            Ambiguous += 1
        else:
            Skipped += 1
    print(f"Summary: renamed={Renamed}, skipped={Skipped}, ambiguous={Ambiguous}")
    print("Dropping NOT NULL on the renamed columns so V2 INSERTs that skip them succeed:")
    NotNullDropped = 0
    for Table, LegacyCol in TARGETS:
        if _DropNotNullIfPresent(Db, Table, _LegacyName(LegacyCol)):
            print(f"  DROP NOT NULL: {Table}.{_LegacyName(LegacyCol)}")
            NotNullDropped += 1
    print(f"  NOT NULL drops: {NotNullDropped}")
    print("After:")
    for Table, LegacyCol in TARGETS:
        NewName = _LegacyName(LegacyCol)
        HasLegacy = _ColumnExists(Db, Table, LegacyCol)
        HasNew = _ColumnExists(Db, Table, NewName)
        if HasNew and not HasLegacy:
            print(f"  {Table}.{NewName}: present (legacy hidden from V2 code) -- OK")
        elif not HasLegacy and not HasNew:
            print(f"  {Table}.{LegacyCol}: absent -- OK")
        else:
            print(f"  {Table}.{LegacyCol}: STILL PRESENT under legacy name -- FAIL")
            return 1
    return 0 if Ambiguous == 0 else 2


if __name__ == "__main__":
    sys.exit(Run())
