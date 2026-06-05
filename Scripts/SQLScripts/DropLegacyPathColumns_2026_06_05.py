import sys
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: path-perfect-implementation | # see path-storage.S1
DROPS = [
    ("RootFolders", "RootFolder"),
    ("ScanJobs", "RootFolderPath"),
    ("MediaFiles", "_legacy_filepath"),
    ("MediaFilesArchive", "_legacy_filepath"),
    ("TranscodeQueue", "_legacy_filepath"),
    ("TranscodeAttempts", "_legacy_filepath"),
    ("TemporaryFilePaths", "_legacy_originalpath"),
    ("TemporaryFilePaths", "_legacy_localsourcepath"),
    ("TemporaryFilePaths", "_legacy_localoutputpath"),
    ("ShowSettings", "_legacy_showfolder"),
]


# directive: path-perfect-implementation | # see path-storage.S1
def _ColumnExists(Db, Table: str, Column: str) -> bool:
    Row = Db.ExecuteScalar(
        "SELECT 1 FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) AND LOWER(column_name) = LOWER(%s) LIMIT 1",
        (Table, Column),
    )
    return Row is not None


# directive: path-perfect-implementation | # see path-storage.S1
def Run() -> int:
    Db = DatabaseService()
    Dropped = 0
    Skipped = 0
    for Table, Column in DROPS:
        if not _ColumnExists(Db, Table, Column):
            print(f"[skip] {Table}.{Column} not present")
            Skipped += 1
            continue
        Db.ExecuteNonQuery(f"ALTER TABLE {Table} DROP COLUMN {Column}")
        print(f"[ok]   dropped {Table}.{Column}")
        Dropped += 1
    print(f"[done] {Dropped} columns dropped, {Skipped} already absent")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
