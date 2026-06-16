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
    Resolver = MagicMock()
    Resolver.GetEffectivePolicy = lambda Mf: None
    Emitter = MagicMock()
    Emitter.EmitTracks = lambda Mf, P, AudioStreams=None, LibraryDefault=None: []
    return TranscodeShape(
        ResolutionCalculator=Resolution,
        OutputFilenameBuilder=Filename,
        CodecParameterAssembler=CodecAssembler,
        AudioCodecArgsBuilder=AudioCodec,
        AudioFilterBuilder=AudioFilter,
        VideoFilterBuilder=VideoFilter,
        MediaProbeAdapter=Probe,
        Resolver=Resolver,
        Emitter=Emitter,
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

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
    def test_audio_filter_applied_via_emitter_blocks(self):
        """Emitter returning a block with FilterArgs lands the per-track filter in the command."""
        from Features.AudioNormalization.AudioFilterEmitter import TrackBlock
        Block = TrackBlock(
            Label='Original', Language='eng', Strategy='linear',
            MapArgs=['-map', '0:a:0'],
            CodecArgs=['-c:a:0', 'eac3'],
            FilterArgs=['-filter:a:0', 'loudnorm=I=-23:linear=true'],
            MetadataArgs=['-metadata:s:a:0', 'language=eng'],
            DispositionArgs=['-disposition:a:0', '0'],
        )
        Resolver = MagicMock()
        Resolver.GetEffectivePolicy = lambda Mf: {'Enabled': True}
        Emitter = MagicMock()
        Emitter.EmitTracks = lambda Mf, P, AudioStreams=None, LibraryDefault=None: [Block]
        Shape = _MakeShape()
        Shape.Resolver = Resolver
        Shape.Emitter = Emitter
        Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-filter:a:0' in Spec.Command
        assert 'loudnorm=I=-23:linear=true' in Spec.Command

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C8
    def test_audio_stream_copy_when_emitter_empty(self):
        """No policy / no emitter blocks -> fallback to single-stream -c:a copy."""
        Spec = _MakeShape().Build(_MakeMediaFile(), MagicMock(), _MakeContext())
        assert '-c:a copy' in Spec.Command
