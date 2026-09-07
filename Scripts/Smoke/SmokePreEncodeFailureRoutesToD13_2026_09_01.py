# directive: bug-0093-preencode-fail-loud-via-d13
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch

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
        "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, Disposition, DispositionReason, ProfileName, WorkerName, ErrorMessage, ProcessingMode, OldSizeBytes, NewSizeBytes) "
        "VALUES (%s, NOW(), TRUE, 'Replace', %s, 'SMOKE-bug-0093', 'smoke-tester', 'bug-0093 smoke synthetic parent', 'Transcode', 200000, 100000) "
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
    Cur.execute("DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s", (ParentId,))
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


def InsertTfp(Db, AttemptId):
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    Cur.execute(
        "INSERT INTO TemporaryFilePaths (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath) "
        "VALUES (%s, 1, %s, 1, %s)",
        (AttemptId, f"smoke-src-{AttemptId}.mkv", f"smoke-out-{AttemptId}-mv.mp4"),
    )
    Conn.commit()
    Cur.close()
    Db.CloseConnection(Conn)


def Main():
    Db = DatabaseService()
    print("=" * 60)
    print("SMOKE: bug-0093-preencode-fail-loud-via-d13")
    print("=" * 60)

    StartTs = Db.ExecuteQuery("SELECT NOW() - INTERVAL '5 seconds' AS Now")[0]['Now']
    print(f"  start_ts={StartTs}")

    print("\n[1/3] LogPreEncodeFallback emit -> Logs row at WARNING")
    MockMediaFileId = 888777
    PartialCompletion.LogPreEncodeFallback(MockMediaFileId, "DemucsDaemonUnavailableError: closed stdout unexpectedly")
    time.sleep(1)
    Count = CountLogsContaining(Db, f"PreEncodePartialFallback MediaFileId={MockMediaFileId}", StartTs)
    assert Count >= 1, f"Expected >=1 PreEncodePartialFallback log row, got {Count}"
    LevelRows = Db.ExecuteQuery(
        "SELECT LogLevel FROM Logs WHERE Message LIKE %s ESCAPE '!' AND Timestamp > %s ORDER BY Timestamp DESC LIMIT 1",
        (f"%{EscapeLikePattern(f'PreEncodePartialFallback MediaFileId={MockMediaFileId}')}%", StartTs),
    )
    Level = LevelRows[0].get('LogLevel') if LevelRows else None
    assert Level == 'WARNING', f"Expected Level=WARNING, got {Level!r}"
    print(f"  logged 1x at WARNING [OK]")

    print("\n[2/3] EnqueuePartialCompletionFollowup writes AudioFix TranscodeQueue row")
    MediaFileId = PickIdleMvTerminalMediaFileId(Db)
    print(f"  target MediaFileId={MediaFileId}")
    ParentId = CreateSyntheticParent(Db, MediaFileId, 'PartialSuccess_AudioSlotCopied')
    print(f"  synthetic parent attempt id={ParentId}")
    Followup = PartialCompletion.FollowupPlanForCopiedSlot('AudioSlot')
    Result = QueueManagementBusinessService().EnqueuePartialCompletionFollowup(
        MediaFileId=MediaFileId,
        ProcessingMode=Followup['ProcessingMode'],
        AudioSlotOverride=Followup['AudioSlotOverride'],
        ParentTranscodeAttemptId=ParentId,
    )
    assert Result.get('Success'), f"EnqueuePartialCompletionFollowup failed: {Result}"
    Rows = Db.ExecuteQuery(
        "SELECT Id, ProcessingMode, AudioSlotOverride, ParentTranscodeAttemptId, Status "
        "FROM TranscodeQueue WHERE ParentTranscodeAttemptId=%s",
        (ParentId,),
    )
    assert len(Rows) == 1, f"Expected 1 follow-up row, got {len(Rows)}"
    R = Rows[0]
    assert R['ProcessingMode'] == 'AudioFix'
    assert R['AudioSlotOverride'] is None
    assert R['Status'] == 'Pending'
    print(f"  row shape verified: mode={R['ProcessingMode']} override={R['AudioSlotOverride']!r} status={R['Status']} [OK]")
    CleanupSynthetic(Db, ParentId)
    print(f"  cleanup done")

    print("\n[3/3] ProcessFileReplacement bypasses ComplianceGate on PartialSuccess_AudioSlotCopied")
    MediaFileId = PickIdleMvTerminalMediaFileId(Db)
    ParentId = CreateSyntheticParent(Db, MediaFileId, 'PartialSuccess_AudioSlotCopied')
    InsertTfp(Db, ParentId)

    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
    Svc = FileReplacementBusinessService()
    Svc._WorkerName = 'smoke-tester'
    CapturedKwargs = {}
    def CaptureExecute(self, *args, **kwargs):
        CapturedKwargs.update(kwargs)
        return {'Success': False, 'ErrorMessage': 'smoke-stop-after-capture'}

    with patch('Features.FileReplacement.TranscodedOutputPlacement.TranscodedOutputPlacement.Execute', CaptureExecute):
        with patch.object(Svc.FileManager, 'ValidateFileExists', return_value=True):
            with patch('Features.FileReplacement.FileReplacementBusinessService.Path') as MockPath:
                MockPath.return_value.CanonicalDisplay.return_value = f"T:\\smoke-{ParentId}.mkv"
                MockPath.return_value.Resolve.return_value = f"/local/smoke-{ParentId}.mkv"
                try:
                    Svc.ProcessFileReplacement(TranscodeAttemptId=ParentId)
                except Exception:
                    pass
    print(f"  captured Execute kwargs: RunComplianceGate={CapturedKwargs.get('RunComplianceGate', '<not captured>')}")
    assert CapturedKwargs.get('RunComplianceGate') is False, (
        f"Expected RunComplianceGate=False for PartialSuccess_AudioSlotCopied, got {CapturedKwargs.get('RunComplianceGate')!r}"
    )
    print(f"  ComplianceGate BYPASSED for PartialSuccess_AudioSlotCopied [OK]")
    CleanupSynthetic(Db, ParentId)

    print("\n[bonus] Same path with VmafAutoReplace -> gate DOES run")
    MediaFileId = PickIdleMvTerminalMediaFileId(Db)
    ParentId = CreateSyntheticParent(Db, MediaFileId, 'VmafAutoReplace')
    InsertTfp(Db, ParentId)
    CapturedKwargs.clear()
    Svc2 = FileReplacementBusinessService()
    Svc2._WorkerName = 'smoke-tester'
    with patch('Features.FileReplacement.TranscodedOutputPlacement.TranscodedOutputPlacement.Execute', CaptureExecute):
        with patch.object(Svc2.FileManager, 'ValidateFileExists', return_value=True):
            with patch('Features.FileReplacement.FileReplacementBusinessService.Path') as MockPath:
                MockPath.return_value.CanonicalDisplay.return_value = f"T:\\smoke-{ParentId}.mkv"
                MockPath.return_value.Resolve.return_value = f"/local/smoke-{ParentId}.mkv"
                try:
                    Svc2.ProcessFileReplacement(TranscodeAttemptId=ParentId)
                except Exception:
                    pass
    print(f"  captured Execute kwargs: RunComplianceGate={CapturedKwargs.get('RunComplianceGate', '<not captured>')}")
    assert CapturedKwargs.get('RunComplianceGate') is True, (
        f"Expected RunComplianceGate=True for VmafAutoReplace, got {CapturedKwargs.get('RunComplianceGate')!r}"
    )
    print(f"  ComplianceGate RAN for VmafAutoReplace [OK]")
    CleanupSynthetic(Db, ParentId)

    print("\n" + "=" * 60)
    print("SMOKE PASSED: log emit + follow-up enqueue + gate bypass verified against live DB")
    print("=" * 60)


if __name__ == '__main__':
    Main()
