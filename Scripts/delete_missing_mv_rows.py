"""Delete MediaFiles rows whose -mv.mp4 file was destroyed by the
2026-05-25 errant shell-glob delete. Read-only first, then commit on flag.

Scope: rows in the 5 affected shows whose FilePath ends in '-mv.mp4'
AND whose on-disk path (via WorkerContext resolution) is absent.

For each row, cascade-delete:
  - ActiveJobs (via TranscodeQueue.Id)
  - TemporaryFilePaths (via TranscodeAttempts.Id)
  - MediaFilesArchive (via TranscodeAttempts.Id)
  - TranscodeQueue
  - TranscodeAttempts
  - MediaFiles row itself

No file operations.
"""

import os, sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Tests.Pipeline.Harness.Invocation import _EnsureWorkerContext
_EnsureWorkerContext('I9-2024')

from Core.Database.DatabaseService import DatabaseService
from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
from Core.WorkerContext import WorkerContext

SHOWS = [
    'Adventure Time',
    'Ren & Stimpy',
    'Teenage Robot',
    'Animaniacs',
    'Gumball',
]

Db = DatabaseService()
ctx = WorkerContext.Current()
roots = LoadStorageRoots(Db)


def resolve(canonical):
    sr, rel = PathParse(canonical, roots)
    if sr is None or rel is None:
        return None
    return PathResolve(sr, rel, ctx.WorkerName, Db)


def cascade_delete(mediafile_id):
    Db.ExecuteNonQuery(
        "DELETE FROM ActiveJobs WHERE QueueId IN (SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s)",
        (mediafile_id,),
    )
    Db.ExecuteNonQuery(
        "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (mediafile_id,),
    )
    Db.ExecuteNonQuery(
        "DELETE FROM MediaFilesArchive WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (mediafile_id,),
    )
    Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (mediafile_id,))
    Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (mediafile_id,))
    Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (mediafile_id,))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--commit', action='store_true')
    args = p.parse_args()

    total_targeted = 0
    total_deleted = 0
    for show in SHOWS:
        rows = Db.ExecuteQuery(
            "SELECT Id, FilePath FROM MediaFiles WHERE FilePath ILIKE %s AND FilePath ILIKE %s",
            (f'%{show}%', '%-mv.mp4'),
        )
        missing = []
        for r in rows:
            local = resolve(r['FilePath'])
            if not local or not os.path.exists(local):
                missing.append((r['Id'], r['FilePath']))
        print(f"{show}: {len(rows)} -mv.mp4 rows, {len(missing)} have missing files")
        total_targeted += len(missing)

        if args.commit and missing:
            for mid, _ in missing:
                cascade_delete(mid)
                total_deleted += 1

    print()
    if args.commit:
        print(f"COMMITTED: deleted {total_deleted} rows (out of {total_targeted} targeted)")
    else:
        print(f"DRY RUN: would delete {total_targeted} rows. Re-run with --commit.")


if __name__ == '__main__':
    main()
