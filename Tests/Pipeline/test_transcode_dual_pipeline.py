"""Test case 2 -- Transcode with both audio fix and video transcode.

A file that needs both video re-encode (video codec wrong / downscale)
AND audio normalization runs through the Transcode pipeline ONCE; the
one-shot pass handles both. AudioComplete flips to true post-flight,
the file becomes compliant, drops out of every queue surface, and
Jellyfin is notified.

After the encode, a follow-up RecomputeForFiles call must NOT re-flag
the file -- this catches the regression where compliance state would
oscillate after a successful transcode.

See Tests/Pipeline/pipeline-test-harness.feature.md criterion 18.
"""

from __future__ import annotations

import time

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import Fixtures
from Tests.Pipeline.Harness.Backup import BackupMediaFile, RestoreMediaFile
from Tests.Pipeline.Harness.Invocation import InvokeTranscode
from Tests.Pipeline.Harness.Assertions import (
    AssertIntegratedLoudnessNear,
    AssertTruePeakAtOrBelow,
    AssertDbState,
    AssertNoQueueRows,
    AssertVideoCodecMatchesProfile,
)
from Tests.Pipeline.Harness.JellyfinVerify import AssertNotifyFired


def _CurrentCanonicalPath(MediaFileId: int) -> str:
    Rows = DatabaseService().ExecuteQuery(
        "SELECT FilePath FROM MediaFiles WHERE Id = %s", (MediaFileId,),
    )
    return dict(Rows[0])['filepath']


def _CurrentLocalPath(MediaFileId: int) -> str:
    from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
    from Core.WorkerContext import WorkerContext
    Db = DatabaseService()
    Canonical = _CurrentCanonicalPath(MediaFileId)
    SrId, Rel = PathParse(Canonical, LoadStorageRoots(Db))
    Ctx = WorkerContext.Current()
    return PathResolve(SrId, Rel, Ctx.WorkerName, Db)


def test_transcode_dual_pipeline(notify_capture):
    """One Transcode pass handles BOTH video re-encode AND audio normalize;
    the file becomes compliant and stays out of every queue."""

    MediaFileId = Fixtures.TranscodeCandidate(MaxSizeMB=500)
    Handle = BackupMediaFile(MediaFileId)

    try:
        T0 = time.time()
        AttemptId = InvokeTranscode(MediaFileId)
        assert AttemptId > 0, "Transcode attempt id should be positive"

        PostLocalPath = _CurrentLocalPath(MediaFileId)
        PostCanonical = _CurrentCanonicalPath(MediaFileId)

        # Video transcoded to the assigned profile codec
        AssertVideoCodecMatchesProfile(MediaFileId)

        # Audio normalized in the same pass
        AssertIntegratedLoudnessNear(PostLocalPath, TargetLufs=-23.0, ToleranceLU=1.0)
        AssertTruePeakAtOrBelow(PostLocalPath, MaxDbtp=-1.0)

        # DB state: complete + compliant + not flagged for any queue
        AssertDbState(
            MediaFileId,
            AudioComplete=True,
            IsCompliant=True,
            RecommendedMode=None,
        )
        AssertNoQueueRows(MediaFileId)

        # TranscodeAttempts shows Success + FileReplaced
        Row = DatabaseService().ExecuteQuery(
            "SELECT Success, FileReplaced FROM TranscodeAttempts WHERE Id = %s",
            (AttemptId,),
        )
        assert Row, "TranscodeAttempts row missing"
        R = dict(Row[0])
        assert R.get('success') is True, f"Transcode attempt Success={R.get('success')}"
        assert R.get('filereplaced') is True, f"FileReplaced={R.get('filereplaced')}"

        # Jellyfin notified
        AssertNotifyFired(notify_capture, PostCanonical, UpdateType='Modified', SinceTs=T0)

        # Regression check: recompute does NOT re-flag the file
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        QueueManagementBusinessService().RecomputeForFiles([MediaFileId])
        AssertDbState(
            MediaFileId,
            IsCompliant=True,
            RecommendedMode=None,
        )
        AssertNoQueueRows(MediaFileId)

    finally:
        RestoreMediaFile(Handle)
