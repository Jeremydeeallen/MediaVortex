import os
import sys
import argparse

ScriptDir = os.path.dirname(os.path.abspath(__file__))
RepoRoot = os.path.abspath(os.path.join(ScriptDir, '..', '..'))
if RepoRoot not in sys.path:
    sys.path.insert(0, RepoRoot)

from Core.Database.DatabaseService import DatabaseService
from Core.Path.LocalPath import LocalExists, LocalGetSize


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def FetchDuplicatePairs(Db):
    Sql = (
        "WITH norm AS ( "
        "  SELECT m.Id, m.StorageRootId, m.RelativePath, m.FileName, m.SizeMB, m.Codec, "
        "         m.TranscodedByMediaVortex, m.RemuxedByMediaVortex, "
        "         sr.CanonicalPrefix, "
        "         regexp_replace(m.RelativePath, '/[^/]+$', '') AS Dir, "
        "         CASE WHEN m.FileName ~ '-mv\\.[^.]+$' THEN regexp_replace(m.FileName, '-mv\\.[^.]+$', '') "
        "              ELSE regexp_replace(m.FileName, '\\.[^.]+$', '') END AS Base, "
        "         m.FileName ~ '-mv\\.[^.]+$' AS IsMv "
        "  FROM MediaFiles m "
        "  JOIN StorageRoots sr ON sr.Id = m.StorageRootId "
        "  WHERE m.StorageRootId IS NOT NULL AND m.RelativePath IS NOT NULL "
        ") "
        "SELECT a.Id AS MvId, a.FileName AS MvName, a.SizeMB AS MvSizeMB, a.Codec AS MvCodec, "
        "       a.TranscodedByMediaVortex AS MvTrans, a.RemuxedByMediaVortex AS MvRemux, "
        "       a.CanonicalPrefix AS MvPrefix, a.RelativePath AS MvRel, "
        "       b.Id AS SrcId, b.FileName AS SrcName, b.SizeMB AS SrcSizeMB, b.Codec AS SrcCodec, "
        "       b.CanonicalPrefix AS SrcPrefix, b.RelativePath AS SrcRel "
        "FROM norm a "
        "JOIN norm b ON a.StorageRootId = b.StorageRootId "
        "           AND a.Dir = b.Dir "
        "           AND a.Base = b.Base "
        "           AND a.IsMv = TRUE "
        "           AND b.IsMv = FALSE "
        "           AND a.Id <> b.Id "
        "ORDER BY a.Id"
    )
    return Db.ExecuteQuery(Sql)


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def CanonicalLocal(Prefix, Rel):
    return Prefix + Rel.replace('/', chr(92))


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def DeleteRow(Db, MediaFileId):
    Db.ExecuteNonQuery('DELETE FROM FailureBudgetResets WHERE MediaFileId = %s', (MediaFileId,))
    return Db.ExecuteNonQuery('DELETE FROM MediaFiles WHERE Id = %s', (MediaFileId,))


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def SizeDriftSafe(LocalPath, DbSizeMB):
    Actual = LocalGetSize(LocalPath)  # allow: local-path; canonical-equals-local on i9
    Expected = int(DbSizeMB * 1024 * 1024)
    Pct = abs(Actual - Expected) / max(Expected, 1) * 100
    return Pct <= 10, Actual, Expected, Pct


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def Main():
    Parser = argparse.ArgumentParser(description='Disk-aware cleanup of duplicate MediaFile pairs (BUG-0067 follow-up).')
    Parser.add_argument('--execute', action='store_true', help='Actually delete files + DB rows. Without this flag, runs dry-run.')
    Parser.add_argument('--include-unflagged-both', action='store_true', help='Include BothOnDisk pairs where the mv row has neither TranscodedByMediaVortex=True nor RemuxedByMediaVortex=True. Default: skip (too risky).')
    Args = Parser.parse_args()

    DryRun = not Args.execute
    Mode = 'DRY-RUN' if DryRun else 'EXECUTE'
    print(f'=== CleanupDuplicateSourcesFromBug0067 [{Mode}] ===')
    print('Policy: when BOTH files exist on disk -> delete SOURCE file + source DB row; keep -mv.')
    print()

    Db = DatabaseService()
    Pairs = FetchDuplicatePairs(Db)
    print(f'Found {len(Pairs)} duplicate pairs total.')
    print()

    Buckets = {'BothOnDisk': [], 'OnlyMvOnDisk': [], 'OnlySrcOnDisk': [], 'NeitherOnDisk': [], 'Skipped': []}

    for P in Pairs:
        MvLocal = CanonicalLocal(P['MvPrefix'], P['MvRel'])
        SrcLocal = CanonicalLocal(P['SrcPrefix'], P['SrcRel'])
        MvExists = LocalExists(MvLocal)  # allow: local-path; canonical-equals-local on i9
        SrcExists = LocalExists(SrcLocal)  # allow: local-path; canonical-equals-local on i9

        if MvExists and SrcExists:
            Bucket = 'BothOnDisk'
        elif MvExists and not SrcExists:
            Bucket = 'OnlyMvOnDisk'
        elif not MvExists and SrcExists:
            Bucket = 'OnlySrcOnDisk'
        else:
            Bucket = 'NeitherOnDisk'

        Buckets[Bucket].append({'P': P, 'MvLocal': MvLocal, 'SrcLocal': SrcLocal, 'MvExists': MvExists, 'SrcExists': SrcExists})

    print('Disk-state breakdown:')
    for K in ('BothOnDisk', 'OnlyMvOnDisk', 'OnlySrcOnDisk', 'NeitherOnDisk'):
        print(f'  {K}: {len(Buckets[K])}')
    print()

    Stats = {'FileDeleted': 0, 'MvRowDeleted': 0, 'SrcRowDeleted': 0, 'Skipped': 0}

    UnflaggedBothSkipped = 0
    for Item in Buckets['BothOnDisk']:
        P = Item['P']
        FlagVerified = (P['MvTrans'] is True) or (P['MvRemux'] is True)
        if not FlagVerified and not Args.include_unflagged_both:
            UnflaggedBothSkipped += 1
            continue
        Tag = 'VerifiedMv' if FlagVerified else 'UnflaggedMv'
        Header = f"[BothOnDisk/{Tag}] mv={P['MvId']} src={P['SrcId']} basename={P['MvName'][:60]}..."
        print(Header)
        Safe, Actual, Expected, Pct = SizeDriftSafe(Item['SrcLocal'], P['SrcSizeMB'])
        if not Safe:
            print(f'  SAFETY ABORT: source size on disk ({Actual} bytes) drifts {Pct:.1f}% from DB SizeMB ({Expected} bytes); skipping.')
            Stats['Skipped'] += 1
            Buckets['Skipped'].append(Item)
            print()
            continue
        if DryRun:
            print(f'  WOULD delete source FILE: {Item["SrcLocal"]} ({Actual:,} bytes)')
            print(f'  WOULD delete source DB row: Id={P["SrcId"]} (TranscodeQueue/ProblemFiles cascade)')
        else:
            try:
                os.remove(Item['SrcLocal'])
                Stats['FileDeleted'] += 1
                print(f'  DELETED source file: {Item["SrcLocal"]}')
            except OSError as Ex:
                print(f'  FILE DELETE FAILED: {Ex}; skipping DB cleanup for pair.')
                Stats['Skipped'] += 1
                print()
                continue
            Rows = DeleteRow(Db, P['SrcId'])
            if Rows == 1:
                Stats['SrcRowDeleted'] += 1
                print(f'  DELETED source DB row: Id={P["SrcId"]}')
            else:
                print(f'  unexpected DB rowcount={Rows}')
        print()
    if UnflaggedBothSkipped:
        print(f'[BothOnDisk/UnflaggedMv]: SKIPPED {UnflaggedBothSkipped} pairs (mv row not flagged TranscodedByMediaVortex=True or RemuxedByMediaVortex=True). Pass --include-unflagged-both to include them. These need operator eyes -- the -mv naming might be coincidental rather than MV-produced.')
        print()

    for Item in Buckets['OnlyMvOnDisk']:
        P = Item['P']
        Header = f"[OnlyMvOnDisk] mv={P['MvId']} src={P['SrcId']} -- source DB row is stale (no file)"
        print(Header)
        if DryRun:
            print(f'  WOULD delete source DB row: Id={P["SrcId"]}')
        else:
            Rows = DeleteRow(Db, P['SrcId'])
            if Rows == 1:
                Stats['SrcRowDeleted'] += 1
                print(f'  DELETED source DB row: Id={P["SrcId"]}')
            else:
                print(f'  unexpected DB rowcount={Rows}')
        print()

    for Item in Buckets['OnlySrcOnDisk']:
        P = Item['P']
        Header = f"[OnlySrcOnDisk] mv={P['MvId']} src={P['SrcId']} -- mv DB row is stale (no file)"
        print(Header)
        if DryRun:
            print(f'  WOULD delete mv DB row: Id={P["MvId"]}')
        else:
            Rows = DeleteRow(Db, P['MvId'])
            if Rows == 1:
                Stats['MvRowDeleted'] += 1
                print(f'  DELETED mv DB row: Id={P["MvId"]}')
            else:
                print(f'  unexpected DB rowcount={Rows}')
        print()

    for Item in Buckets['NeitherOnDisk']:
        P = Item['P']
        Header = f"[NeitherOnDisk] mv={P['MvId']} src={P['SrcId']} -- both DB rows are phantom (no files)"
        print(Header)
        if DryRun:
            print(f'  WOULD delete mv DB row: Id={P["MvId"]}')
            print(f'  WOULD delete src DB row: Id={P["SrcId"]}')
        else:
            R1 = DeleteRow(Db, P['MvId'])
            R2 = DeleteRow(Db, P['SrcId'])
            if R1 == 1:
                Stats['MvRowDeleted'] += 1
                print(f'  DELETED mv DB row: Id={P["MvId"]}')
            if R2 == 1:
                Stats['SrcRowDeleted'] += 1
                print(f'  DELETED src DB row: Id={P["SrcId"]}')
        print()

    print()
    print('Summary:')
    for K, V in Stats.items():
        print(f'  {K}: {V}')
    print()
    if DryRun:
        print('Dry-run only -- pass --execute to actually delete.')


if __name__ == '__main__':
    Main()
