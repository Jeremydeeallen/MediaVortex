# directive: partial-pipeline-completion | # see transcode.D13
"""Smoke: drive the partial-completion code path end-to-end against live DB."""
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Features.TranscodeJob.Worker import PartialCompletion
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


def PickIdleMvTerminalMediaFileId(Db):
    Rows = Db.ExecuteQuery(
        "SELECT mf.Id FROM MediaFiles mf "
        "WHERE mf.TranscodedByMediaVortex=TRUE "
        "  AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId=mf.Id AND tq.Status IN ('Pending','Running')) "
        "  AND NOT EXISTS (SELECT 1 FROM TranscodeAttempts ta WHERE ta.MediaFileId=mf.Id AND ta.Success IS NULL) "
        "LIMIT 1"
    )
    if not Rows:
        raise RuntimeError("No idle MV-terminal MediaFile found for smoke")
    return int(Rows[0]['Id'])


def CreateSyntheticParent(Db, MediaFileId, DispositionReason):
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    Cur.execute(
        "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, Disposition, DispositionReason, ProfileName, WorkerName, ErrorMessage) "
        "VALUES (%s, NOW(), TRUE, 'Replace', %s, 'SMOKE-partial-completion', 'smoke-tester', 'partial-completion smoke synthetic parent') "
        "RETURNING Id",
        (MediaFileId, DispositionReason),
    )
    ParentId = Cur.fetchone()[0]
    Conn.commit()
    Cur.close()
    Db.CloseConnection(Conn)
    return ParentId


def CleanupSynthetic(Db, ParentId):
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    Cur.execute("DELETE FROM TranscodeQueue WHERE ParentTranscodeAttemptId = %s", (ParentId,))
    Cur.execute("DELETE FROM TranscodeAttempts WHERE Id = %s", (ParentId,))
    Conn.commit()
    Cur.close()
    Db.CloseConnection(Conn)


def CountLogsContaining(Db, Substring, SinceIso):
    Rows = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Count FROM Logs WHERE Message LIKE %s ESCAPE '!' AND Timestamp > %s",
        (f"%{EscapeLikePattern(Substring)}%", SinceIso),
    )
    return int(Rows[0]['Count'])


