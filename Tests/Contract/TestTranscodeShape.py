from unittest.mock import MagicMock, patch

import pytest

from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.TranscodeShape import TranscodeShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
def _MakeShape():
    """Wire TranscodeShape with mock collaborators."""
    Resolution = MagicMock()
    Resolution.CalculateTargetResolution = lambda Profile, Source: '720p'
    Resolution.CalculateScaleFilter = lambda S, T, M, P: 'scale=w=1280:h=-2'
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.GenerateOutputFileName = lambda Orig, Src, Tgt, Container='mp4', Crf=None: 'Show-mv.mp4.inprogress'
    CodecAssembler = MagicMock()
    CodecAssembler.AddCodecParameters = MagicMock()
    CodecAssembler.AddFilmGrainParameter = MagicMock()
    CodecAssembler.AddPixelFormatParameter = MagicMock()
    AudioCodec = MagicMock()
    AudioCodec.BuildAudioCodecArgs = lambda Mf, Bitrate: ['-c:a', 'aac', '-b:a', '128k']
    AudioFilter = MagicMock()
    AudioFilter.Build = lambda Mf: 'loudnorm=I=-23:linear=true'
    VideoFilter = MagicMock()
    VideoFilter.Build = lambda Profile, Scale, Interlaced: 'scale=w=1280:h=-2'
    Probe = MagicMock()
    Probe.RunAnalysis = lambda InputPath: None
    return TranscodeShape(
        ResolutionCalculator=Resolution,
        OutputFilenameBuilder=Filename,
        CodecParameterAssembler=CodecAssembler,
        AudioCodecArgsBuilder=AudioCodec,
        AudioFilterBuilder=AudioFilter,
        VideoFilterBuilder=VideoFilter,
        MediaProbeAdapter=Probe,
    )


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
def _MakeMediaFile():
    """Build a stub MediaFile."""
    Mf = MagicMock()
    Mf.FileName = "Show.mkv"
    Mf.Resolution = "1080p"
    Mf.Codec = "h264"
    Mf.IsInterlaced = False
    Mf.Id = 1
    return Mf


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
def _MakeContext(UseNvidia=0):
    """Build a minimal Context dict for Transcode Build."""
    return {
        'InputPath': "T:\\Shows\\Show.mkv",
        'FFmpegPath': "C:\\ffmpeg.exe",
        'AudioStreamIndex': 0,
        'ProfileSettings': {'UseNvidiaHardware': UseNvidia, 'Codec': 'libsvtav1', 'Quality': 32, 'ContainerType': 'mp4'},
        'CodecParameters': [],
    }


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
class TestTranscodeShape:
    """Contract: TranscodeShape orchestrates collaborators and returns a CommandSpec for the encode."""

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=False)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def test_returns_commandspec(self, _Mock):
        """Build returns a CommandSpec value object."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert isinstance(Spec, CommandSpec)

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=False)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def test_nvenc_dispatch(self, _Mock):
        """ProfileSettings.UseNvidiaHardware=1 selects av1_nvenc codec."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext(UseNvidia=1))
        assert '-c:v av1_nvenc' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=False)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def test_software_dispatch(self, _Mock):
        """ProfileSettings.UseNvidiaHardware=0 falls back to ProfileSettings.Codec."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext(UseNvidia=0))
        assert '-c:v libsvtav1' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=False)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def test_audio_filter_applied_when_present(self, _Mock):
        """AudioFilterBuilder.Build result is passed to ffmpeg via -af."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-af' in Spec.Command
        assert 'loudnorm=I=-23:linear=true' in Spec.Command

    @patch('Features.AudioCompletion.AudioCompletionService.AudioCompletionService.ShouldStreamCopyAudio', return_value=True)
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def test_audio_stream_copy_when_complete(self, _Mock):
        """AudioCompleteService.ShouldStreamCopy=True -> -c:a copy emitted, no filter probe."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-c:a copy' in Spec.Command
