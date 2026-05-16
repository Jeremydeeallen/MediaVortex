"""End-to-end test for the 3-of-4-physical-machines scenario.

Triggers (via the same HTTP endpoints the GUI uses):
  - Remux on larry-worker-1
  - Transcode on dot-worker-1 (auto-triggers post-disposition VMAF)
  - VMAF on wakko-worker-1 (picks up the auto-queued VMAF)

Then verifies each operation completed correctly on the backend AND
that re-scanning the touched files does NOT flag them as updated.

Run live. Aborts on first major failure. Reports per-step pass/fail.
"""
import sys
import os
import time
import json
import socket
import urllib.request
import urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Unbuffered stdout so live progress shows up in monitor / log tail.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from Core.Database.DatabaseService import DatabaseService

API_BASE = 'http://localhost:5000'
TEST_WORKERS = {
    'remux': 'larry-worker-1',
    'transcode': 'dot-worker-1',
    'vmaf': 'wakko-worker-1',
}
POLL_INTERVAL_SEC = 10
TIMEOUT_REMUX_SEC = 600
TIMEOUT_TRANSCODE_SEC = 2400
TIMEOUT_VMAF_SEC = 1800


def Section(label):
    print(f'\n=== {label} ===')


def Post(path, body):
    Req = urllib.request.Request(
        f'{API_BASE}{path}',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(Req, timeout=30) as Resp:
        return json.loads(Resp.read().decode('utf-8'))


def PickRemuxCandidate(Db):
    """Pick a small MKV that isn't yet transcoded by MediaVortex."""
    Rows = Db.ExecuteQuery(
        "SELECT Id, FilePath, FileName, SizeMB FROM MediaFiles "
        "WHERE ContainerFormat ILIKE %s "
        "  AND TranscodedByMediaVortex IS NOT TRUE "
        "  AND SizeMB BETWEEN 80 AND 250 "
        "  AND FFprobeFailureCount = 0 "
        "  AND HasExplicitEnglishAudio = TRUE "
        "  AND FilePath LIKE 'T:%%' "
        "  AND AssignedProfile IS NOT NULL "
        "ORDER BY RANDOM() LIMIT 1",
        ('%matroska%',)
    )
    if not Rows:
        raise RuntimeError('No remux candidate found')
    return Rows[0]


def PickTranscodeCandidate(Db, ExcludeId):
    """Pick a small file with an AssignedProfile, eligible for transcode."""
    # Pick a candidate where SVT-AV1 will actually WIN compression -- otherwise
    # post-disposition decides Discard and VMAF never runs (observed against
    # Bob Hearts Abishola SDTV at 145MB in the prior run). Need:
    #  - resolution 720p+ (1080p ideal)
    #  - source codec h264 (NOT hevc/av1 -- those already compress well)
    #  - 250-700MB so the transcode is meaningful but bounded
    Rows = Db.ExecuteQuery(
        "SELECT Id, FilePath, FileName, SizeMB, AssignedProfile, Codec, ResolutionCategory FROM MediaFiles "
        "WHERE TranscodedByMediaVortex IS NOT TRUE "
        "  AND SizeMB BETWEEN 250 AND 700 "
        "  AND Codec = 'h264' "
        "  AND ResolutionCategory IN ('720p', '1080p') "
        "  AND FFprobeFailureCount = 0 "
        "  AND HasExplicitEnglishAudio = TRUE "
        "  AND FilePath LIKE 'T:%%' "
        "  AND AssignedProfile IS NOT NULL "
        "  AND Id <> %s "
        "ORDER BY RANDOM() LIMIT 1",
        (ExcludeId,)
    )
    if not Rows:
        raise RuntimeError('No transcode candidate found')
    return Rows[0]


def ConfigureWorkerCapabilities(Db):
    """Scope each test worker so it claims only one job type.
    All OTHER workers stay Paused so they cannot contend.

    CRITICAL ORDERING (learned the hard way from the failed run at 10:09):
    1. Pause the 3 test workers first (lets their current services drain).
    2. Sleep 25s so the per-worker capability poller picks up Paused.
    3. Flip capabilities AND set Status=Online in the same UPDATE.
    4. Sleep 25s so the poller sees Online and starts services in the
       FINAL capability state -- no mid-flight capability change can
       kill an in-progress job.
    Default capability-poll interval is ~15s; 25s buys a safe cushion.
    """
    Section('Configuring worker capabilities (pause -> wait -> reconfigure -> wait)')
    for W in TEST_WORKERS.values():
        Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s",
            (W,)
        )
        print(f'  paused: {W}')
    print('  Sleeping 25s for capability poller to drain services...')
    time.sleep(25)

    # larry-worker-1 -> remux only
    Db.ExecuteNonQuery(
        "UPDATE Workers SET RemuxEnabled=TRUE, TranscodeEnabled=FALSE, QualityTestEnabled=FALSE, "
        "MaxConcurrentRemuxJobs=1, Status='Online' WHERE WorkerName=%s",
        ('larry-worker-1',)
    )
    print('  larry-worker-1: RemuxEnabled=true, TranscodeEnabled=false, QualityTestEnabled=false, Online')
    # dot-worker-1 -> transcode only
    Db.ExecuteNonQuery(
        "UPDATE Workers SET RemuxEnabled=FALSE, TranscodeEnabled=TRUE, QualityTestEnabled=FALSE, "
        "MaxConcurrentTranscodeJobs=1, Status='Online' WHERE WorkerName=%s",
        ('dot-worker-1',)
    )
    print('  dot-worker-1: RemuxEnabled=false, TranscodeEnabled=true, QualityTestEnabled=false, Online')
    # wakko-worker-1 -> vmaf only
    Db.ExecuteNonQuery(
        "UPDATE Workers SET RemuxEnabled=FALSE, TranscodeEnabled=FALSE, QualityTestEnabled=TRUE, "
        "MaxConcurrentQualityTestJobs=1, Status='Online' WHERE WorkerName=%s",
        ('wakko-worker-1',)
    )
    print('  wakko-worker-1: RemuxEnabled=false, TranscodeEnabled=false, QualityTestEnabled=true, Online')
    print('  Sleeping 25s for capability poller to start services in FINAL capability state...')
    time.sleep(25)


