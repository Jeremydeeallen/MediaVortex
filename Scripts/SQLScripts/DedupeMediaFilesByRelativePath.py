"""Dedupe MediaFiles rows that share (StorageRootId, LOWER(RelativePath)) but
differ in FilePath escaping (e.g. 'T:\\Show\\f.mkv' vs 'T:\\\\Show\\f.mkv').

Backs FileScanning.feature.md criterion 27 and the KNOWN-ISSUES.md entry of
2026-05-16. The existing idx_mediafiles_filepath_unique keys on the raw
LOWER(FilePath) string, so escape variants slip through as distinct paths;
RelativePath (forward-slash form) is identical between the variants but has
no unique constraint. Result: 45k+ duplicate logical-file pairs.

Per dup group:
  Keeper = row with the CLEANEST FilePath (no doubled backslashes anywhere),
           ties broken by HIGHEST Id.
  Losers = the rest. FK references on TranscodeAttempts, TranscodeQueue,
           TranscodeFiles, ProblemFiles, and the MediaFilesArchive.Id
           correlation are repointed to the keeper before deletion.
  Keeper's FilePath is rewritten to the canonical clean form
  (no doubled backslashes) so the future UNIQUE (StorageRootId,
  LOWER(RelativePath)) constraint never sees a doubled variant.

Idempotent: re-running after success finds no dup groups and exits clean.
Use --dry-run to see the plan without writing.
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def DoubledBackslashCount(FilePath):
    if not FilePath:
        return 0
    return FilePath.count('\\\\')


def CanonicalFilePath(FilePath):
    """Collapse runs of backslashes to a single backslash."""
    if not FilePath:
        return FilePath
    while '\\\\' in FilePath:
        FilePath = FilePath.replace('\\\\', '\\')
    return FilePath


def PickKeeper(Rows):
    """Lowest doubled-backslash count wins; ties broken by highest Id."""
    Best = None
    BestKey = None
    for R in Rows:
        Key = (-DoubledBackslashCount(R['FilePath']), R['Id'])
        if BestKey is None or Key > BestKey:
            BestKey = Key
            Best = R
    return Best


def LoadDupGroups(Db):
    """Return list of (StorageRootId, RelativePathLower, [rows...]).

    Loads all rows belonging to ANY dup group in a single query (45k+ groups
    -> 90k+ rows), then groups in Python. Per-group SELECTs would issue
    45k+ round-trips and take minutes.
    """
    Rows = Db.ExecuteQuery("""
        SELECT Id, FilePath, RelativePath, StorageRootId
        FROM MediaFiles
        WHERE (StorageRootId, LOWER(RelativePath)) IN (
            SELECT StorageRootId, LOWER(RelativePath)
            FROM MediaFiles
            WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL
            GROUP BY StorageRootId, LOWER(RelativePath)
            HAVING COUNT(*) > 1
        )
        ORDER BY StorageRootId, LOWER(RelativePath), Id
    """)
    GroupMap = {}
    for R in Rows:
        Key = (R['StorageRootId'], R['RelativePath'].lower())
        GroupMap.setdefault(Key, []).append(R)
    return [(K[0], K[1], V) for K, V in GroupMap.items()]


def Run(DryRun):
    Db = DatabaseService()
    print('=== Loading duplicate groups ===')
    Groups = LoadDupGroups(Db)
    print(f'Duplicate groups found: {len(Groups)}')
    if not Groups:
        print('Nothing to do.')
        return

    TotalLosers = 0
    Plan = []
    for SRId, Rp, Rows in Groups:
        Keeper = PickKeeper(Rows)
        Losers = [R for R in Rows if R['Id'] != Keeper['Id']]
        TotalLosers += len(Losers)
        CleanFp = CanonicalFilePath(Keeper['FilePath'])
        RewriteKeeperFp = CleanFp != Keeper['FilePath']
        Plan.append((SRId, Rp, Keeper, Losers, CleanFp, RewriteKeeperFp))

    print(f'Total loser rows to migrate+delete: {TotalLosers}')
    KeeperRewrites = sum(1 for P in Plan if P[5])
    print(f'Keeper FilePath rewrites (doubled-backslash cleanup): {KeeperRewrites}')

    if DryRun:
        print('\n=== DRY RUN -- first 5 groups ===')
        for (SRId, Rp, Keeper, Losers, CleanFp, RewriteKeeperFp) in Plan[:5]:
            print(f'  SRId={SRId}  rp={Rp!r}')
            tag = ' (will rewrite)' if RewriteKeeperFp else ''
            print(f'    KEEP   Id={Keeper["Id"]:>7}  FilePath={Keeper["FilePath"]!r}{tag}')
            if RewriteKeeperFp:
                print(f'                       new FilePath={CleanFp!r}')
            for L in Losers:
                print(f'    DELETE Id={L["Id"]:>7}  FilePath={L["FilePath"]!r}')
        print('\nNo writes made.')
        return

    print('\n=== EXECUTING (batched per group, transaction per group) ===')
    Connection = Db.GetConnection()
    Cursor = Connection.cursor()
    Done = 0
    try:
        for (SRId, Rp, Keeper, Losers, CleanFp, RewriteKeeperFp) in Plan:
            KeeperId = Keeper['Id']
            LoserIds = [L['Id'] for L in Losers]
            Placeholders = ','.join(['%s'] * len(LoserIds))

            # 1. Repoint FK references on each child table.
            Cursor.execute(
                f"UPDATE TranscodeAttempts SET MediaFileId = %s WHERE MediaFileId IN ({Placeholders})",
                [KeeperId] + LoserIds,
            )
            Cursor.execute(
                f"UPDATE TranscodeQueue SET MediaFileId = %s WHERE MediaFileId IN ({Placeholders})",
                [KeeperId] + LoserIds,
            )
            Cursor.execute(
                f"UPDATE TranscodeFiles SET MediaFileId = %s WHERE MediaFileId IN ({Placeholders})",
                [KeeperId] + LoserIds,
            )
            Cursor.execute(
                f"UPDATE ProblemFiles SET MediaFileId = %s WHERE MediaFileId IN ({Placeholders})",
                [KeeperId] + LoserIds,
            )
            # MediaFilesArchive.Id correlates to MediaFiles.Id but has no FK.
            Cursor.execute(
                f"UPDATE MediaFilesArchive SET Id = %s WHERE Id IN ({Placeholders})",
                [KeeperId] + LoserIds,
            )

            # 2. Canonicalize keeper FilePath if needed.
            if RewriteKeeperFp:
                Cursor.execute(
                    "UPDATE MediaFiles SET FilePath = %s WHERE Id = %s",
                    (CleanFp, KeeperId),
                )

            # 3. Delete losers.
            Cursor.execute(
                f"DELETE FROM MediaFiles WHERE Id IN ({Placeholders})",
                LoserIds,
            )

            Connection.commit()
            Done += 1
            if Done % 500 == 0:
                print(f'  ...{Done}/{len(Plan)} groups committed')
        print(f'  ...{Done}/{len(Plan)} groups committed')
    except Exception as Ex:
        Connection.rollback()
        print(f'ABORTED at group {Done + 1}: {Ex}')
        raise
    finally:
        Db.CloseConnection(Connection)

    print('\n=== Verifying ===')
    Remaining = Db.ExecuteQuery("""
        SELECT COUNT(*) AS c FROM (
            SELECT StorageRootId, LOWER(RelativePath)
            FROM MediaFiles
            WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL
            GROUP BY StorageRootId, LOWER(RelativePath)
            HAVING COUNT(*) > 1
        ) sq
    """)
    print(f'Remaining duplicate groups: {Remaining[0]["c"]}')


if __name__ == '__main__':
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument('--dry-run', action='store_true', help='Show plan without writing')
    Args = Parser.parse_args()
    Run(DryRun=Args.dry_run)
