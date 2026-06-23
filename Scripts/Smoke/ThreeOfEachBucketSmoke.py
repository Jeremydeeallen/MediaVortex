import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: filereplacement-drain-bug
POLL_INTERVAL_SECONDS = 30
MAX_WAIT_MINUTES = 60


# directive: filereplacement-drain-bug
def _PickCandidates(Db, Bucket, Limit=3):
    Sql = (
        "SELECT m.Id FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE m.WorkBucket = %s "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "AND m.HasExplicitEnglishAudio = TRUE "
        "AND m.SizeMB BETWEEN 80 AND 350 "
        "AND (m.AudioCorruptSuspect IS NULL OR m.AudioCorruptSuspect = FALSE) "
        "AND m.SourceIntegratedLufs IS NOT NULL "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (Bucket, Limit * 5))
    return [int(R['id']) for R in Rows[:Limit]]


# directive: filereplacement-drain-bug
def _QueueAll(Mids):
    Qmbs = QueueManagementBusinessService()
    Queued = []
    for Mid in Mids:
        R = Qmbs.AddJobToQueue(MediaFileId=Mid, Priority=150, ForceAdd=True)
        if R.get('Success'):
            Queued.append(Mid)
            print(f"  queued {Mid} -> Queue.Id={R.get('ItemId')}")
        else:
            print(f"  FAILED to queue {Mid}: {R.get('ErrorMessage')}")
    return Queued


# directive: filereplacement-drain-bug
def _Snapshot(Db, Mids):
    if not Mids:
        return {}
    Placeholders = ",".join(["%s"] * len(Mids))
    Rows = Db.ExecuteQuery(
        f"SELECT Id, WorkBucket, IsCompliant FROM MediaFiles WHERE Id IN ({Placeholders})",
        tuple(Mids),
    )
    return {int(R['id']): R for R in Rows}


# directive: filereplacement-drain-bug
def _StillQueued(Db, Mids):
    if not Mids:
        return set()
    Placeholders = ",".join(["%s"] * len(Mids))
    Rows = Db.ExecuteQuery(
        f"SELECT DISTINCT MediaFileId FROM TranscodeQueue WHERE MediaFileId IN ({Placeholders}) AND Status IN ('Pending','Running')",
        tuple(Mids),
    )
    return {int(R['mediafileid']) for R in Rows}


# directive: filereplacement-drain-bug
def Run():
    Db = DatabaseService()

    print("--- Picking candidates ---")
    TranscodeMids = _PickCandidates(Db, 'Transcode', 3)
    RemuxMids = _PickCandidates(Db, 'Remux', 3)
    AudioFixMids = _PickCandidates(Db, 'AudioFixOnly', 3)
    All = TranscodeMids + RemuxMids + AudioFixMids
    print(f"  Transcode={TranscodeMids}")
    print(f"  Remux={RemuxMids}")
    print(f"  AudioFix={AudioFixMids}")
    if len(All) != 9:
        print(f"FATAL: only found {len(All)}/9 candidates; aborting")
        sys.exit(1)

    print("\n--- Queuing 9 jobs ---")
    Queued = _QueueAll(All)
    if len(Queued) != 9:
        print(f"FATAL: only queued {len(Queued)}/9; aborting")
        sys.exit(1)

    print("\n--- Polling until terminal ---")
    Started = time.time()
    while True:
        Elapsed = (time.time() - Started) / 60.0
        InQueue = _StillQueued(Db, Queued)
        Snap = _Snapshot(Db, Queued)
        Compliant = sum(1 for Mid in Queued if Snap.get(Mid, {}).get('iscompliant') is True)
        Print = f"  t+{Elapsed:.1f}min: {len(InQueue)} still in queue, {Compliant}/9 compliant"
        print(Print)
        if not InQueue:
            break
        if Elapsed >= MAX_WAIT_MINUTES:
            print(f"TIMEOUT after {MAX_WAIT_MINUTES} minutes; bailing")
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    print("\n--- Final per-file outcomes ---")
    Snap = _Snapshot(Db, Queued)
    Compliant = 0
    for Group, Mids in (('Transcode', TranscodeMids), ('Remux', RemuxMids), ('AudioFix', AudioFixMids)):
        print(f"  {Group}:")
        for Mid in Mids:
            S = Snap.get(Mid, {})
            Bucket = S.get('workbucket')
            IsComp = S.get('iscompliant')
            Mark = 'PASS' if IsComp is True else 'FAIL'
            print(f"    {Mid}: bucket={Bucket} iscompliant={IsComp} -> {Mark}")
            if IsComp is True:
                Compliant += 1

    print(f"\nSummary: {Compliant}/9 compliant")
    if Compliant == 9:
        print("OK -- 3-of-each-bucket smoke PASSED")
        sys.exit(0)
    else:
        print("FAIL -- not all 9 became compliant")
        sys.exit(1)


if __name__ == '__main__':
    Run()
