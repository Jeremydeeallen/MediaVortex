"""Test case 1 -- Quick Fix then Transcode preserves audio.

Drives a real MediaFile through the Remux pipeline first (one-shot
audio normalize), then through the Transcode pipeline (video re-encode
with `-c:a copy` because AudioComplete=true). Asserts audio is
byte-identical between the post-Remux and post-Transcode files, and
that every contract from audio-completion + linear-loudnorm +
jellyfin-push-notify holds.

See Tests/Pipeline/pipeline-test-harness.feature.md criterion 17.
"""

from __future__ import annotations

import time

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import Fixtures
from Tests.Pipeline.Harness.Backup import BackupMediaFile, RestoreMediaFile
from Tests.Pipeline.Harness.Invocation import InvokeQuickFix, InvokeTranscode
from Tests.Pipeline.Harness.Assertions import (
    AssertIntegratedLoudnessNear,
    AssertTruePeakAtOrBelow,
    AssertAudioBytesIdentical,
    AssertDbState,
    AssertNoQueueRows,
    AudioStreamHash,
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


def test_quickfix_then_transcode_preserves_audio(notify_capture):
    """Quick Fix normalizes audio + flips AudioComplete; subsequent Transcode
    does NOT touch audio (byte-identical) but does re-encode video."""

    MediaFileId = Fixtures.QuickFixCandidate(MaxSizeMB=500)
    Handle = BackupMediaFile(MediaFileId)

    try:
        # === Step 1: Quick Fix ===
        T0 = time.time()
        QuickAttemptId = InvokeQuickFix(MediaFileId)
        assert QuickAttemptId > 0, "Quick Fix attempt id should be positive"

        PostQuickLocalPath = _CurrentLocalPath(MediaFileId)
        PostQuickCanonical = _CurrentCanonicalPath(MediaFileId)

        # Audio normalized to target loudness
        AssertIntegratedLoudnessNear(PostQuickLocalPath, TargetLufs=-23.0, ToleranceLU=1.0)
        AssertTruePeakAtOrBelow(PostQuickLocalPath, MaxDbtp=-1.0)  # slight slack from -2 ceiling

        # AudioComplete flipped, file is compliant
        AssertDbState(
            MediaFileId,
            AudioComplete=True,
        )
        AssertNoQueueRows(MediaFileId)

        # TranscodeAttempts captured with Success + FileReplaced
        Row = DatabaseService().ExecuteQuery(
            "SELECT Success, FileReplaced FROM TranscodeAttempts WHERE Id = %s",
            (QuickAttemptId,),
        )
        assert Row, "TranscodeAttempts row missing"
        R = dict(Row[0])
        assert R.get('success') is True, f"Quick Fix attempt Success={R.get('success')}"
        assert R.get('filereplaced') is True, f"Quick Fix FileReplaced={R.get('filereplaced')}"

        # Jellyfin notified
        AssertNotifyFired(notify_capture, PostQuickCanonical, UpdateType='Modified', SinceTs=T0)

        # Capture the audio hash to compare against post-Transcode
        AudioHashPostQuick = AudioStreamHash(PostQuickLocalPath)

        # === Step 2: Transcode ===
        # The Quick Fix flipped AudioComplete=true and may have marked the
        # file compliant. To force a Transcode invocation, the routing must
        # pick the file up again -- we directly invoke (the harness's
        # InvokeTranscode bypasses the routing gate). The expectation:
        # video re-encoded to AssignedProfile codec; audio bytes unchanged.
        T1 = time.time()
        TranscodeAttemptId = InvokeTranscode(MediaFileId)
        assert TranscodeAttemptId > 0, "Transcode attempt id should be positive"
        assert TranscodeAttemptId != QuickAttemptId, "Distinct attempt ids expected"

        PostTranscodeLocalPath = _CurrentLocalPath(MediaFileId)
        PostTranscodeCanonical = _CurrentCanonicalPath(MediaFileId)

        # Audio byte-identical to the post-Quick file (proves -c:a copy)
        AssertAudioBytesIdentical(PostQuickLocalPath, PostTranscodeLocalPath)
        # And same hash equality, captured proactively in case path renames
        AudioHashPostTranscode = AudioStreamHash(PostTranscodeLocalPath)
        assert AudioHashPostQuick == AudioHashPostTranscode, (
            f"Audio hash changed across transcode: "
            f"post-quick={AudioHashPostQuick[:12]}, "
            f"post-transcode={AudioHashPostTranscode[:12]}"
        )

        # AudioComplete still true (never flipped back)
        AssertDbState(MediaFileId, AudioComplete=True)

        # Jellyfin notified a second time
        AssertNotifyFired(notify_capture, PostTranscodeCanonical, UpdateType='Modified', SinceTs=T1)

    finally:
        # Restore unconditionally -- never leave the library in a half-test state.
        RestoreMediaFile(Handle)
