"""Read-only damage assessment after the bulk -mv.mp4 delete mistake.

For each MediaFiles row pointing at an -mv.mp4 path in the four affected
shows, check:
  - Is the -mv.mp4 file currently on disk? (status: file_exists / file_missing)
  - Is there a corresponding .mkv source row in MediaFiles AND on disk?
  - If both are missing -> TRUE data loss

Output: per-show counts + a small sample of each category.
"""

import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Tests.Pipeline.Harness.Invocation import _EnsureWorkerContext
_EnsureWorkerContext('I9-2024')

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots
from Core.Path.Worker import Worker
from Core.WorkerContext import WorkerContext

Db = DatabaseService()
ctx = WorkerContext.Current()
roots = GetStorageRoots()
W = Worker(Name=ctx.WorkerName, Platform=getattr(ctx, 'Platform', 'windows'), Db=Db)

# The shows I deleted from
SHOWS = [
    'Adventure Time',
    'Ren & Stimpy',
    'Teenage Robot',
    'Animaniacs',
    'Gumball',
]

def resolve(canonical):
    try:
        P = Path.FromLegacyString(canonical, roots)
    except PathError:
        return None
    try:
        return P.Resolve(W)
    except PathError:
        return None

for show in SHOWS:
    print(f"=== {show} ===")
    rows = Db.ExecuteQuery(
        "SELECT Id, FilePath FROM MediaFiles WHERE FilePath ILIKE %s AND FilePath ILIKE %s ORDER BY FilePath",
        (f'%{show}%', '%-mv.mp4'),
    )
    file_exists = 0
    file_missing = 0
    missing_with_mkv_recoverable = 0
    missing_no_mkv = 0
    samples_missing = []
    for r in rows:
        canonical = r['FilePath']
        local = resolve(canonical)
        if local and os.path.exists(local):
            file_exists += 1
            continue
        file_missing += 1
        # Check if there's a recoverable .mkv source
        mkv_canonical = canonical.replace('-mv.mp4', '.mkv')
        mkv_local = resolve(mkv_canonical)
        if mkv_local and os.path.exists(mkv_local):
            missing_with_mkv_recoverable += 1
        else:
            missing_no_mkv += 1
            if len(samples_missing) < 3:
                samples_missing.append(canonical)
    total = file_exists + file_missing
    print(f"  Total -mv.mp4 rows for this show: {total}")
    print(f"  -mv.mp4 file STILL on disk:      {file_exists}")
    print(f"  -mv.mp4 file MISSING:            {file_missing}")
    print(f"    of those, recoverable (mkv source available): {missing_with_mkv_recoverable}")
    print(f"    of those, NO recovery path (mkv source gone): {missing_no_mkv}")
    if samples_missing:
        print(f"  Sample(s) with no recovery path:")
        for s in samples_missing:
            print(f"    {s}")
    print()
