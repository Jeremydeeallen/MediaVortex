from unittest.mock import MagicMock, patch

import pytest

from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.SubtitleFixShape import SubtitleFixShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
def _MakeShape():
    """Wire SubtitleFixShape with mock collaborators."""
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.CollapseMvSuffix = lambda B: B
    AudioCodec = MagicMock()
    AudioCodec.BuildAudioCodecArgs = lambda Mf, ProfileBitrate: ['-c:a', 'aac', '-b:a', '128k']
    AudioFilter = MagicMock()
    AudioFilter.Build = lambda Mf: None
    Probe = MagicMock()
    Probe.RunAnalysis = lambda InputPath: None
    return SubtitleFixShape(
        OutputFilenameBuilder=Filename,
        AudioCodecArgsBuilder=AudioCodec,
        AudioFilterBuilder=AudioFilter,
        MediaProbeAdapter=Probe,
    )


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
def _MakeMediaFile():
    """Build a stub MediaFile."""
    Mf = MagicMock()
    Mf.FileName = "Show.mkv"
    Mf.Codec = "h264"
    Mf.AudioCodec = "aac"
    Mf.Id = 1
    return Mf


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
def _MakeContext():
    """Build a minimal Context dict for SubtitleFix Build."""
    return {
        'InputPath': "T:\\Shows\\Season 1\\Show.mkv",
        'FFmpegPath': "C:\\ffmpeg.exe",
        'AudioStreamIndex': 0,
        'SubtitleStreamIndex': 0,
    }


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
class TestSubtitleFixShape:
    """Contract: SubtitleFixShape emits unconditional -f mp4 + -movflags +faststart + mov_text subtitle codec."""

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def test_emits_f_mp4_unconditionally(self, _Mock):
        """SubtitleFix output is always MP4 -- emits -f mp4 regardless of ProfileSettings."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert Spec is not None
        assert '-f mp4' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def test_emits_movflags_faststart_unconditionally(self, _Mock):
        """SubtitleFix output gets +faststart; matches Remux invariant."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert Spec is not None
        assert '-movflags +faststart' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def test_emits_mov_text_subtitle_codec(self, _Mock):
        """ASS/SSA -> mov_text conversion is the SubtitleFix shape's defining transform."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-c:s mov_text' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def test_video_stream_copy(self, _Mock):
        """SubtitleFix keeps video as -c:v copy."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-c:v copy' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def test_returns_commandspec_value_object(self, _Mock):
        """Build returns CommandSpec; OutputPath ends in -mv.mp4.inprogress."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert isinstance(Spec, CommandSpec)
        assert Spec.OutputPath.endswith("-mv.mp4.inprogress")
