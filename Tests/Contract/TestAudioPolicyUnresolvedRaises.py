# directive: audio-dialog-boost-real | # see audio-normalization.C26
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.TranscodeJob.Emit.RemuxShape import RemuxShape
from Features.TranscodeJob.Emit.SubtitleFixShape import SubtitleFixShape
from Features.TranscodeJob.Emit.TranscodeShape import TranscodeShape


# directive: audio-dialog-boost-real | # see audio-normalization.C26
def _MakeMediaFile(Codec='h264', AudioCodec='aac'):
    Mf = MagicMock()
    Mf.Id = 1
    Mf.FileName = 'Test.mkv'
    Mf.Codec = Codec
    Mf.AudioCodec = AudioCodec
    Mf.AudioChannels = 2
    Mf.SourceIntegratedLufs = -24.0
    Mf.SourceLoudnessRangeLU = 8.0
    Mf.SourceTruePeakDbtp = -3.0
    Mf.SourceIntegratedThresholdLufs = -34.0
    Mf.IsInterlaced = None
    return Mf


# directive: audio-dialog-boost-real | # see audio-normalization.C26
def _RemuxContext(HasAudio=True):
    return {
        'InputPath': 'T:\\Shows\\Test.mkv',
        'FFmpegPath': 'C:\\ffmpeg.exe',
        'AudioStreamIndex': 0,
        'HasAudio': HasAudio,
    }


# directive: audio-dialog-boost-real | # see audio-normalization.C26
def _MakeRemuxShape(Policy=None, Blocks=None):
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.CollapseMvSuffix = lambda B: B
    Probe = MagicMock()
    Probe.RunAnalysis = lambda InputPath: None
    Resolver = MagicMock()
    Resolver.GetEffectivePolicy = lambda Mf: Policy
    StreamProbe = MagicMock()
    StreamProbe.Probe = lambda InputPath: [{'index': 0, 'tags': {'language': 'eng'}}]
    Emitter = MagicMock()
    Emitter.EmitTracks.return_value = Blocks if Blocks is not None else []
    return RemuxShape(
        OutputFilenameBuilder=Filename,
        AudioCodecArgsBuilder=MagicMock(),
        MediaProbeAdapter=Probe,
        Resolver=Resolver,
        Emitter=Emitter,
        StreamProbe=StreamProbe,
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C26
def _MakeSubtitleFixShape(Policy=None, Blocks=None):
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.CollapseMvSuffix = lambda B: B
    Probe = MagicMock()
    Analysis = MagicMock()
    Analysis.AudioStreamIndex = 0
    Analysis.SubtitleStreamIndex = 0
    Analysis.AudioCodec = 'aac'
    Probe.RunAnalysis = lambda InputPath: Analysis
    Resolver = MagicMock()
    Resolver.GetEffectivePolicy = lambda Mf: Policy
    StreamProbe = MagicMock()
    StreamProbe.Probe = lambda InputPath: [{'index': 0, 'tags': {'language': 'eng'}}]
    Emitter = MagicMock()
    Emitter.EmitTracks.return_value = Blocks if Blocks is not None else []
    return SubtitleFixShape(
        OutputFilenameBuilder=Filename,
        AudioCodecArgsBuilder=MagicMock(),
        MediaProbeAdapter=Probe,
        Resolver=Resolver,
        Emitter=Emitter,
        StreamProbe=StreamProbe,
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C26
def _MakeTranscodeShape(Policy=None, Blocks=None):
    Resolution = MagicMock()
    Resolution.CalculateTargetResolution = lambda Ps, Src: '1280x720'
    Resolution.CalculateScaleFilter = lambda Src, Tgt, Mf, Ps: None
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.GenerateOutputFileName = lambda Fn, Sr, Tr, Ct, Crf: 'Out-mv.mp4.inprogress'
    Assembler = MagicMock()
    Assembler.AddCodecParameters = lambda Parts, Params, Ps: None
    Assembler.AddFilmGrainParameter = lambda Parts, Params, Ps: None
    Assembler.AddPixelFormatParameter = lambda Parts, Params, Ps: None
    Vf = MagicMock()
    Vf.Build = lambda Ps, Sc, Il: None
    Probe = MagicMock()
    Analysis = MagicMock()
    Analysis.AudioStreamIndex = 0
    Probe.RunAnalysis = lambda InputPath: Analysis
    Resolver = MagicMock()
    Resolver.GetEffectivePolicy = lambda Mf: Policy
    StreamProbe = MagicMock()
    StreamProbe.Probe = lambda InputPath: [{'index': 0, 'tags': {'language': 'eng'}}]
    Emitter = MagicMock()
    Emitter.EmitTracks.return_value = Blocks if Blocks is not None else []
    return TranscodeShape(
        ResolutionCalculator=Resolution,
        OutputFilenameBuilder=Filename,
        CodecParameterAssembler=Assembler,
        VideoFilterBuilder=Vf,
        MediaProbeAdapter=Probe,
        Resolver=Resolver,
        Emitter=Emitter,
        StreamProbe=StreamProbe,
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C26
class TestRemuxShapeUnresolvedPolicy(unittest.TestCase):
    """C26: RemuxShape MUST NOT ship -c:a copy fallback when Policy is None or Blocks list is empty. Instead raise AudioPolicyUnresolvedError (caught + returns None + logs)."""

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_policy_missing(self):
        Shape = _MakeRemuxShape(Policy=None)
        with patch('Features.TranscodeJob.Emit.RemuxShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _RemuxContext())
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_emit_returns_empty_blocks(self):
        Shape = _MakeRemuxShape(Policy=MagicMock(), Blocks=[])
        with patch('Features.TranscodeJob.Emit.RemuxShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _RemuxContext())
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_does_not_emit_c_a_copy_fallback_when_policy_missing(self):
        Shape = _MakeRemuxShape(Policy=None)
        with patch('Features.TranscodeJob.Emit.RemuxShape.LoggingService'):
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), _RemuxContext())
        self.assertIsNone(Spec)


# directive: audio-dialog-boost-real | # see audio-normalization.C26
class TestSubtitleFixShapeUnresolvedPolicy(unittest.TestCase):
    """C26: SubtitleFixShape same contract."""

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_policy_missing(self):
        Shape = _MakeSubtitleFixShape(Policy=None)
        with patch('Features.TranscodeJob.Emit.SubtitleFixShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), {
                'InputPath': 'T:\\Shows\\Test.mkv', 'FFmpegPath': 'C:\\ffmpeg.exe',
                'AudioStreamIndex': 0, 'SubtitleStreamIndex': 0,
            })
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_emit_returns_empty_blocks(self):
        Shape = _MakeSubtitleFixShape(Policy=MagicMock(), Blocks=[])
        with patch('Features.TranscodeJob.Emit.SubtitleFixShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), {
                'InputPath': 'T:\\Shows\\Test.mkv', 'FFmpegPath': 'C:\\ffmpeg.exe',
                'AudioStreamIndex': 0, 'SubtitleStreamIndex': 0,
            })
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)


