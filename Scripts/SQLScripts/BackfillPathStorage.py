"""Phase 2 of path-storage rewrite -- backfill (StorageRootId, RelativePath)
on every existing row that has a parseable FilePath.

Owns: path-storage.feature.md criteria 6, 7.

Strategy:
- Read StorageRoots: {media_tv -> 'T:\\', movies -> 'M:\\', xxx -> 'Z:\\'}.
- For each row in MediaFiles, TranscodeQueue, TranscodeAttempts, ShowSettings,
  MediaFilesArchive, TemporaryFilePaths:
  - Read the table's primary path column (FilePath, RootFolder, ShowFolder,
    OriginalPath, etc. -- depends on the table).
  - Try matching against each CanonicalPrefix (longest first, case-insensitive).
  - On match: set StorageRootId; strip the prefix; convert backslashes to
    forward slashes; trim leading slashes; store as RelativePath.
  - On no match: leave (NULL, NULL); count as orphan.
- Reports matched/orphan counts per table, with a sample of orphans for
  operator review BEFORE Phase 5 cleanup.

Idempotent: rows that already have StorageRootId populated are skipped unless
--force is passed.

Reversible: a separate flag --reset clears all StorageRootId+RelativePath
columns back to NULL on every table (use for dev iteration; never in prod).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


# Per-table backfill config:
#   table:        SQL identifier
#   pathColumn:   the column that today carries the canonical path
#   pkColumn:     primary key, used to UPDATE row-by-row
TABLES = [
    {'table': 'MediaFiles',         'pathColumn': 'FilePath',    'pkColumn': 'Id'},
    {'table': 'TranscodeQueue',     'pathColumn': 'FilePath',    'pkColumn': 'Id'},
    {'table': 'TranscodeAttempts',  'pathColumn': 'FilePath',    'pkColumn': 'Id'},
    {'table': 'ShowSettings',       'pathColumn': 'ShowFolder',  'pkColumn': 'Id'},
    {'table': 'MediaFilesArchive',  'pathColumn': 'FilePath',    'pkColumn': 'Id'},
    # TemporaryFilePaths has 3 path columns (OriginalPath, LocalSourcePath,
    # LocalOutputPath); the (StorageRootId, RelativePath) we add here
    # represents the SOURCE side (OriginalPath). The output side is handled
    # by Phase 3 writer changes -- not retroactively backfilled because the
    # legacy LocalOutputPath rows have the well-known wonky staging shape
    # (`\staging\<worker>\T:\Show\<filename>`) that doesn't cleanly map.
    {'table': 'TemporaryFilePaths', 'pathColumn': 'OriginalPath', 'pkColumn': 'Id'},
]


def LoadStorageRoots(Db):
    """Return list of (Id, Name, CanonicalPrefix) sorted by prefix length
    descending so longest match wins (e.g. T:\\Foo\\ before T:\\)."""
    Rows = Db.ExecuteQuery("SELECT Id, Name, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC")
    return [{'Id': R['Id'], 'Name': R['Name'], 'Prefix': R['CanonicalPrefix']} for R in Rows]


def Parse(CanonicalPath, StorageRoots):
    """Return (storage_root_id, relative_path) or (None, None) if no match."""
    if not CanonicalPath:
        return (None, None)
    Upper = CanonicalPath.upper()
    for Sr in StorageRoots:
        PrefUpper = Sr['Prefix'].upper()
        if Upper.startswith(PrefUpper):
            Rel = CanonicalPath[len(Sr['Prefix']):]
            Rel = Rel.replace('\\', '/').lstrip('/')
            return (Sr['Id'], Rel)
    return (None, None)


def BackfillTable(Db, TableConfig, StorageRoots, Force=False):
    """Backfill (StorageRootId, RelativePath) for one table. Returns
    (matched_count, orphan_count, orphan_samples)."""
    Table = TableConfig['table']
    PathCol = TableConfig['pathColumn']
    PkCol = TableConfig['pkColumn']

    WhereClause = "" if Force else " WHERE StorageRootId IS NULL"
    Rows = Db.ExecuteQuery(
        f"SELECT {PkCol} AS pk, {PathCol} AS path FROM {Table}{WhereClause}"
    )
    if not Rows:
        print(f"  {Table:22}  no rows to backfill")
        return (0, 0, [])

    Matched = 0
    Orphan = 0
    OrphanSamples = []
    for R in Rows:
        SrId, Rel = Parse(R['path'], StorageRoots)
        if SrId is None:
            Orphan += 1
            if len(OrphanSamples) < 5:
                OrphanSamples.append((R['pk'], R['path']))
            continue
        Db.ExecuteNonQuery(
            f"UPDATE {Table} SET StorageRootId = %s, RelativePath = %s WHERE {PkCol} = %s",
            (SrId, Rel, R['pk']),
        )
        Matched += 1
    print(f"  {Table:22}  matched={Matched:>6}  orphans={Orphan:>4}")
    return (Matched, Orphan, OrphanSamples)


def Main():
    Force = '--force' in sys.argv
    Reset = '--reset' in sys.argv

    Db = DatabaseService()

    if Reset:
        print("RESET mode: clearing StorageRootId + RelativePath on every table.\n")
        for TableConfig in TABLES:
            Db.ExecuteNonQuery(
                f"UPDATE {TableConfig['table']} SET StorageRootId = NULL, RelativePath = NULL"
            )
            print(f"  CLEARED {TableConfig['table']}")
        return

    StorageRoots = LoadStorageRoots(Db)
    print(f"Loaded {len(StorageRoots)} StorageRoots:")
    for Sr in StorageRoots:
        print(f"  Id={Sr['Id']:>3}  {Sr['Name']:10}  prefix={Sr['Prefix']!r}")
    print()
    if Force:
        print("FORCE mode: backfilling every row (overwriting existing StorageRootId/RelativePath).\n")
    else:
        print("Default mode: only backfilling rows with StorageRootId IS NULL.\n")

    AllOrphans = {}
    TotalMatched = 0
    TotalOrphan = 0
    for TableConfig in TABLES:
        Matched, Orphan, Samples = BackfillTable(Db, TableConfig, StorageRoots, Force=Force)
        TotalMatched += Matched
        TotalOrphan += Orphan
        if Samples:
            AllOrphans[TableConfig['table']] = Samples

    print()
    print(f"TOTAL: matched={TotalMatched}  orphans={TotalOrphan}")

    if AllOrphans:
        print("\nOrphan samples (first 5 per table) -- review before Phase 5 cleanup:")
        for Table, Samples in AllOrphans.items():
            print(f"\n  {Table}:")
            for Pk, Path_ in Samples:
                print(f"    {Pk}  {Path_!r}")


if __name__ == "__main__":
    Main()