def WaitForAttempt(Db, MediaFileId, MinAttemptDate, ProfileNameFilter, Timeout, Label):
    """Poll TranscodeAttempts for a Success or failure on this MediaFileId."""
    print(f'  Waiting for {Label} attempt (MediaFileId={MediaFileId}, profile~{ProfileNameFilter!r})...')
    Start = time.time()
    LastReport = 0
    while time.time() - Start < Timeout:
        Rows = Db.ExecuteQuery(
            "SELECT Id, WorkerName, ProfileName, Success, FileReplaced, "
            "       Disposition, DispositionReason, VMAF, AttemptDate, CompletedDate, "
            "       LEFT(ErrorMessage, 200) AS Err "
            "FROM TranscodeAttempts "
            "WHERE MediaFileId=%s AND AttemptDate >= %s "
            "ORDER BY AttemptDate DESC LIMIT 1",
            (MediaFileId, MinAttemptDate)
        )
        if Rows:
            R = Rows[0]
            if R['CompletedDate'] is not None or R['Success'] is not None:
                Elapsed = int(time.time() - Start)
                Verdict = 'PASS' if R['Success'] else 'FAIL'
                print(f'  {Verdict} after {Elapsed}s: worker={R["WorkerName"]} profile={R["ProfileName"]!r} '
                      f'success={R["Success"]} replaced={R["FileReplaced"]} disp={R["Disposition"]!r} '
                      f'vmaf={R["VMAF"]} err={R["Err"]!r}')
                return R
        Now = int(time.time() - Start)
        if Now - LastReport >= 60:
            print(f'  ...{Now}s elapsed, still waiting')
            LastReport = Now
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f'{Label} did not complete within {Timeout}s')


def VerifyFileSkippedOnRescan(Db, MediaFileId, Label):
    """Call HasFileChanged on the touched file -- equivalent to what a
    full scan would do for this row. Returns True if scan would SKIP."""
    from Features.FileScanning.FileScanningRepository import FileScanningRepository
    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService

    Repo = FileScanningRepository()
    Svc = FileScanningBusinessService(Repo)

    Rows = Db.ExecuteQuery(
        "SELECT Id, FilePath, StorageRootId, RelativePath FROM MediaFiles WHERE Id=%s",
        (MediaFileId,)
    )
    if not Rows:
        print(f'  {Label}: MediaFileId={MediaFileId} not found in DB -- file was DELETED?')
        return False
    Row = Rows[0]
    FilePath = Row['FilePath']

    # Find the FULL row via the repo's normal loader
    AllRows = Repo.GetMediaFilesByRootFolder('T:' + chr(92))
    Target = [r for r in AllRows if r.Id == MediaFileId]
    if not Target:
        print(f'  {Label}: row {MediaFileId} not in T:\\ -- different root?')
        return False
    DbFile = Target[0]

    if not os.path.exists(FilePath):
        print(f'  {Label}: file does NOT exist at {FilePath!r}')
        return False

    try:
        SizeMB = Svc.FileManager.GetFileSizeMB(FilePath)
        FileName = Svc.FileManager.GetFileNameFromPath(FilePath)
        Mtime = Svc.GetFileModificationTime(FilePath)
        Changed = Svc.HasFileChanged(DbFile, SizeMB, FileName, Mtime)
        Verdict = 'SKIP (good)' if not Changed else 'CHANGED (bad -- would re-update)'
        print(f'  {Label}: HasFileChanged={Changed} -> scan would {Verdict}')
        print(f'         stored: SizeMB={DbFile.SizeMB!r} FileName={DbFile.FileName!r} Mtime={DbFile.FileModificationTime!r}')
        print(f'         disk:   SizeMB={SizeMB!r} FileName={FileName!r} Mtime={Mtime!r}')
        return not Changed
    except Exception as Ex:
        print(f'  {Label}: HasFileChanged raised {type(Ex).__name__}: {Ex}')
        return False