# directive: audio-dialog-boost-real | # see audio-normalization.C26
class TestTranscodeShapeUnresolvedPolicy(unittest.TestCase):
    """C26: TranscodeShape MUST NOT ship legacy ProfileAudioCeiling reencode fallback when Policy is None or Blocks empty."""

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_policy_missing(self):
        Shape = _MakeTranscodeShape(Policy=None)
        Context = {
            'InputPath': 'T:\\Shows\\Test.mkv',
            'FFmpegPath': 'C:\\ffmpeg.exe',
            'AudioStreamIndex': 0,
            'ProfileSettings': {'ContainerType': 'mp4', 'Quality': 28, 'UseNvidiaHardware': 0, 'Codec': 'libsvtav1'},
            'CodecParameters': [],
        }
        with patch('Features.TranscodeJob.Emit.TranscodeShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), Context)
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)

    # directive: audio-dialog-boost-real | # see audio-normalization.C26
    def test_returns_none_and_logs_when_emit_returns_empty_blocks(self):
        Shape = _MakeTranscodeShape(Policy=MagicMock(), Blocks=[])
        Context = {
            'InputPath': 'T:\\Shows\\Test.mkv',
            'FFmpegPath': 'C:\\ffmpeg.exe',
            'AudioStreamIndex': 0,
            'ProfileSettings': {'ContainerType': 'mp4', 'Quality': 28, 'UseNvidiaHardware': 0, 'Codec': 'libsvtav1'},
            'CodecParameters': [],
        }
        with patch('Features.TranscodeJob.Emit.TranscodeShape.LoggingService') as MockLog:
            Spec = Shape.Build(_MakeMediaFile(), MagicMock(), Context)
        self.assertIsNone(Spec)
        MockLog.LogException.assert_called_once()
        _Msg, Ex, _Cls, _Fn = MockLog.LogException.call_args.args
        self.assertIsInstance(Ex, AudioPolicyUnresolvedError)


if __name__ == '__main__':
    unittest.main()
