"""Find and (optionally) delete stale `.inprogress` files left on disk.

Per `WorkerService/worker-lifecycle.feature.md` criteria 9 and 11, a
`.inprogress` file is supposed to be deleted on encode failure (C9) or
on the next worker startup via crash recovery (C11). Any `.inprogress`
older than the longest reasonable encode window is unambiguously an
orphan from one of the lifecycle holes (legacy lifecycle holes).

Default age cutoff: 240 minutes (4 hours). Anything older is safe to
delete -- no live worker is still writing to it.

Dry-run by default. Pass --commit to actually delete.
"""

import argparse
import os
import sys
import time
from pathlib import Path


# Storage roots to scan. These are the canonical share paths the I9 worker
# uses; the same files are visible on the Linux workers via NFS but we
# only need to find each file once, so scanning from one host is enough.
SCAN_ROOTS = [
    r"\\10.0.0.43\TV",
    r"\\10.0.0.43\Movies",
    r"\\10.0.0.43\Videos",
]


def Main():
    Parser = argparse.ArgumentParser()
    Parser.add_argument('--commit', action='store_true', help='Actually delete (default: dry-run)')
    Parser.add_argument('--min-age-minutes', type=int, default=240,
                        help='Only flag files older than this many minutes (default: 240 = 4h)')
    Args = Parser.parse_args()

    CutoffSec = time.time() - (Args.min_age_minutes * 60)
    print(f'Scanning for .inprogress files older than {Args.min_age_minutes} minutes ...')

    Found = []  # (Path, SizeBytes, AgeMinutes)
    for Root in SCAN_ROOTS:
        if not os.path.isdir(Root):
            print(f'  SKIP: {Root} not accessible')
            continue
        print(f'  walking {Root} ...')
        for Dir, _, Files in os.walk(Root):
            for F in Files:
                if not F.endswith('.inprogress'):
                    continue
                Full = os.path.join(Dir, F)
                try:
                    Stat = os.stat(Full)
                except Exception:
                    continue
                if Stat.st_mtime > CutoffSec:
                    continue
                AgeMin = (time.time() - Stat.st_mtime) / 60.0
                Found.append((Full, Stat.st_size, AgeMin))

    print()
    print(f'=== RESULTS ===')
    print(f'Stale .inprogress files found: {len(Found)}')
    TotalBytes = sum(S for _, S, _ in Found)
    print(f'Total reclaimable: {TotalBytes / (1024**3):.2f} GB')
    print()
    Found.sort(key=lambda T: T[2], reverse=True)  # oldest first
    for Pth, Sz, Age in Found[:30]:
        AgeStr = f'{Age/60.0:.1f}h' if Age >= 60 else f'{Age:.0f}m'
        print(f'  {Sz/(1024**2):8.1f} MB  {AgeStr:>7}  {Pth}')
    if len(Found) > 30:
        print(f'  ... and {len(Found) - 30} more')

    if not Args.commit:
        print()
        print('DRY RUN. Pass --commit to delete.')
        return

    print()
    print('--commit set. Deleting ...')
    Deleted = 0
    Failed = 0
    for Pth, _, _ in Found:
        try:
            os.remove(Pth)
            Deleted += 1
        except Exception as Ex:
            Failed += 1
            print(f'  FAILED: {Pth}: {Ex}')
    print(f'Deleted {Deleted} files, {Failed} failures.')


if __name__ == '__main__':
    Main()
