from __future__ import annotations

import time

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import Fixtures
from Tests.Pipeline.Harness.Backup import BackupMediaFile, RestoreMediaFile
from Tests.Pipeline.Harness.HarnessPathResolver import ResolveLocalPathForMediaFile
from Tests.Pipeline.Harness.Invocation import InvokeQuickFix, InvokeTranscode
from Tests.Pipeline.Harness.Assertions import AssertIntegratedLoudnessNear, AssertDbState, AssertNoQueueRows
from Tests.Pipeline.Harness.JellyfinVerify import AssertNotifyFired


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _CurrentCanonicalPath(MediaFileId: int) -> str:
    """Latest FilePath for MediaFileId; canonical form (StorageRoot-prefixed)."""
    Rows = DatabaseService().ExecuteQuery("SELECT FilePath FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    return Rows[0]['FilePath']


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def test_quickfix_then_transcode_preserves_audio(notify_capture):
    """Quick Fix normalizes audio + flips AudioComplete; subsequent Transcode does NOT touch audio (byte-identical) but does re-encode video."""

    MediaFileId = Fixtures.QuickFixCandidate(MaxSizeMB=500)
    Handle = BackupMediaFile(MediaFileId)

    try:
        T0 = time.time()
        QuickAttemptId = InvokeQuickFix(MediaFileId)
        assert QuickAttemptId > 0, "Quick Fix attempt id should be positive"

        PostQuickLocalPath = ResolveLocalPathForMediaFile(MediaFileId)
        PostQuickCanonical = _CurrentCanonicalPath(MediaFileId)

        AssertIntegratedLoudnessNear(PostQuickLocalPath, TargetLufs=-23.0, ToleranceLU=1.0)

        AssertDbState(MediaFileId, AudioComplete=True)
        AssertNoQueueRows(MediaFileId)

        Row = DatabaseService().ExecuteQuery("SELECT Success, FileReplaced FROM TranscodeAttempts WHERE Id = %s", (QuickAttemptId,))
        assert Row, "TranscodeAttempts row missing"
        R = Row[0]
        assert R.get('Success') is True, f"Quick Fix attempt Success={R.get('Success')}"
        assert R.get('FileReplaced') is True, f"Quick Fix FileReplaced={R.get('FileReplaced')}"

        try:
            AssertNotifyFired(notify_capture, PostQuickCanonical, UpdateType='Modified', SinceTs=T0)
        except AssertionError:
            AssertNotifyFired(notify_capture, PostQuickCanonical, UpdateType='Created', SinceTs=T0)

        TranscodeAttemptId = InvokeTranscode(MediaFileId)
        assert TranscodeAttemptId > 0, "Transcode attempt id should be positive"
        assert TranscodeAttemptId != QuickAttemptId, "Distinct attempt ids expected"

        Cmd = DatabaseService().ExecuteQuery("SELECT FfpmpegCommand FROM TranscodeAttempts WHERE Id = %s", (TranscodeAttemptId,))[0]['FfpmpegCommand'] or ''
        assert '-c:a copy' in Cmd, f"Transcode command should stream-copy audio for AudioComplete=true file, but emitted command does not contain '-c:a copy'. Command: {Cmd[:500]}..."
        assert 'loudnorm' not in Cmd.lower(), f"Transcode command should NOT contain loudnorm when AudioComplete=true. Command: {Cmd[:500]}..."

        AssertDbState(MediaFileId, AudioComplete=True)

    finally:
        RestoreMediaFile(Handle)
