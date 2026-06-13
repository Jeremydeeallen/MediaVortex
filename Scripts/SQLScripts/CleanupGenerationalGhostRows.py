"""Retire generational ghost MediaFile rows.

When a legacy lifecycle hole left an `.inprogress -> -mv.mp4` rename half-done last
week, a subsequent scan picked up the orphan `-mv.mp4` and created its
own MediaFile row. Meanwhile the original MediaFile row eventually
got re-processed into a `-mv-mv.mp4` canonical. Result: the same
episode now has two rows pointing at different generations in the same
directory -- the older one is a "ghost" the cascade has no reason to
touch but the disk-orphan cleanup can't catch because the row "claims"
the file.

Target pair shape (this script):
  ghost     -> ...basename-mv.mp4       (older generation, no successor link)
  canonical -> ...basename-mv-mv.mp4    (current generation)

Distinct from `CleanupOrphanMvPairs.py` which handles `.mkv -> -mv.mp4`
source-vs-output pairs.

Retire rule:
  - Ghost has zero TranscodeAttempts        -> straight DELETE
  - Ghost has TranscodeAttempts             -> re-parent attempts +
                                               cascade rows to the
                                               canonical, then DELETE
  - Ghost has AdmissionDeferReason set      -> KEEP_BOTH (operator
                                               parked this for review)

After retire, the ghost-referenced disk file becomes unreferenced;
`CleanupSourceFileOrphans.py` on its next run will pick it up.

Dry-run by default. Pass --commit to actually retire.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


# Match trailing "-mv" repetitions + ".mp4"; capture the chain so we can
# count generations.
MV_GEN_RE = re.compile(r'((?:-mv)+)\.mp4$', re.IGNORECASE)


def GenerationCount(FilePath: str) -> int:
    """0 means no -mv suffix, 1 means -mv.mp4, 2 means -mv-mv.mp4, etc."""
    M = MV_GEN_RE.search(FilePath)
    if not M:
        return 0
    return M.group(1).count('-mv')


def StrippedBase(FilePath: str) -> str:
    """File path with the entire -mv*.mp4 tail removed, lowercased."""
    M = MV_GEN_RE.search(FilePath)
    if not M:
        return FilePath.lower()
    return FilePath[:M.start()].lower()


def Main():
    Parser = argparse.ArgumentParser()
    Parser.add_argument('--commit', action='store_true', help='Actually retire (default: dry-run)')
    Parser.add_argument('--limit', type=int, default=None, help='Stop after N ghosts retired')
    Args = Parser.parse_args()

    Db = DatabaseService()

    print('Loading all -mv*.mp4 MediaFile rows ...')
    Rows = Db.ExecuteQuery(
        "SELECT Id, FilePath, AdmissionDeferReason FROM MediaFiles WHERE FilePath ILIKE %s",
        ('%-mv.mp4',),
    )
    print(f'  {len(Rows)} candidates')

    # Group by (lowercased stripped base). Each group's row with the highest
    # generation count is the canonical; the rest are ghost candidates.
    Groups = defaultdict(list)
    for R in Rows:
        Key = StrippedBase(R['FilePath'])
        Groups[Key].append({
            'Id': R['Id'],
            'FilePath': R['FilePath'],
            'Gen': GenerationCount(R['FilePath']),
            'AdmissionDeferReason': R.get('AdmissionDeferReason'),
        })

    # Filter to groups with multiple rows at differing generations
    GenerationalPairs = [
        Sorted for Sorted in (
            sorted(G, key=lambda R: R['Gen']) for G in Groups.values()
        )
        if len(Sorted) >= 2 and Sorted[0]['Gen'] < Sorted[-1]['Gen']
    ]
    print(f'  {len(GenerationalPairs)} generational pair groups')

    Retire = []        # ghost rows to delete outright
    ReParent = []      # ghost rows with attempts -- re-parent then delete
    KeepBoth = []      # parked for manual review or weird shape

    for Group in GenerationalPairs:
        Canonical = Group[-1]
        for Ghost in Group[:-1]:
            if Ghost['AdmissionDeferReason']:
                KeepBoth.append((Ghost, Canonical, f'AdmissionDeferReason={Ghost["AdmissionDeferReason"]!r}'))
                continue
            AttemptCount = Db.ExecuteQuery(
                "SELECT COUNT(*) AS c FROM TranscodeAttempts WHERE MediaFileId = %s",
                (Ghost['Id'],),
            )[0]['c']
            if AttemptCount == 0:
                Retire.append((Ghost, Canonical))
            else:
                ReParent.append((Ghost, Canonical, AttemptCount))
            if Args.limit and (len(Retire) + len(ReParent)) >= Args.limit:
                break
        if Args.limit and (len(Retire) + len(ReParent)) >= Args.limit:
            break

    print()
    print('=== RESULTS ===')
    print(f'Retire (no attempts, direct delete):     {len(Retire)}')
    print(f'Re-parent (has attempts, then delete):   {len(ReParent)}')
    print(f'Keep-both (parked for review):           {len(KeepBoth)}')
    print()
    for Ghost, Canonical in Retire[:8]:
        print(f'  RETIRE ghost Id={Ghost["Id"]} gen={Ghost["Gen"]} -> canonical Id={Canonical["Id"]} gen={Canonical["Gen"]}')
        print(f'         {Ghost["FilePath"]}')
    if len(Retire) > 8:
        print(f'  ... and {len(Retire) - 8} more retire')
    for Ghost, Canonical, AC in ReParent[:5]:
        print(f'  RE-PARENT ghost Id={Ghost["Id"]} ({AC} attempts) -> canonical Id={Canonical["Id"]}')
    if len(ReParent) > 5:
        print(f'  ... and {len(ReParent) - 5} more re-parent')
    for Ghost, Canonical, Reason in KeepBoth[:3]:
        print(f'  KEEP_BOTH Id={Ghost["Id"]}: {Reason}')

    if not Args.commit:
        print()
        print('DRY RUN. Pass --commit to apply.')
        return

    print()
    print('--commit set. Applying ...')
    Done = 0
    Failed = 0
    for Ghost, Canonical in Retire:
        try:
            Db.ExecuteNonQuery('DELETE FROM MediaFiles WHERE Id = %s', (Ghost['Id'],))
            Done += 1
        except Exception as Ex:
            Failed += 1
            print(f'  FAILED retire {Ghost["Id"]}: {Ex}')
    for Ghost, Canonical, _ in ReParent:
        try:
            # Re-parent TranscodeAttempts. Downstream MediaFilesArchive +
            # TemporaryFilePaths reference TranscodeAttempt rows, not the
            # MediaFile directly, so they follow automatically.
            Db.ExecuteNonQuery(
                'UPDATE TranscodeAttempts SET MediaFileId = %s WHERE MediaFileId = %s',
                (Canonical['Id'], Ghost['Id']),
            )
            Db.ExecuteNonQuery('DELETE FROM MediaFiles WHERE Id = %s', (Ghost['Id'],))
            Done += 1
        except Exception as Ex:
            Failed += 1
            print(f'  FAILED re-parent {Ghost["Id"]}: {Ex}')
    print(f'Applied to {Done} ghost rows, {Failed} failures.')
    print('Next CleanupSourceFileOrphans.py run will sweep the now-unreferenced disk files.')


if __name__ == '__main__':
    Main()
