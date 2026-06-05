import sys
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


# directive: path-perfect-implementation | # see path-storage.S1
def _AddColumnIfMissing(Db, Table: str, Column: str, Ddl: str) -> bool:
    Existing = Db.ExecuteScalar(
        "SELECT 1 FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) AND LOWER(column_name) = LOWER(%s) LIMIT 1",
        (Table, Column),
    )
    if Existing:
        print(f"[skip] {Table}.{Column} already present")
        return False
    Db.ExecuteNonQuery(f"ALTER TABLE {Table} ADD COLUMN {Column} {Ddl}")
    print(f"[ok]   {Table}.{Column} added")
    return True


# directive: path-perfect-implementation | # see path-storage.S1
def _BackfillRootFolders(Db, Srs) -> int:
    Rows = Db.ExecuteQuery(
        "SELECT Id, RootFolder FROM RootFolders WHERE StorageRootId IS NULL OR RelativePath IS NULL",
        (),
    )
    Updated = 0
    for R in Rows:
        try:
            P = Path.FromLegacyString(R["RootFolder"], Srs)
        except PathError as Ex:
            print(f"[FAIL] RootFolders.Id={R['Id']} cannot parse {R['RootFolder']!r}: {Ex}")
            return -1
        Db.ExecuteNonQuery(
            "UPDATE RootFolders SET StorageRootId = %s, RelativePath = %s WHERE Id = %s",
            (P.StorageRootId, P.RelativePath, R["Id"]),
        )
        Updated += 1
    print(f"[ok]   RootFolders: backfilled {Updated} rows")
    return Updated


# directive: path-perfect-implementation | # see path-storage.S1
def _CleanupMalformedScanJobs(Db, Srs) -> int:
    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT RootFolderPath FROM ScanJobs WHERE StorageRootId IS NULL OR RelativePath IS NULL",
        (),
    )
    Malformed = []
    for R in Rows:
        Rfp = R["RootFolderPath"]
        try:
            Path.FromLegacyString(Rfp, Srs)
        except PathError:
            Malformed.append(Rfp)
    Deleted = 0
    for Rfp in Malformed:
        Cnt = Db.ExecuteScalar(
            "SELECT COUNT(*) FROM ScanJobs WHERE RootFolderPath = %s AND Status IN ('Completed','Failed','Stopped')",
            (Rfp,),
        ) or 0
        if Cnt == 0:
            print(f"[FAIL] malformed ScanJobs.RootFolderPath={Rfp!r} has non-terminal rows; refusing to delete")
            return -1
        Db.ExecuteNonQuery("DELETE FROM ScanJobs WHERE RootFolderPath = %s", (Rfp,))
        Deleted += int(Cnt)
        print(f"[ok]   deleted {Cnt} historical ScanJobs row(s) with malformed RootFolderPath={Rfp!r}")
    return Deleted


# directive: path-perfect-implementation | # see path-storage.S1
def _BackfillScanJobs(Db, Srs) -> int:
    Rows = Db.ExecuteQuery(
        "SELECT JobId, RootFolderPath FROM ScanJobs WHERE StorageRootId IS NULL OR RelativePath IS NULL",
        (),
    )
    Updated = 0
    for R in Rows:
        try:
            P = Path.FromLegacyString(R["RootFolderPath"], Srs)
        except PathError as Ex:
            print(f"[FAIL] ScanJobs.JobId={R['JobId']} cannot parse {R['RootFolderPath']!r}: {Ex}")
            return -1
        Db.ExecuteNonQuery(
            "UPDATE ScanJobs SET StorageRootId = %s, RelativePath = %s WHERE JobId = %s",
            (P.StorageRootId, P.RelativePath, R["JobId"]),
        )
        Updated += 1
    print(f"[ok]   ScanJobs: backfilled {Updated} rows")
    return Updated


# directive: path-perfect-implementation | # see path-storage.S1
def Run() -> int:
    Db = DatabaseService()
    Srs = GetStorageRoots()

    _AddColumnIfMissing(Db, "RootFolders", "StorageRootId", "BIGINT NULL REFERENCES StorageRoots(Id)")
    _AddColumnIfMissing(Db, "RootFolders", "RelativePath", "TEXT NULL")
    _AddColumnIfMissing(Db, "ScanJobs", "StorageRootId", "BIGINT NULL REFERENCES StorageRoots(Id)")
    _AddColumnIfMissing(Db, "ScanJobs", "RelativePath", "TEXT NULL")

    Rf = _BackfillRootFolders(Db, Srs)
    if Rf < 0:
        return 2

    Cleaned = _CleanupMalformedScanJobs(Db, Srs)
    if Cleaned < 0:
        return 3

    Sj = _BackfillScanJobs(Db, Srs)
    if Sj < 0:
        return 4

    NullRf = Db.ExecuteScalar(
        "SELECT COUNT(*) FROM RootFolders WHERE StorageRootId IS NULL OR RelativePath IS NULL",
        (),
    )
    NullSj = Db.ExecuteScalar(
        "SELECT COUNT(*) FROM ScanJobs WHERE StorageRootId IS NULL OR RelativePath IS NULL",
        (),
    )
    print(f"[verify] RootFolders rows with NULL typed pair: {NullRf}")
    print(f"[verify] ScanJobs rows with NULL typed pair: {NullSj}")
    if (NullRf or 0) != 0 or (NullSj or 0) != 0:
        print("[FAIL] verification gate not met")
        return 5
    print("[done] Step 1 complete")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
