"""Detect and (optionally) delete source-file orphans left on disk after
a Quick Fix or Transcode replaced them with a -mv*.mp4 successor.

Scope: for every MediaFile whose canonical FilePath ends in -mv*.mp4,
walk its directory and flag any sibling file that:
  1. Has the same base name (with trailing -mv*.mp4 stripped)
  2. Is NOT the canonical itself
  3. Is NOT referenced by any MediaFile row
  4. Is NOT a sidecar (.nfo, -thumb.jpg, .srt, .idx, .sub, .ssa, .ass)

Catches both source-extension siblings (.mkv, .mp4, .avi, etc.) and
intermediate -mv generations (e.g. -mv.mp4 alongside a canonical
-mv-mv.mp4). Sidecar files are always preserved.

Dry-run by default. Pass --commit to actually delete.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Tests.Pipeline.Harness.Invocation import _EnsureWorkerContext
_EnsureWorkerContext('I9-2024')

from Core.Database.DatabaseService import DatabaseService
from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
from Core.WorkerContext import WorkerContext


SOURCE_VIDEO_EXTS = {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.wmv', '.ts', '.mpg', '.mpeg'}
SIDECAR_SUFFIXES = ('.nfo', '.srt', '.idx', '.sub', '.ssa', '.ass', '.vtt')
SIDECAR_TOKENS = ('-thumb.', '-poster.', '-fanart.', '-banner.', '-clearart.', '-landscape.')
# Filenames matching these substrings (case-insensitive) are preserved
# regardless of whether a MediaFile row references them. These are
# pre-MediaVortex assets the operator keeps for separate reasons.
KEEP_TOKENS = ('optimized',)

# Strip one-or-more "-mv" repetitions just before ".mp4"
MV_GEN_RE = re.compile(r'(?:-mv)+\.mp4$', re.IGNORECASE)


def IsSidecar(LowerName: str) -> bool:
    return (LowerName.endswith(SIDECAR_SUFFIXES)
            or any(Tok in LowerName for Tok in SIDECAR_TOKENS))


def StripMvGenerations(Filename: str) -> str:
    """'Foo-mv-mv.mp4' -> 'Foo'.  Returns None if no -mv*.mp4 suffix."""
    M = MV_GEN_RE.search(Filename)
    return Filename[:M.start()] if M else None


def Main():
    Parser = argparse.ArgumentParser()
    Parser.add_argument('--commit', action='store_true', help='Actually delete (default: dry-run)')
    Parser.add_argument('--limit', type=int, default=None, help='Stop after N orphans found')
    Args = Parser.parse_args()

    Db = DatabaseService()
    Ctx = WorkerContext.Current()
    Roots = LoadStorageRoots(Db)

    # Index every known MediaFile path (lowercased local path) so we can
    # cheaply test "is this file referenced anywhere in the DB?"
    print('Loading MediaFile index ...')
    AllMf = Db.ExecuteQuery('SELECT StorageRootId, RelativePath, FilePath FROM MediaFiles')
    Referenced = set()
    for R in AllMf:
        Local = None
        if R.get('StorageRootId') and R.get('RelativePath') is not None:
            Local = PathResolve(R['StorageRootId'], R['RelativePath'] or '', Ctx.WorkerName, Db)
        if not Local and R.get('FilePath'):
            try:
                Sr, Rel = PathParse(R['FilePath'], Roots)
                if Sr is not None:
                    Local = PathResolve(Sr, Rel or '', Ctx.WorkerName, Db)
            except Exception:
                pass
        if Local:
            Referenced.add(os.path.normcase(Local))
    print(f'  Indexed {len(Referenced)} MediaFile paths')

    # Canonical -mv*.mp4 rows: each one tells us a directory + basename to check.
    # Use parameter binding -- psycopg2 treats bare % in a SQL string as a
    # format placeholder.
    Canonicals = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, RelativePath, FilePath FROM MediaFiles "
        "WHERE FilePath ILIKE %s",
        ('%-mv.mp4',),
    )
    print(f'Found {len(Canonicals)} canonical -mv*.mp4 MediaFile rows')

    # Group canonicals by directory so we list each dir once
    ByDir = defaultdict(list)
    for R in Canonicals:
        Local = None
        if R.get('StorageRootId') and R.get('RelativePath') is not None:
            Local = PathResolve(R['StorageRootId'], R['RelativePath'] or '', Ctx.WorkerName, Db)
        if not Local:
            continue
        ByDir[os.path.dirname(Local)].append(os.path.basename(Local))

    print(f'Scanning {len(ByDir)} directories ...')

    Orphans = []  # (LocalPath, SizeBytes)
    DirsScanned = 0
    for DirPath, Canons in ByDir.items():
        DirsScanned += 1
        if DirsScanned % 200 == 0:
            print(f'  ... {DirsScanned}/{len(ByDir)} dirs, {len(Orphans)} orphans so far')
        # Compute the set of "basenames after -mv strip" we care about in this dir
        Bases = set()
        CanonLowerNames = set()
        for Cn in Canons:
            Base = StripMvGenerations(Cn)
            if Base:
                Bases.add(Base.lower())
            CanonLowerNames.add(Cn.lower())
        try:
            Entries = os.listdir(DirPath)
        except Exception as Ex:
            print(f'  WARN: cannot list {DirPath}: {Ex}')
            continue
        for Entry in Entries:
            EL = Entry.lower()
            if EL in CanonLowerNames:
                continue
            if IsSidecar(EL):
                continue
            if any(Tok in EL for Tok in KEEP_TOKENS):
                continue
            # Match against any base in this directory
            MatchedBase = None
            for B in Bases:
                if EL.startswith(B):
                    MatchedBase = B
                    break
            if not MatchedBase:
                continue
            # The remainder after the base must be either a source-ext or a -mv*.mp4 chain.
            # Match remainder directly against SOURCE_VIDEO_EXTS (`os.path.splitext('.mkv')`
            # returns `('.mkv', '')`, which would never match -- a leading-dot file is
            # treated as having no extension).
            Remainder = EL[len(MatchedBase):]
            IsVideoSrc = (Remainder in SOURCE_VIDEO_EXTS)
            IsMvGen = bool(MV_GEN_RE.search(Remainder))
            if not (IsVideoSrc or IsMvGen):
                continue
            # Confirm it's not referenced anywhere in the DB
            FullPath = os.path.join(DirPath, Entry)
            if os.path.normcase(FullPath) in Referenced:
                continue
            try:
                SizeBytes = os.path.getsize(FullPath)
            except Exception:
                SizeBytes = 0
            Orphans.append((FullPath, SizeBytes))
            if Args.limit and len(Orphans) >= Args.limit:
                break
        if Args.limit and len(Orphans) >= Args.limit:
            break

    print()
    print(f'=== RESULTS ===')
    print(f'Orphans found: {len(Orphans)}')
    TotalBytes = sum(S for _, S in Orphans)
    print(f'Total reclaimable: {TotalBytes / (1024**3):.2f} GB')
    print()
    # Show sample paths
    for Pth, Sz in Orphans[:15]:
        print(f'  {Sz/(1024**2):8.1f} MB  {Pth}')
    if len(Orphans) > 15:
        print(f'  ... and {len(Orphans) - 15} more')

    if not Args.commit:
        print()
        print('DRY RUN. Pass --commit to delete.')
        return

    print()
    print('--commit set. Deleting ...')
    Deleted = 0
    Failed = 0
    for Pth, _ in Orphans:
        try:
            os.remove(Pth)
            Deleted += 1
        except Exception as Ex:
            Failed += 1
            print(f'  FAILED: {Pth}: {Ex}')
    print(f'Deleted {Deleted} files, {Failed} failures.')


if __name__ == '__main__':
    Main()
