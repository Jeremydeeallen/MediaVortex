from __future__ import annotations

import time

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import Fixtures
from Tests.Pipeline.Harness.Backup import BackupMediaFile, RestoreMediaFile
from Tests.Pipeline.Harness.HarnessPathResolver import ResolveLocalPathForMediaFile
from Tests.Pipeline.Harness.Invocation import InvokeTranscode
from Tests.Pipeline.Harness.Assertions import AssertIntegratedLoudnessNear, AssertDbState, AssertNoQueueRows, AssertVideoCodecMatchesProfile
from Tests.Pipeline.Harness.JellyfinVerify import AssertNotifyFired


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _CurrentCanonicalPath(MediaFileId: int) -> str:
    """Latest FilePath for MediaFileId; canonical form (StorageRoot-prefixed)."""
    Rows = DatabaseService().ExecuteQuery("SELECT FilePath FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    return Rows[0]['FilePath']


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def test_transcode_dual_pipeline(notify_capture):
    """One Transcode pass handles BOTH video re-encode AND audio normalize; the file becomes compliant and stays out of every queue."""

    MediaFileId = Fixtures.TranscodeCandidate(MaxSizeMB=500)
    Handle = BackupMediaFile(MediaFileId)

    try:
        T0 = time.time()
        AttemptId = InvokeTranscode(MediaFileId)
        assert AttemptId > 0, "Transcode attempt id should be positive"

        PostLocalPath = ResolveLocalPathForMediaFile(MediaFileId)
        PostCanonical = _CurrentCanonicalPath(MediaFileId)

        AssertVideoCodecMatchesProfile(MediaFileId)

        AssertIntegratedLoudnessNear(PostLocalPath, TargetLufs=-23.0, ToleranceLU=1.0)

        AssertDbState(MediaFileId, AudioComplete=True, IsCompliant=True, WorkBucket=None)
        AssertNoQueueRows(MediaFileId)

        Row = DatabaseService().ExecuteQuery("SELECT Success, FileReplaced FROM TranscodeAttempts WHERE Id = %s", (AttemptId,))
        assert Row, "TranscodeAttempts row missing"
        R = Row[0]
        assert R.get('Success') is True, f"Transcode attempt Success={R.get('Success')}"
        assert R.get('FileReplaced') is True, f"FileReplaced={R.get('FileReplaced')}"

        try:
            AssertNotifyFired(notify_capture, PostCanonical, UpdateType='Modified', SinceTs=T0)
        except AssertionError:
            AssertNotifyFired(notify_capture, PostCanonical, UpdateType='Created', SinceTs=T0)

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        QueueManagementBusinessService().RecomputeForFiles([MediaFileId])
        AssertDbState(MediaFileId, IsCompliant=True, WorkBucket=None)
        AssertNoQueueRows(MediaFileId)

    finally:
        RestoreMediaFile(Handle)
