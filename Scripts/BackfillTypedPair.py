# directive: path-schema-migration | # see path.S6
import sys
from pathlib import Path as PyPath

sys.path.append(str(PyPath(__file__).parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Path import Path, PathError


# directive: path-schema-migration | # see path.S6
def _LoadStorageRoots(Db):
    """Load StorageRoots prefix list, longest-first."""
    Rows = Db.ExecuteQuery(
        "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
    )
    return [{"Id": R.get("id", R.get("Id")),
             "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
            for R in Rows]


# directive: path-schema-migration | # see path.S6
def _BackfillTable(Db, Table, IdCol, LegacyCol, SidCol, RelCol, StorageRoots, Commit: bool):
    """Walk every row where typed pair is NULL but legacy column is populated. Parse via FromLegacyString and UPDATE typed pair. Return (parsed, failed) counts; failures logged."""
    SelectSql = (
        f"SELECT {IdCol} AS rowid, {LegacyCol} AS legacy "
        f"FROM {Table} "
        f"WHERE ({SidCol} IS NULL OR {RelCol} IS NULL) AND {LegacyCol} IS NOT NULL"
    )
    Rows = Db.ExecuteQuery(SelectSql)
    Parsed = 0
    Failed = []
    for Row in Rows:
        RowId = Row.get("rowid")
        Legacy = Row.get("legacy")
        try:
            P = Path.FromLegacyString(Legacy, StorageRoots)
        except PathError as Exc:
            Failed.append((RowId, Legacy, str(Exc)))
            continue
        if Commit:
            Db.ExecuteNonQuery(
                f"UPDATE {Table} SET {SidCol} = %s, {RelCol} = %s WHERE {IdCol} = %s",
                (P.StorageRootId, P.RelativePath, RowId),
            )
        Parsed += 1
    return (Parsed, Failed)


# directive: path-schema-migration | # see path.S6
def Main():
    """Backfill typed pair on every path-bearing table; dry-run by default, --commit to persist."""
    Commit = "--commit" in sys.argv
    Db = DatabaseService()
    StorageRoots = _LoadStorageRoots(Db)
    Targets = [
        ("MediaFiles", "Id", "FilePath", "StorageRootId", "RelativePath"),
        ("TranscodeAttempts", "Id", "FilePath", "StorageRootId", "RelativePath"),
    ]
    Mode = "COMMIT" if Commit else "DRY-RUN"
    print(f"=== Backfill typed pair ({Mode}) ===")
    print(f"StorageRoots: {len(StorageRoots)}")
    for Table, IdCol, LegacyCol, SidCol, RelCol in Targets:
        Parsed, Failed = _BackfillTable(Db, Table, IdCol, LegacyCol, SidCol, RelCol, StorageRoots, Commit)
        print(f"{Table}: parsed={Parsed}, failed={len(Failed)}")
        for RowId, Legacy, Err in Failed[:5]:
            print(f"  FAIL id={RowId}: {Legacy!r} -> {Err}")
        if len(Failed) > 5:
            print(f"  ... {len(Failed) - 5} more failures")


if __name__ == "__main__":
    Main()