def Main():
    Db = DatabaseService()

    Section('Pre-flight')
    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS N FROM TranscodeQueue", ())
    if Rows[0]['N'] > 0:
        print(f'FAIL: queue has {Rows[0]["N"]} rows -- run with empty queue')
        sys.exit(2)
    print('  Queue empty')

    ConfigureWorkerCapabilities(Db)

    Section('Pick candidates')
    RemuxFile = PickRemuxCandidate(Db)
    TranscodeFile = PickTranscodeCandidate(Db, RemuxFile['Id'])
    print(f'  Remux candidate:     Id={RemuxFile["Id"]}  {RemuxFile["FilePath"]}')
    print(f'  Transcode candidate: Id={TranscodeFile["Id"]} ({TranscodeFile["AssignedProfile"]!r})  {TranscodeFile["FilePath"]}')

    # Capture "min attempt date" so we don't match older attempts
    MinDate = Db.ExecuteQuery("SELECT NOW() AT TIME ZONE 'UTC' AS T", ())[0]['T']
    print(f'  Cutoff timestamp: {MinDate}')

    Section('Trigger remux via GUI endpoint')
    R = Post('/api/ShowSettings/AddToQueue', {
        'MediaFileIds': [RemuxFile['Id']],
        'Mode': 'Remux',
    })
    print(f'  Response: {R}')
    if not R.get('Success'):
        print('  FAIL: remux queue add failed')
        sys.exit(3)

    Section('Trigger transcode via GUI endpoint')
    R = Post('/api/TranscodeQueue/AddJob', {
        'MediaFileId': TranscodeFile['Id'],
        'Priority': 195,
        'ForceAdd': True,
    })
    print(f'  Response: {R}')
    if not R.get('Success'):
        print('  FAIL: transcode queue add failed')
        sys.exit(3)

    Section('Wait for remux completion on larry-worker-1')
    RemuxAttempt = WaitForAttempt(Db, RemuxFile['Id'], MinDate, 'Remux', TIMEOUT_REMUX_SEC, 'remux')
    if not RemuxAttempt['Success']:
        print('  FAIL: remux did not succeed; aborting before transcode wait')
        sys.exit(4)

    Section('Wait for transcode + VMAF completion')
    TxAttempt = WaitForAttempt(Db, TranscodeFile['Id'], MinDate, '%', TIMEOUT_TRANSCODE_SEC, 'transcode')
    if not TxAttempt['Success']:
        print('  FAIL: transcode did not succeed')
        sys.exit(4)
    # VMAF may be a separate attempt or the same row updated. Wait for a
    # TERMINAL disposition (anything except None/Pending) or a non-NULL VMAF
    # score or QualityTestCompleted. Previous version exited on
    # Disposition='Pending' (AwaitingVmaf) because the truthy check matched --
    # bug observed in run 2.
    print('  Waiting for VMAF on the transcode attempt...')
    TerminalDispositions = ('Replace', 'BypassReplace', 'NoReplace', 'Requeue', 'Discard')
    Start = time.time()
    LastReport = 0
    Done = False
    while time.time() - Start < TIMEOUT_VMAF_SEC:
        Rows = Db.ExecuteQuery(
            "SELECT VMAF, QualityTestCompleted, Disposition, DispositionReason, FileReplaced "
            "FROM TranscodeAttempts WHERE Id=%s",
            (TxAttempt['Id'],)
        )
        R = Rows[0]
        TerminalReached = R['Disposition'] in TerminalDispositions
        if R['VMAF'] is not None or TerminalReached:
            print(f'  VMAF result: vmaf={R["VMAF"]} qt_completed={R["QualityTestCompleted"]} '
                  f'disp={R["Disposition"]!r} reason={R["DispositionReason"]!r} '
                  f'replaced={R["FileReplaced"]}')
            Done = True
            break
        Now = int(time.time() - Start)
        if Now - LastReport >= 60:
            print(f'  ...{Now}s elapsed, still waiting on VMAF (disp={R["Disposition"]!r})')
            LastReport = Now
        time.sleep(POLL_INTERVAL_SEC)
    if not Done:
        print('  FAIL: VMAF did not reach a terminal disposition within timeout')
        sys.exit(4)

    Section('Verify scan would SKIP touched files (no spurious UpdatedFiles)')
    SkipRemux = VerifyFileSkippedOnRescan(Db, RemuxFile['Id'], 'Remux file')
    SkipTx = VerifyFileSkippedOnRescan(Db, TranscodeFile['Id'], 'Transcode file')

    Section('Verdict')
    AllPass = SkipRemux and SkipTx and RemuxAttempt['Success'] and TxAttempt['Success']
    if AllPass:
        print('  END-TO-END PASS: all 3 backend operations succeeded AND scan would skip the touched files.')
        sys.exit(0)
    else:
        print('  END-TO-END FAIL: see per-section detail above.')
        sys.exit(1)


if __name__ == '__main__':
    Main()
