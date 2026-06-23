import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: filereplacement-drain-bug
POLL_INTERVAL_SECONDS = 30
MAX_WAIT_MINUTES = 60


# directive: filereplacement-drain-bug
BUCKET_TO_PROCESSING_MODE = {
    'Transcode': 'Transcode',
    'Remux': 'Remux',
    'AudioFixOnly': 'AudioFix',
}


# directive: worker-runtime-state
def _PickCandidates(Db, Bucket, MinSizeMB, MaxSizeMB, MinVideoKbps, Limit=3):
    Sql = (
        "SELECT m.Id, m.FileName, m.SizeMB, m.VideoBitrateKbps FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE m.WorkBucket = %s "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "AND m.HasExplicitEnglishAudio = TRUE "
        "AND m.SizeMB BETWEEN %s AND %s "
        "AND (m.VideoBitrateKbps IS NULL OR m.VideoBitrateKbps >= %s) "
        "AND (m.AudioCorruptSuspect IS NULL OR m.AudioCorruptSuspect = FALSE) "
        "AND m.SourceIntegratedLufs IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = m.Id AND tq.Status IN ('Pending','Running')) "
        "ORDER BY m.SizeMB DESC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (Bucket, MinSizeMB, MaxSizeMB, MinVideoKbps, Limit))
    return [{'id': int(R['id']), 'filename': R['filename'], 'size_mb': float(R['sizemb']), 'video_kbps': R['videobitratekbps']} for R in Rows]


# directive: filereplacement-drain-bug
def _InsertQueueRow(Db, MfRow, ProcessingMode):
    SizeBytes = int(MfRow['size_mb'] * 1024 * 1024)
    Db.ExecuteNonQuery(
        "INSERT INTO TranscodeQueue "
        "(FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, ProcessingMode, MediaFileId, StorageRootId, RelativePath) "
        "SELECT FileName, '', %s, SizeMB, 200, 'Pending', NOW(), %s, %s, StorageRootId, RelativePath "
        "FROM MediaFiles WHERE Id = %s",
        (SizeBytes, ProcessingMode, MfRow['id'], MfRow['id']),
    )


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
    Transcode = _PickCandidates(Db, 'Transcode', MinSizeMB=200, MaxSizeMB=600, MinVideoKbps=2500, Limit=3)
    Remux = _PickCandidates(Db, 'Remux', MinSizeMB=80, MaxSizeMB=600, MinVideoKbps=0, Limit=3)
    AudioFix = _PickCandidates(Db, 'AudioFixOnly', MinSizeMB=80, MaxSizeMB=600, MinVideoKbps=0, Limit=3)
    print(f"  Transcode: {[r['id'] for r in Transcode]} (sizes: {[round(r['size_mb']) for r in Transcode]} MB)")
    print(f"  Remux:     {[r['id'] for r in Remux]} (sizes: {[round(r['size_mb']) for r in Remux]} MB)")
    print(f"  AudioFix:  {[r['id'] for r in AudioFix]} (sizes: {[round(r['size_mb']) for r in AudioFix]} MB)")
    AllRows = Transcode + Remux + AudioFix
    AllMids = [r['id'] for r in AllRows]
    if len(AllRows) != 9:
        print(f"FATAL: only found {len(AllRows)}/9 candidates; aborting")
        sys.exit(1)

    print("\n--- Inserting 9 queue rows with correct ProcessingMode ---")
    for R in Transcode:
        _InsertQueueRow(Db, R, 'Transcode')
        print(f"  queued MediaFile {R['id']} as Transcode")
    for R in Remux:
        _InsertQueueRow(Db, R, 'Remux')
        print(f"  queued MediaFile {R['id']} as Remux")
    for R in AudioFix:
        _InsertQueueRow(Db, R, 'AudioFix')
        print(f"  queued MediaFile {R['id']} as AudioFix")

    print("\n--- Polling until terminal ---")
    Started = time.time()
    while True:
        Elapsed = (time.time() - Started) / 60.0
        InQueue = _StillQueued(Db, AllMids)
        Snap = _Snapshot(Db, AllMids)
        Compliant = sum(1 for Mid in AllMids if Snap.get(Mid, {}).get('iscompliant') is True)
        print(f"  t+{Elapsed:.1f}min: {len(InQueue)} still in queue, {Compliant}/9 compliant")
        if not InQueue:
            break
        if Elapsed >= MAX_WAIT_MINUTES:
            print(f"TIMEOUT after {MAX_WAIT_MINUTES} minutes; bailing")
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    print("\n--- Final per-file outcomes ---")
    Snap = _Snapshot(Db, AllMids)
    Compliant = 0
    Groups = [('Transcode', Transcode), ('Remux', Remux), ('AudioFix', AudioFix)]
    for GroupName, Rows in Groups:
        print(f"  {GroupName}:")
        for R in Rows:
            Mid = R['id']
            S = Snap.get(Mid, {})
            Bucket = S.get('workbucket')
            IsComp = S.get('iscompliant')
            Mark = 'PASS' if IsComp is True else 'FAIL'
            FnShort = R['filename'][:55] if R['filename'] else '?'
            print(f"    {Mid} {FnShort}: bucket={Bucket} iscompliant={IsComp} -> {Mark}")
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
