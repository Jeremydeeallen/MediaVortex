"""Set up the 1-per-physical-machine remux test.

Adds 4 remux jobs to TranscodeQueue, configures the 4 test workers
(larry-worker-1, wakko-worker-1, dot-worker-1, I9-2024) to claim one
each. Other workers stay Paused.
"""
import sys
import os
import ntpath
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService

CANDIDATE_IDS = [8330, 7011, 8211, 22678]
TEST_WORKERS = ['larry-worker-1', 'wakko-worker-1', 'dot-worker-1', 'I9-2024']


def Run():
    Db = DatabaseService()

    # 1. Sanity: queue should be empty
    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS N FROM TranscodeQueue")
    Existing = Rows[0]['N']
    if Existing > 0:
        print(f"FAIL: TranscodeQueue already has {Existing} rows. Refusing to add to a non-empty queue.")
        return

    # 2. Set MaxConcurrentRemuxJobs=1 on the 4 test workers
    print('=== Setting MaxConcurrentRemuxJobs=1 on test workers ===')
    for W in TEST_WORKERS:
        Db.ExecuteNonQuery(
            "UPDATE Workers SET MaxConcurrentRemuxJobs = 1 WHERE WorkerName = %s",
            (W,)
        )
        print(f'  {W} -> MaxConcurrentRemuxJobs=1')

    # 3. Enable Remux on I9-2024 (Larry/Wakko/Dot already RemuxEnabled=true)
    Db.ExecuteNonQuery(
        "UPDATE Workers SET RemuxEnabled = TRUE WHERE WorkerName = 'I9-2024'"
    )
    print('  I9-2024 -> RemuxEnabled=true')

    # 4. Add 4 remux jobs (one per candidate) -- worker claim is opportunistic;
    #    with only 4 workers Online (next step) and each capped at 1, each
    #    worker should claim exactly one.
    print()
    print('=== Adding 4 remux jobs ===')
    for Cid in CANDIDATE_IDS:
        Rows = Db.ExecuteQuery(
            "SELECT FilePath, FileName, FileSize, SizeMB FROM MediaFiles WHERE Id = %s",
            (Cid,)
        )
        R = Rows[0]
        FilePath = R['FilePath']
        Directory = ntpath.dirname(FilePath)
        Db.ExecuteNonQuery(
            """INSERT INTO TranscodeQueue
                (FilePath, FileName, Directory, SizeBytes, SizeMB,
                 Priority, Status, ProcessingMode, MediaFileId, DateAdded)
            VALUES (%s, %s, %s, %s, %s, 100, 'queued', 'Remux', %s, NOW())""",
            (FilePath, R['FileName'], Directory,
             R['FileSize'] or int((R['SizeMB'] or 0) * 1024 * 1024),
             R['SizeMB'] or 0, Cid)
        )
        print(f'  queued: {FilePath}')

    # 5. Flip the 4 test workers to Online
    print()
    print('=== Flipping test workers to Online ===')
    for W in TEST_WORKERS:
        Db.ExecuteNonQuery(
            "UPDATE Workers SET Status = 'Online' WHERE WorkerName = %s",
            (W,)
        )
        print(f'  {W} -> Online')

    print()
    print('=== DONE. Capability poller will pick up changes within ~15s. ===')


if __name__ == '__main__':
    Run()
