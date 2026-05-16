"""Backfill MediaFiles.FileName where Linux-worker writes corrupted it with the full FilePath.

Root cause (now fixed in Services/FileManagerService.py::GetFileNameFromPath):
Linux's os.path.basename does not recognize '\' as a separator. Workers
running on Linux that received a Windows-shaped canonical FilePath
(e.g. 'T:\\Show\\file.mkv') stored the ENTIRE path as FileName instead
of just the basename. The result: 91,588 of 102,576 MediaFiles rows had
FileName == FilePath, which caused HasFileChanged to return True on every
cross-worker scan (NameChanged check failed) and trigger spurious full-row
UPDATEs (criterion 26 side effect, exposed once the mtime drift was fixed).

This script repairs the column once. After it runs, redeploy workers with
the corrected GetFileNameFromPath so new writes don't re-corrupt.

Idempotent: only updates rows where the computed basename differs from the
stored FileName. Safe to re-run.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def ExtractBasename(FilePath: str) -> str:
    """OS-agnostic basename: treat both '/' and '\\' as separators."""
    if not FilePath:
        return ''
    Normalized = FilePath.replace('\\', '/')
    return Normalized.rsplit('/', 1)[-1]


def Run(DryRun: bool = False):
    Db = DatabaseService()
    print('=== Identifying rows that need repair ===')
    # Pull all rows that have a FilePath, decide repair in Python.
    # Avoids fragile SQL escaping of backslashes through bash + psycopg2.
    Rows = Db.ExecuteQuery(
        "SELECT Id, FilePath, FileName FROM MediaFiles WHERE FilePath IS NOT NULL"
    )
    print(f'Total rows with a FilePath: {len(Rows)}')

    Repairs = []
    AlreadyCorrect = 0
    for R in Rows:
        FilePath = R['FilePath']
        Current = R['FileName']
        Expected = ExtractBasename(FilePath)
        if Current == Expected:
            AlreadyCorrect += 1
            continue
        Repairs.append((R['Id'], Expected))

    print(f'Already correct (no-op):       {AlreadyCorrect}')
    print(f'Rows needing repair:           {len(Repairs)}')

    if not Repairs:
        print('Nothing to do.')
        return

    if DryRun:
        print('\n=== DRY RUN -- showing first 5 repairs, not committing ===')
        for (Id, NewName) in Repairs[:5]:
            print(f'  Id={Id}  ->  FileName={NewName!r}')
        return

    print(f'\n=== Repairing {len(Repairs)} rows (batched 5000 per transaction) ===')
    Batch = 5000
    Done = 0
    for i in range(0, len(Repairs), Batch):
        Chunk = Repairs[i:i + Batch]
        for (Id, NewName) in Chunk:
            Db.ExecuteNonQuery(
                "UPDATE MediaFiles SET FileName = %s WHERE Id = %s",
                (NewName, Id),
            )
        Done += len(Chunk)
        print(f'  ...{Done}/{len(Repairs)}')

    print(f'\nDone. {Done} rows repaired.')


if __name__ == '__main__':
    DryRun = '--dry-run' in sys.argv
    Run(DryRun=DryRun)