def Main():
    Db = DatabaseService()

    print("=" * 60)
    print("SMOKE: partial-pipeline-completion end-to-end")
    print("=" * 60)

    print("\n[1/5] SniffFirstFallback correctness")
    assert PartialCompletion.SniffFirstFallback("[libopus] channel_layout fail") == 'AudioSlot'
    assert PartialCompletion.SniffFirstFallback("[av1_nvenc] init failed") == 'VideoSlot'
    print("  sniff audio-marker -> AudioSlot [OK]")
    print("  sniff video-marker -> VideoSlot [OK]")

    StartTs = Db.ExecuteQuery("SELECT NOW() - INTERVAL '5 seconds' AS Now")[0]['Now']
    print(f"  start_ts={StartTs}")

    print("\n[2/5] Emit all five log points")
    MockMediaFileId = 999999
    MockParentAttemptId = 888888
    PartialCompletion.LogSniff(MockMediaFileId, "[libopus] test-only", 'AudioSlot')
    PartialCompletion.LogFallbackAttempt(MockMediaFileId, 1, 'AudioSlot')
    PartialCompletion.LogFallbackSuccess(MockMediaFileId, 1, 'AudioSlot')
    PartialCompletion.LogBothFallbacksFailed(MockMediaFileId, "orig-smoke", "fb1-smoke", "fb2-smoke")
    PartialCompletion.LogPartialRetryExhausted(MockMediaFileId, MockParentAttemptId, "child-smoke")
    print("  5 log emits fired")

    print("\n[3/5] Verify log entries in Logs table")
    time.sleep(1)
    Counts = {
        'PartialCompletionSniff': CountLogsContaining(Db, 'PartialCompletionSniff MediaFileId=999999', StartTs),
        'PartialCompletionFallback': CountLogsContaining(Db, 'PartialCompletionFallback MediaFileId=999999', StartTs),
        'PartialCompletionSuccess': CountLogsContaining(Db, 'PartialCompletionSuccess MediaFileId=999999', StartTs),
        'PartialCompletionExhausted': CountLogsContaining(Db, 'PartialCompletionExhausted MediaFileId=999999', StartTs),
        'PartialRetryExhausted': CountLogsContaining(Db, 'PartialRetryExhausted MediaFileId=999999', StartTs),
    }
    for Key, N in Counts.items():
        Marker = "[OK]" if N >= 1 else "[MISS]"
        print(f"  {Key}: {N} row(s) {Marker}")
    if not all(N >= 1 for N in Counts.values()):
        raise RuntimeError(f"Some log entries missing: {Counts}")

    print("\n[4/5] EnqueuePartialCompletionFollowup (AudioSlot copied)")
    MediaFileId = PickIdleMvTerminalMediaFileId(Db)
    print(f"  target MediaFileId={MediaFileId}")
    ParentId = CreateSyntheticParent(Db, MediaFileId, 'PartialSuccess_AudioSlotCopied')
    print(f"  synthetic parent attempt id={ParentId}")
    Svc = QueueManagementBusinessService()
    Followup = PartialCompletion.FollowupPlanForCopiedSlot('AudioSlot')
    Result = Svc.EnqueuePartialCompletionFollowup(
        MediaFileId=MediaFileId,
        ProcessingMode=Followup['ProcessingMode'],
        AudioSlotOverride=Followup['AudioSlotOverride'],
        ParentTranscodeAttemptId=ParentId,
    )
    assert Result.get('Success'), f"EnqueuePartialCompletionFollowup failed: {Result}"
    print(f"  follow-up ItemId={Result.get('ItemId')}")
    Rows = Db.ExecuteQuery(
        "SELECT Id, ProcessingMode, AudioSlotOverride, ParentTranscodeAttemptId, Status "
        "FROM TranscodeQueue WHERE ParentTranscodeAttemptId=%s",
        (ParentId,),
    )
    assert len(Rows) == 1, f"Expected 1 follow-up row, got {len(Rows)}"
    R = Rows[0]
    assert R['ProcessingMode'] == 'AudioFix', f"Expected AudioFix, got {R['ProcessingMode']}"
    assert R['AudioSlotOverride'] is None, f"Expected NULL override, got {R['AudioSlotOverride']!r}"
    assert R['ParentTranscodeAttemptId'] == ParentId
    assert R['Status'] == 'Pending'
    print(f"  row shape verified: mode={R['ProcessingMode']} override={R['AudioSlotOverride']!r} parent={R['ParentTranscodeAttemptId']} status={R['Status']} [OK]")
    CleanupSynthetic(Db, ParentId)
    print(f"  cleanup done")

    print("\n[5/5] EnqueuePartialCompletionFollowup (VideoSlot copied)")
    MediaFileId = PickIdleMvTerminalMediaFileId(Db)
    print(f"  target MediaFileId={MediaFileId}")
    ParentId = CreateSyntheticParent(Db, MediaFileId, 'PartialSuccess_VideoSlotCopied')
    print(f"  synthetic parent attempt id={ParentId}")
    Followup = PartialCompletion.FollowupPlanForCopiedSlot('VideoSlot')
    Result = Svc.EnqueuePartialCompletionFollowup(
        MediaFileId=MediaFileId,
        ProcessingMode=Followup['ProcessingMode'],
        AudioSlotOverride=Followup['AudioSlotOverride'],
        ParentTranscodeAttemptId=ParentId,
    )
    assert Result.get('Success'), f"EnqueuePartialCompletionFollowup failed: {Result}"
    print(f"  follow-up ItemId={Result.get('ItemId')}")
    Rows = Db.ExecuteQuery(
        "SELECT Id, ProcessingMode, AudioSlotOverride, ParentTranscodeAttemptId, Status "
        "FROM TranscodeQueue WHERE ParentTranscodeAttemptId=%s",
        (ParentId,),
    )
    R = Rows[0]
    assert R['ProcessingMode'] == 'Transcode', f"Expected Transcode, got {R['ProcessingMode']}"
    assert R['AudioSlotOverride'] == 'Copy', f"Expected 'Copy' override, got {R['AudioSlotOverride']!r}"
    print(f"  row shape verified: mode={R['ProcessingMode']} override={R['AudioSlotOverride']!r} parent={R['ParentTranscodeAttemptId']} status={R['Status']} [OK]")
    CleanupSynthetic(Db, ParentId)
    print(f"  cleanup done")

    print("\n" + "=" * 60)
    print("SMOKE PASSED: all 5 phases green + DB writes verified + logs landed")
    print("=" * 60)


if __name__ == '__main__':
    Main()
