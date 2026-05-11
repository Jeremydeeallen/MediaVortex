"""Phase 1 of path-storage rewrite -- additive schema migration only.

Owns: path-storage.feature.md criteria 1, 2, 10 (additive portion).

Adds:
- NEW table StorageRoots (share-root registry; NOT the existing per-show
  RootFolders table, which stays as-is for scan targeting)
- NEW table StorageRootResolutions (per-(storage-root x worker) mapping;
  replaces WorkerShareMappings in Phase 5)
- NEW nullable columns StorageRootId + RelativePath on every path-bearing
  table: MediaFiles, TranscodeQueue, TranscodeAttempts, TemporaryFilePaths,
  ShowSettings, MediaFilesArchive

NO CHECK constraints yet (activated in Phase 4).
NO data backfill of path columns (that is Phase 2).
NO removal of legacy FilePath columns (that is Phase 5).

Seeds:
- StorageRoots with the 3 known shares (T -> media_tv, M -> movies, Z -> xxx)
- StorageRootResolutions from existing WorkerShareMappings (Linux workers)
  plus default Windows-drive resolutions per registered Windows worker

Fully idempotent. Reversible by dropping new columns/tables.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


# Initial share inventory. The CanonicalPrefix is the value the existing
# DB uses (Windows-shaped). It is used by Phase 2 backfill to longest-prefix-
# match existing FilePath values against the right storage root.
STORAGE_ROOTS = [
    {'Name': 'media_tv', 'Description': 'TV shows on Brain CIFS (T: on Windows)',                'CanonicalPrefix': 'T:\\'},
    {'Name': 'movies',   'Description': 'Movies on Synology _video/Adults/Movies (M: on Windows)', 'CanonicalPrefix': 'M:\\'},
    {'Name': 'xxx',      'Description': 'XXX share root on Synology (Z: on Windows)',             'CanonicalPrefix': 'Z:\\'},
]

# Tables that gain (StorageRootId, RelativePath) columns.
PATH_BEARING_TABLES = [
    'MediaFiles',
    'TranscodeQueue',
    'TranscodeAttempts',
    'TemporaryFilePaths',
    'ShowSettings',
    'MediaFilesArchive',
]


def TableExists(Cursor, TableName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s AND table_schema = current_schema()",
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s AND table_schema = current_schema()",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def Main():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        # === 1. StorageRoots ===
        if not TableExists(Cur, 'StorageRoots'):
            print("  CREATE StorageRoots")
            Cur.execute("""
                CREATE TABLE StorageRoots (
                    Id BIGSERIAL PRIMARY KEY,
                    Name TEXT UNIQUE NOT NULL,
                    Description TEXT,
                    CanonicalPrefix TEXT UNIQUE NOT NULL,
                    CreatedAt TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            Conn.commit()
        else:
            print("  EXISTS  StorageRoots")

        # === 2. StorageRootResolutions ===
        if not TableExists(Cur, 'StorageRootResolutions'):
            print("  CREATE StorageRootResolutions")
            Cur.execute("""
                CREATE TABLE StorageRootResolutions (
                    Id BIGSERIAL PRIMARY KEY,
                    StorageRootId BIGINT NOT NULL REFERENCES StorageRoots(Id) ON DELETE CASCADE,
                    WorkerName TEXT NOT NULL,
                    Platform TEXT NOT NULL,
                    AbsolutePath TEXT NOT NULL,
                    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
                    CreatedAt TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (StorageRootId, WorkerName)
                )
            """)
            Conn.commit()
        else:
            print("  EXISTS  StorageRootResolutions")

        # === 3. Path columns on each path-bearing table ===
        for TableName in PATH_BEARING_TABLES:
            if not TableExists(Cur, TableName):
                print(f"  SKIP    {TableName} (table missing)")
                continue
            if not ColumnExists(Cur, TableName, 'StorageRootId'):
                print(f"  ADD     {TableName}.StorageRootId")
                Cur.execute(f"ALTER TABLE {TableName} ADD COLUMN StorageRootId BIGINT REFERENCES StorageRoots(Id)")
                Conn.commit()
            else:
                print(f"  EXISTS  {TableName}.StorageRootId")
            if not ColumnExists(Cur, TableName, 'RelativePath'):
                print(f"  ADD     {TableName}.RelativePath")
                Cur.execute(f"ALTER TABLE {TableName} ADD COLUMN RelativePath TEXT")
                Conn.commit()
            else:
                print(f"  EXISTS  {TableName}.RelativePath")

        # === 4. Seed StorageRoots ===
        for Row in STORAGE_ROOTS:
            Cur.execute("SELECT Id FROM StorageRoots WHERE Name = %s", (Row['Name'],))
            Existing = Cur.fetchone()
            if Existing:
                print(f"  EXISTS  StorageRoots[{Row['Name']!r}] Id={Existing[0]}")
            else:
                Cur.execute(
                    "INSERT INTO StorageRoots (Name, Description, CanonicalPrefix) VALUES (%s, %s, %s) RETURNING Id",
                    (Row['Name'], Row['Description'], Row['CanonicalPrefix']),
                )
                NewId = Cur.fetchone()[0]
                print(f"  SEED    StorageRoots[{Row['Name']!r}] Id={NewId} CanonicalPrefix={Row['CanonicalPrefix']!r}")
                Conn.commit()

        # === 5. Seed StorageRootResolutions ===
        # Map drive letter -> StorageRoot.Id
        Cur.execute("SELECT Id, Name, CanonicalPrefix FROM StorageRoots")
        StorageRootByPrefix = {Row[2].upper(): {'Id': Row[0], 'Name': Row[1]} for Row in Cur.fetchall()}

        # 5a. From WorkerShareMappings (Linux workers + any with explicit mappings)
        Cur.execute(
            "SELECT wsm.WorkerName, wsm.DriveLetter, wsm.LocalMountPrefix, w.Platform "
            "FROM WorkerShareMappings wsm "
            "LEFT JOIN Workers w ON w.WorkerName = wsm.WorkerName"
        )
        for WorkerName, DriveLetter, LocalMountPrefix, Platform in Cur.fetchall():
            CanonPrefix = f"{DriveLetter.upper()}:\\"
            Sr = StorageRootByPrefix.get(CanonPrefix)
            if not Sr:
                print(f"  WARN    No StorageRoot for drive '{DriveLetter}:' (worker {WorkerName}); skipping")
                continue
            Cur.execute(
                "SELECT Id FROM StorageRootResolutions WHERE StorageRootId = %s AND WorkerName = %s",
                (Sr['Id'], WorkerName),
            )
            if Cur.fetchone():
                print(f"  EXISTS  StorageRootResolutions[{Sr['Name']}/{WorkerName}]")
                continue
            Cur.execute(
                "INSERT INTO StorageRootResolutions (StorageRootId, WorkerName, Platform, AbsolutePath) "
                "VALUES (%s, %s, %s, %s) RETURNING Id",
                (Sr['Id'], WorkerName, Platform or 'linux', LocalMountPrefix),
            )
            NewId = Cur.fetchone()[0]
            print(f"  SEED    StorageRootResolutions[{Sr['Name']}/{WorkerName}] Id={NewId} -> {LocalMountPrefix!r}")
            Conn.commit()

        # 5b. Default Windows-drive resolutions for any Windows worker that
        # has no explicit WorkerShareMappings entry (most Windows workers
        # use native drive letters and skipped the legacy mappings table).
        Cur.execute("SELECT WorkerName, Platform FROM Workers WHERE Platform = 'windows'")
        WindowsWorkers = Cur.fetchall()
        for WorkerName, Platform in WindowsWorkers:
            for Row in STORAGE_ROOTS:
                Sr = StorageRootByPrefix.get(Row['CanonicalPrefix'].upper())
                Cur.execute(
                    "SELECT Id FROM StorageRootResolutions WHERE StorageRootId = %s AND WorkerName = %s",
                    (Sr['Id'], WorkerName),
                )
                if Cur.fetchone():
                    continue
                # Windows: AbsolutePath == CanonicalPrefix (drive letters are native)
                Cur.execute(
                    "INSERT INTO StorageRootResolutions (StorageRootId, WorkerName, Platform, AbsolutePath) "
                    "VALUES (%s, %s, %s, %s) RETURNING Id",
                    (Sr['Id'], WorkerName, 'windows', Row['CanonicalPrefix']),
                )
                NewId = Cur.fetchone()[0]
                print(f"  SEED    StorageRootResolutions[{Sr['Name']}/{WorkerName}] Id={NewId} -> {Row['CanonicalPrefix']!r} (windows-native)")
                Conn.commit()

        # === 6. Summary ===
        print("\nDone.\n")
        print("StorageRoots:")
        Cur.execute("SELECT Id, Name, CanonicalPrefix FROM StorageRoots ORDER BY Id")
        for Row in Cur.fetchall():
            print(f"  Id={Row[0]:>3}  {Row[1]:12}  {Row[2]}")
        print("\nStorageRootResolutions:")
        Cur.execute("""
            SELECT srr.Id, sr.Name, srr.WorkerName, srr.Platform, srr.AbsolutePath
            FROM StorageRootResolutions srr
            JOIN StorageRoots sr ON sr.Id = srr.StorageRootId
            ORDER BY srr.WorkerName, sr.Name
        """)
        for Row in Cur.fetchall():
            print(f"  Id={Row[0]:>3}  {Row[1]:10}  {Row[2]:<18}  {Row[3]:<8}  {Row[4]}")
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    Main()
