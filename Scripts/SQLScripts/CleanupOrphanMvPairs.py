#!/usr/bin/env python3
r"""
CleanupOrphanMvPairs.py
Restores the designed FileReplacement end-state for MediaFiles row pairs
that BUG-0013 left in drift: one row pointing at a .mkv source and a
second row pointing at the -mv.mp4 post-Quick-Fix output, both on disk.

Per the design contract (FileReplacement.feature.md + worker-lifecycle):
a successful Quick Fix should leave ONE MediaFiles row whose FilePath
has been rewritten to the -mv.mp4, the source file deleted from disk,
the audit trail captured in TranscodeAttempts + MediaFilesArchive.

These pairs are drift from that contract. This script restores it via
an audit-gated retirement: delete the source row AND the source file
ONLY when a successful TranscodeAttempts row proves the -mv.mp4 came
from the source through a real pipeline run.

Audit gate per pair (all must hold to retire the source):

  1. Source path has a non-mp4 extension (.mkv, .avi, etc.)
  2. -mv.mp4 path on disk exists, non-zero size
  3. TranscodeAttempts has a row for the source MediaFileId with
     Success=true AND FileReplaced=true
  4. That TranscodeAttempts row's FfpmpegCommand references the
     -mv.mp4 output filename (proof the attempt produced THIS file)

Pairs where ALL four hold are classified RETIRE -- delete the source
MediaFiles ROW (resolves UniqueViolation, lets Quick Fix run again).
**File on disk is NEVER deleted** -- spot-checks on real candidates
2026-05-25 showed 3 of 5 -mv.mp4 files had off-target audio from
BUG-0013-era runs (Pokemon at -18 LUFS + clipping, Office at -32 LUFS).
The .mkv source is the only safe copy of correctly-mastered audio for
those cases. A future LUFS-verified retire script can reclaim disk
space once new (BUG-0013-fixed) Quick Fix runs produce correct
outputs; until then the source files stay.

Pairs that fail ANY audit check are KEEP_BOTH -- preserve both as-is.

Dry-run by default. --commit applies DB-row deletes only.

Usage:
  py Scripts/SQLScripts/CleanupOrphanMvPairs.py [--commit] [--worker-name I9-2024] [--limit N]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


def _InitWorkerContext(WorkerName: str) -> None:
    from Core.WorkerContext import WorkerContext
    if WorkerContext.Current() is not None:
        return
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT FFmpegPath, FFprobePath, Platform FROM Workers WHERE WorkerName = %s",
        (WorkerName,),
    )
    if not Rows:
        print(f"ERROR: Worker {WorkerName!r} not in Workers table.", file=sys.stderr)
        sys.exit(2)
    W = Rows[0]
    MountRows = Db.ExecuteQuery(
        "SELECT DriveLetter, LocalMountPrefix FROM WorkerShareMappings WHERE WorkerName = %s",
        (WorkerName,),
    )
    MountMap = {M['DriveLetter']: M['LocalMountPrefix'] for M in MountRows}
    WorkerContext.Initialize(
        WorkerName=WorkerName,
        Platform=W.get('Platform') or 'windows',
        FFmpegPath=W.get('FFmpegPath'),
        FFprobePath=W.get('FFprobePath'),
        ShareMappings=MountMap,
    )


def _ResolveLocal(CanonicalPath: str) -> Optional[str]:
    try:
        from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
        from Core.WorkerContext import WorkerContext
        Db = DatabaseService()
        SrId, Rel = PathParse(CanonicalPath, LoadStorageRoots(Db))
        Ctx = WorkerContext.Current()
        if SrId is not None and Rel is not None and Ctx is not None:
            return PathResolve(SrId, Rel, Ctx.WorkerName, Db)
    except Exception:
        return None
    return None


def _FetchPairs(Db: DatabaseService, Limit: Optional[int]) -> list:
    """Pairs where A is the non-mp4 source and B is the -mv.mp4 variant."""
    Limit_clause = f"LIMIT {int(Limit)}" if Limit else ""
    Rows = Db.ExecuteQuery(
        f"""
        SELECT a.Id AS AId, a.FilePath AS APath,
               b.Id AS BId, b.FilePath AS BPath
        FROM MediaFiles a
        JOIN MediaFiles b ON LOWER(b.FilePath) = LOWER(
            SUBSTRING(a.FilePath FROM 1 FOR LENGTH(a.FilePath) - LENGTH(
                SUBSTRING(a.FilePath FROM E'\\.[^.\\\\/]+$')
            )) || '-mv.mp4'
        )
        WHERE a.Id != b.Id
          AND a.FilePath NOT LIKE %s
          AND a.FilePath NOT LIKE %s
        ORDER BY a.Id
        {Limit_clause}
        """,
        ('%-mv.mp4', '%-mv-mv.mp4'),
    )
    return [(int(R['AId']), R['APath'], int(R['BId']), R['BPath']) for R in Rows]


def _AuditPair(Db: DatabaseService, AId: int, APath: str, BPath: str,
               ALocal: Optional[str], BLocal: Optional[str]) -> Tuple[str, str]:
    """Run the 4-criterion audit. Return (decision, reason)."""
    # Gate 1: source has a non-mp4 extension (.mkv, .avi, etc.) -- if A
    # is itself an .mp4, the pair is less clear (could be a transcode
    # output that's already canonical), skip with KEEP_BOTH.
    AExt = os.path.splitext(APath)[1].lower()
    if AExt == '.mp4':
        return ('KEEP_BOTH', 'A is .mp4, not a clear source-vs-output pair')

    # Gate 2: -mv.mp4 file actually on disk, non-zero
    if not BLocal:
        return ('KEEP_BOTH', 'B path does not resolve via PathStorage for this worker')
    if not os.path.exists(BLocal):
        return ('KEEP_BOTH', f'B file not present on disk: {BLocal}')
    try:
        if os.path.getsize(BLocal) <= 0:
            return ('KEEP_BOTH', f'B file is empty: {BLocal}')
    except OSError as Ex:
        return ('KEEP_BOTH', f'B file stat failed: {Ex}')

    # Gate 3: TranscodeAttempts has Success=true + FileReplaced=true for A
    AuditRows = Db.ExecuteQuery(
        "SELECT Id, FfpmpegCommand FROM TranscodeAttempts "
        "WHERE MediaFileId = %s AND Success = TRUE AND FileReplaced = TRUE "
        "ORDER BY AttemptDate DESC",
        (AId,),
    )
    if not AuditRows:
        return ('KEEP_BOTH',
                'no TranscodeAttempts row with Success=true AND FileReplaced=true for A')

    # Gate 4: at least one of those rows references the -mv.mp4 output
    # filename in its FFmpeg command (proves the attempt produced THIS file)
    BBasename = os.path.basename(BPath)
    Matched = any(
        R.get('FfpmpegCommand') and BBasename in (R.get('FfpmpegCommand') or '')
        for R in AuditRows
    )
    if not Matched:
        return ('KEEP_BOTH',
                f'A has Success+FileReplaced attempts but none reference {BBasename!r} '
                f'in the FFmpeg command')

    return ('RETIRE', f'A has {len(AuditRows)} successful FileReplaced attempt(s); '
                      f'at least one references {BBasename!r}')


def _DeleteMediaFile(Db: DatabaseService, MediaFileId: int) -> None:
    """Cascade-delete a MediaFile row and all rows that reference it.

    Use this for orphans -- when there is no surviving sibling that history
    should re-parent to. For RETIRE (which has a surviving sibling B),
    use _RetireSourceRow instead.
    """
    Db.ExecuteNonQuery(
        "DELETE FROM ActiveJobs WHERE QueueId IN "
        "(SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    Db.ExecuteNonQuery(
        "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId IN "
        "(SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    Db.ExecuteNonQuery(
        "DELETE FROM MediaFilesArchive WHERE TranscodeAttemptId IN "
        "(SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (MediaFileId,))


def _RetireSourceRow(Db: DatabaseService, SourceId: int, KeptId: int) -> None:
    """Restore the designed end-state for a coexistence pair.

    Re-parents TranscodeAttempts (and via them, MediaFilesArchive +
    TemporaryFilePaths) from the source MediaFile to the surviving
    -mv.mp4 MediaFile, then deletes the source row. The audit trail
    that documented the .mkv -> -mv.mp4 transition now lives with the
    surviving row, which is the designed final state described in
    FileReplacement.feature.md.

    TranscodeQueue and ActiveJobs rows pointing at the source are
    transient and not part of the audit trail -- those are dropped.
    """
    # Drop transient rows
    Db.ExecuteNonQuery(
        "DELETE FROM ActiveJobs WHERE QueueId IN "
        "(SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s)",
        (SourceId,),
    )
    Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (SourceId,))

    # Re-parent the audit trail. MediaFilesArchive + TemporaryFilePaths
    # link via TranscodeAttemptId, so they follow automatically.
    Db.ExecuteNonQuery(
        "UPDATE TranscodeAttempts SET MediaFileId = %s WHERE MediaFileId = %s",
        (KeptId, SourceId),
    )

    # Source row is now safe to delete
    Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (SourceId,))


def Run(Commit: bool, WorkerName: str, Limit: Optional[int]) -> int:
    _InitWorkerContext(WorkerName)
    Db = DatabaseService()
    Pairs = _FetchPairs(Db, Limit)
    print(f"Found {len(Pairs)} candidate pair(s){' (limited)' if Limit else ''}")
    print()

    Actions: Counter = Counter()
    KeepReasons: Counter = Counter()
    Plan: list = []
    Examples: dict = {}

    for AId, APath, BId, BPath in Pairs:
        ALocal = _ResolveLocal(APath)
        BLocal = _ResolveLocal(BPath)
        AExists = bool(ALocal and os.path.exists(ALocal))
        BExists = bool(BLocal and os.path.exists(BLocal))

        # Drift sub-cases that don't need the audit gate
        if not AExists and BExists:
            Decision, Reason = ('DELETE_A_ROW_ONLY', 'A file already gone; B canonical')
        elif AExists and not BExists:
            Decision, Reason = ('DELETE_B_ROW_ONLY', 'B file gone; B row is orphan')
        elif not AExists and not BExists:
            Decision, Reason = ('DELETE_BOTH_ROWS', 'both files gone; lost media')
        else:
            # Both files exist -- run the audit gate
            Decision, Reason = _AuditPair(Db, AId, APath, BPath, ALocal, BLocal)

        Actions[Decision] += 1
        if Decision == 'KEEP_BOTH':
            # Bucket the reason for visibility
            ReasonKey = Reason.split(':')[0].split('--')[0][:50]
            KeepReasons[ReasonKey] += 1

        Plan.append((AId, APath, ALocal, BId, BPath, BLocal, Decision, Reason))
        if Decision not in Examples:
            Examples[Decision] = (AId, APath, BId, BPath, Reason)

    def Short(p: str) -> str:
        return ('...' + p[-80:]) if p and len(p) > 80 else (p or '')

    print("Decision summary:")
    for Dec in ('RETIRE', 'DELETE_A_ROW_ONLY', 'DELETE_B_ROW_ONLY',
                'DELETE_BOTH_ROWS', 'KEEP_BOTH'):
        Count = Actions.get(Dec, 0)
        print(f"  {Dec:20s}  {Count:5d}")
        if Dec in Examples:
            AId, APath, BId, BPath, Reason = Examples[Dec]
            print(f"                       e.g. A={AId} ({Short(APath)})")
            print(f"                            B={BId} ({Short(BPath)})")
            print(f"                            reason: {Reason}")
    print()

    if KeepReasons:
        print("KEEP_BOTH breakdown:")
        for Reason, Count in KeepReasons.most_common():
            print(f"  {Count:5d}  {Reason}")
        print()

    # Effect summary
    Retires = Actions.get('RETIRE', 0)
    DeleteAOnly = Actions.get('DELETE_A_ROW_ONLY', 0)
    DeleteBOnly = Actions.get('DELETE_B_ROW_ONLY', 0)
    DeleteBoth = Actions.get('DELETE_BOTH_ROWS', 0)
    print("If applied:")
    print(f"  Source rows deleted from DB: {Retires + DeleteAOnly + DeleteBoth}")
    print(f"  -mv.mp4 rows deleted from DB: {DeleteBOnly + DeleteBoth}")
    print(f"  Files deleted from disk:     0  (script never deletes files)")
    print(f"  Files left untouched:        {len(Pairs) * 2 - DeleteAOnly}")
    print()

    if not Commit:
        print("DRY RUN. Re-run with --commit to apply.")
        return 0

    if Retires + DeleteAOnly + DeleteBOnly + DeleteBoth == 0:
        print("Nothing to delete. Done.")
        return 0

    print(f"Applying...")
    DeletedRows = 0
    DeletedFiles = 0
    Errors = 0
    for AId, APath, ALocal, BId, BPath, BLocal, Decision, _Reason in Plan:
        try:
            if Decision == 'RETIRE':
                # Re-parent the audit trail to the surviving -mv.mp4 row,
                # then delete the source row. File on disk untouched --
                # the .mkv stays as the safe copy of original audio.
                _RetireSourceRow(Db, AId, BId)
                DeletedRows += 1
            elif Decision == 'DELETE_A_ROW_ONLY':
                # Same as RETIRE -- B is canonical, A is gone from disk.
                # Re-parent the audit trail so history survives.
                _RetireSourceRow(Db, AId, BId)
                DeletedRows += 1
            elif Decision == 'DELETE_B_ROW_ONLY':
                _DeleteMediaFile(Db, BId)
                DeletedRows += 1
            elif Decision == 'DELETE_BOTH_ROWS':
                _DeleteMediaFile(Db, AId)
                _DeleteMediaFile(Db, BId)
                DeletedRows += 2
        except Exception as Ex:
            Errors += 1
            print(f"  ERROR on pair A={AId} B={BId}: {Ex}")

    print(f"Done. {DeletedRows} row(s) deleted, 0 file(s) touched, errors={Errors}.")
    return 0 if Errors == 0 else 1


def Main():
    P = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    P.add_argument('--commit', action='store_true', help='Actually delete (default: dry run)')
    P.add_argument('--worker-name', default='I9-2024',
                   help='Worker for path translation (default: I9-2024)')
    P.add_argument('--limit', type=int, default=None, help='Cap pairs (for testing)')
    Args = P.parse_args()
    sys.exit(Run(Args.commit, Args.worker_name, Args.limit))


if __name__ == '__main__':
    Main()
