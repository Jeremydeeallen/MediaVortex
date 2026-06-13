from unittest.mock import MagicMock, patch

import pytest

from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.RemuxShape import RemuxShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
def _MakeMediaFile(FileName="Show.mkv", Codec="h264", AudioCodec="aac"):
    """Build a stub MediaFile object the shape's getattr() calls can read."""
    Mf = MagicMock()
    Mf.FileName = FileName
    Mf.Codec = Codec
    Mf.AudioCodec = AudioCodec
    Mf.Id = 1
    return Mf


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
def _MakeContext(InputPath="T:\\Shows\\Season 1\\Show.mkv", FFmpegPath="C:\\ffmpeg.exe", HasAudio=True):
    """Build a minimal Context dict for Remux Build."""
    return {
        'InputPath': InputPath,
        'FFmpegPath': FFmpegPath,
        'AudioStreamIndex': 0,
        'HasAudio': HasAudio,
    }


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
def _MakeShape():
    """Wire RemuxShape with mock collaborators that pass paths through unchanged."""
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.CollapseMvSuffix = lambda B: B
    AudioCodec = MagicMock()
    AudioCodec.BuildAudioCodecArgs = lambda Mf, ProfileBitrate: ['-c:a', 'aac', '-b:a', '128k']
    AudioFilter = MagicMock()
    AudioFilter.Build = lambda Mf: None
    Probe = MagicMock()
    Probe.RunAnalysis = lambda InputPath: None
    return RemuxShape(
        OutputFilenameBuilder=Filename,
        AudioCodecArgsBuilder=AudioCodec,
        AudioFilterBuilder=AudioFilter,
        MediaProbeAdapter=Probe,
    )


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
class TestRemuxShape:
    """Contract: RemuxShape.Build emits -f mp4 + -movflags +faststart unconditionally."""

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_emits_f_mp4_unconditionally(self, _Mock):
        """-f mp4 appears in the command regardless of ProfileSettings."""
        Shape = _MakeShape()
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert Spec is not None
        assert '-f mp4' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_emits_movflags_faststart_unconditionally(self, _Mock):
        """-movflags +faststart appears regardless of ProfileSettings."""
        Shape = _MakeShape()
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert Spec is not None
        assert '-movflags +faststart' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_returns_commandspec_value_object(self, _Mock):
        """Build returns the typed CommandSpec, not a plain dict."""
        Shape = _MakeShape()
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert isinstance(Spec, CommandSpec)
        assert Spec.OutputPath.endswith("-mv.mp4.inprogress")

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_video_stream_copy(self, _Mock):
        """Video stream is always copy (no re-encode) in Remux."""
        Shape = _MakeShape()
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-c:v copy' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_hevc_gets_hvc1_tag(self, _Mock):
        """HEVC source video gets -tag:v hvc1 for MP4 compatibility."""
        Shape = _MakeShape()
        Mf = _MakeMediaFile(Codec="hevc")
        Spec = Shape.Build(Mf, MagicMock(), _MakeContext())
        assert '-tag:v hvc1' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_output_collision_refuses(self, _Mock):
        """OutputPath equal to InputPath -- shape refuses (returns None)."""
        Shape = _MakeShape()
        Ctx = _MakeContext(InputPath="T:\\foo-mv.mp4.inprogress")
        Ctx['OutputPath'] = "T:\\foo-mv.mp4.inprogress"
        Spec = Shape.Build(_MakeMediaFile(FileName="foo-mv.mp4.inprogress"), MagicMock(), Ctx)
        assert Spec is None

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def test_no_audio_skips_audio_map(self, _Mock):
        """When HasAudio=False, no -map 0:a:N entry is emitted."""
        Shape = _MakeShape()
        Ctx = _MakeContext(HasAudio=False)
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), Ctx)
        assert Spec is not None
        assert '0:a:' not in Spec.Command
