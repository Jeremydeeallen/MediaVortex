"""
Cleanup script for leftover .orig files on the NAS.
Run on a machine that has /mnt/media_tv mounted.

Two categories:
  BOTH: .orig and media file both exist -> delete .orig (media file is the good remux result)
  ORIG_ONLY: only .orig exists -> rename .orig back to original path (restore the original)
"""
import os
import sys

DryRun = "--execute" not in sys.argv

BasePath = "/mnt/media_tv"

Both = []
OrigOnly = []

for Root, Dirs, Files in os.walk(BasePath):
    for F in Files:
        if F.endswith(".orig"):
            OrigPath = os.path.join(Root, F)
            MediaPath = OrigPath[:-5]  # strip .orig
            if os.path.isfile(MediaPath):
                Both.append((OrigPath, MediaPath))
            else:
                OrigOnly.append((OrigPath, MediaPath))

print(f"=== Summary ===")
print(f"BOTH (delete .orig):     {len(Both)}")
print(f"ORIG_ONLY (restore):     {len(OrigOnly)}")
print(f"TOTAL:                   {len(Both) + len(OrigOnly)}")
print()

if DryRun:
    print("[DRY RUN] Pass --execute to perform changes")
    print()

# Phase 1: Delete .orig where both exist
print(f"=== Phase 1: Delete .orig (both exist) ===")
DeleteOK = 0
DeleteFail = 0
for OrigPath, MediaPath in sorted(Both):
    if DryRun:
        print(f"  [DRY] Would delete: {OrigPath}")
    else:
        try:
            os.remove(OrigPath)
            print(f"  [OK] Deleted: {OrigPath}")
            DeleteOK += 1
        except Exception as E:
            print(f"  [FAIL] {OrigPath}: {E}")
            DeleteFail += 1

print()

# Phase 2: Restore .orig where media file is missing
print(f"=== Phase 2: Restore .orig (media file missing) ===")
RestoreOK = 0
RestoreFail = 0
for OrigPath, MediaPath in sorted(OrigOnly):
    if DryRun:
        print(f"  [DRY] Would rename: {OrigPath}")
        print(f"              -> {MediaPath}")
    else:
        try:
            os.rename(OrigPath, MediaPath)
            print(f"  [OK] Restored: {MediaPath}")
            RestoreOK += 1
        except Exception as E:
            print(f"  [FAIL] {OrigPath}: {E}")
            RestoreFail += 1

print()
if not DryRun:
    print(f"=== Results ===")
    print(f"Deleted:  {DeleteOK} OK, {DeleteFail} failed")
    print(f"Restored: {RestoreOK} OK, {RestoreFail} failed")
