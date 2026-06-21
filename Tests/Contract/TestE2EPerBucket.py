from __future__ import annotations

import time

import pytest

# directive: e2e-pipeline-test-framework
pytestmark = pytest.mark.slow

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import Fixtures
from Tests.Pipeline.Harness import PermanentFixtures
from Tests.Pipeline.Harness.Backup import BackupMediaFile, RestoreMediaFile
from Tests.Pipeline.Harness.HarnessPathResolver import ResolveLocalPathForMediaFile
from Tests.Pipeline.Harness.Invocation import InvokeQuickFix, InvokeTranscode
from Tests.Pipeline.Harness.Assertions import (
    AssertDbState,
    AssertNoQueueRows,
    AssertVideoCodecMatchesProfile,
    AssertIntegratedLoudnessNear,
)


# directive: e2e-pipeline-test-framework
def _CurrentCanonicalPath(MediaFileId: int) -> str:
    Rows = DatabaseService().ExecuteQuery("SELECT FilePath FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    return Rows[0]['FilePath']


# directive: e2e-pipeline-test-framework
def _PickFixture(Bucket: str, LivePickerFn):
    """Use a permanent fixture if present; otherwise fall back to live picker."""
    if PermanentFixtures.IsAvailable(Bucket):
        Props = PermanentFixtures.GetProperties(Bucket)
        return int(Props['SourceMediaFileId'])
    return LivePickerFn()


# directive: e2e-pipeline-test-framework
def test_transcode_bucket_e2e():
    """Pre: file in Transcode bucket. Post: full transcode runs, file becomes compliant, all three booleans TRUE, WorkBucket NULL."""
    MediaFileId = _PickFixture('Transcode', lambda: Fixtures.TranscodeCandidate(MaxSizeMB=500))
    Handle = BackupMediaFile(MediaFileId)
    try:
        Pre = DatabaseService().ExecuteQuery(
            "SELECT WorkBucket, IsCompliant, AudioCompliant, VideoCompliant, ContainerCompliant FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )[0]
        assert Pre['WorkBucket'] == 'Transcode', f"Pre-state expected Transcode, got {Pre['WorkBucket']}"
        AttemptId = InvokeTranscode(MediaFileId)
        assert AttemptId > 0
        AssertVideoCodecMatchesProfile(MediaFileId)
        AssertDbState(
            MediaFileId,
            WorkBucket=None,
            IsCompliant=True,
            AudioCompliant=True,
            VideoCompliant=True,
            ContainerCompliant=True,
        )
        AssertNoQueueRows(MediaFileId)
    finally:
        RestoreMediaFile(Handle)


# directive: e2e-pipeline-test-framework
def test_remux_bucket_e2e():
    """Pre: file in Remux bucket (ContainerCompliant=FALSE). Post: remux runs, container fixed, three booleans TRUE, bucket NULL."""
    MediaFileId = _PickFixture('Remux', lambda: Fixtures.RemuxCandidate(MaxSizeMB=500))
    Handle = BackupMediaFile(MediaFileId)
    try:
        Pre = DatabaseService().ExecuteQuery(
            "SELECT WorkBucket, ContainerCompliant FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )[0]
        assert Pre['WorkBucket'] == 'Remux', f"Pre-state expected Remux, got {Pre['WorkBucket']}"
        assert Pre['ContainerCompliant'] is False
        AttemptId = InvokeQuickFix(MediaFileId)
        assert AttemptId > 0
        AssertDbState(
            MediaFileId,
            WorkBucket=None,
            IsCompliant=True,
            AudioCompliant=True,
            VideoCompliant=True,
            ContainerCompliant=True,
        )
        AssertNoQueueRows(MediaFileId)
    finally:
        RestoreMediaFile(Handle)


# directive: e2e-pipeline-test-framework
def test_audiofixonly_bucket_e2e():
    """Pre: file in AudioFixOnly bucket (only AudioCompliant=FALSE). Post: audio normalized, all three booleans TRUE, bucket NULL."""
    MediaFileId = _PickFixture('AudioFixOnly', lambda: Fixtures.AudioFixOnlyCandidate(MaxSizeMB=500))
    Handle = BackupMediaFile(MediaFileId)
    try:
        Pre = DatabaseService().ExecuteQuery(
            "SELECT WorkBucket, AudioCompliant, VideoCompliant, ContainerCompliant FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )[0]
        assert Pre['WorkBucket'] == 'AudioFixOnly'
        assert Pre['AudioCompliant'] is False
        assert Pre['VideoCompliant'] is True
        assert Pre['ContainerCompliant'] is True
        AttemptId = InvokeQuickFix(MediaFileId)
        assert AttemptId > 0
        PostLocalPath = ResolveLocalPathForMediaFile(MediaFileId)
        AssertIntegratedLoudnessNear(PostLocalPath, TargetLufs=-23.0, ToleranceLU=1.0)
        AssertDbState(
            MediaFileId,
            WorkBucket=None,
            IsCompliant=True,
            AudioCompliant=True,
            VideoCompliant=True,
            ContainerCompliant=True,
            AudioComplete=True,
        )
    finally:
        RestoreMediaFile(Handle)


# directive: e2e-pipeline-test-framework
def test_already_compliant_no_work_e2e():
    """Pre: file already compliant. Post: vertical recomputes are idempotent; state unchanged."""
    MediaFileId = _PickFixture('Compliant', lambda: Fixtures.AlreadyCompliant())
    Pre = DatabaseService().ExecuteQuery(
        "SELECT WorkBucket, IsCompliant, AudioCompliant, VideoCompliant, ContainerCompliant FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )[0]
    assert Pre['WorkBucket'] is None
    assert Pre['IsCompliant'] is True

    from Features.AudioNormalization.AudioVertical import AudioVertical
    from Features.VideoEncoding.VideoVertical import VideoVertical
    from Features.ContainerFormat.ContainerVertical import ContainerVertical
    AudioVertical().RecomputeFor([MediaFileId])
    VideoVertical().RecomputeFor([MediaFileId])
    ContainerVertical().RecomputeFor([MediaFileId])

    AssertDbState(
        MediaFileId,
        WorkBucket=None,
        IsCompliant=True,
        AudioCompliant=True,
        VideoCompliant=True,
        ContainerCompliant=True,
    )
    AssertNoQueueRows(MediaFileId)
