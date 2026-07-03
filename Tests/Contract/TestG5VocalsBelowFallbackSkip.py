# directive: audio-dialog-boost-real | # see audio-normalization.C8
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _DefaultRules():
    return {
        'TargetIntegratedLufs': -23.0,
        'TargetTruePeakDbtp': -2.0,
        'SampleLimitHeadroomDb': 3.0,
        'AcceptableAudioCodecsCsv': 'aac,ac3,eac3,mp3,opus',
        'DialogBoostTargetLufs': -20.0,
        'DialogBoostTargetLra': 5.0,
        'Track0Codec': 'opus',
        'Track1Codec': 'opus',
        'Track0BitratePerChannelKbps': 48,
        'Track0MinPerChannelKbps': 48,
        'Track1StereoBitrateKbps': 64,
        'Track1VocalsRmsFallbackDbfs': -50.0,
        'VocalsBoostDb': 5.0,
        'InstrumentalAttenDb': 3.0,
        'PremixCompressorThreshold': 0.030,
        'PremixCompressorRatio': 9.0,
        'PremixCompressorMakeupDb': 3.0,
        'PremixDynaudnormFrameLen': 150,
        'PremixDynaudnormGaussSize': 13,
    }


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _MakeMediaFile():
    Mf = MagicMock()
    Mf.Id = 1
    Mf.AudioChannels = 6
    Mf.SourceIntegratedLufs = -24.0
    Mf.SourceLoudnessRangeLU = 8.0
    Mf.SourceTruePeakDbtp = -3.0
    Mf.SourceIntegratedThresholdLufs = -34.0
    Mf.AudioStreamLanguageDetectionsJson = None
    return Mf


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _MakeEmitter():
    Detector = MagicMock()
    Detection = MagicMock()
    Detection.StreamLanguages = [MagicMock(StreamIndex=0, Language='eng')]
    Detector.Detect.return_value = Detection
    Resolver = MagicMock()
    Result = MagicMock()
    Result.Plan = {'Language': 'eng'}
    Resolver.PickDefaultLanguage.return_value = Result
    RulesRepo = MagicMock()
    RulesRepo.GetRules.return_value = _DefaultRules()
    return AudioFilterEmitter(LanguageDetectorInstance=Detector, DispositionResolver=Resolver, RulesRepo=RulesRepo)


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _Policy():
    P = MagicMock()
    P.LanguageDefault = 'eng'
    P.EnableSpeechLanguageDetection = False
    return P


# directive: audio-dialog-boost-real | # see audio-normalization.C8
class TestG5VocalsBelowFallbackSkip(unittest.TestCase):
    """G5: when vocals-stem RMS is below Track1VocalsRmsFallbackDbfs, Track 1 (Dialog Boost) MUST NOT be emitted; only Track 0 ships."""

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_should_emit_false_when_vocals_rms_at_threshold(self):
        Emitter = _MakeEmitter()
        self.assertFalse(Emitter._ShouldEmitDialogBoost('/tmp/premix.wav', VocalsRmsDbfs=-50.0, VocalsFallbackDbfs=-50.0))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_should_emit_false_when_vocals_rms_below_threshold(self):
        Emitter = _MakeEmitter()
        self.assertFalse(Emitter._ShouldEmitDialogBoost('/tmp/premix.wav', VocalsRmsDbfs=-62.0, VocalsFallbackDbfs=-50.0))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_should_emit_true_when_vocals_rms_above_threshold(self):
        Emitter = _MakeEmitter()
        self.assertTrue(Emitter._ShouldEmitDialogBoost('/tmp/premix.wav', VocalsRmsDbfs=-30.0, VocalsFallbackDbfs=-50.0))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_should_emit_false_when_premix_path_missing(self):
        Emitter = _MakeEmitter()
        self.assertFalse(Emitter._ShouldEmitDialogBoost(None, VocalsRmsDbfs=-20.0, VocalsFallbackDbfs=-50.0))
        self.assertFalse(Emitter._ShouldEmitDialogBoost('', VocalsRmsDbfs=-20.0, VocalsFallbackDbfs=-50.0))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_should_emit_true_when_premix_present_but_rms_none(self):
        Emitter = _MakeEmitter()
        self.assertTrue(Emitter._ShouldEmitDialogBoost('/tmp/premix.wav', VocalsRmsDbfs=None, VocalsFallbackDbfs=-50.0))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_emit_tracks_returns_only_track0_when_vocals_below_fallback(self):
        Emitter = _MakeEmitter()
        Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {'default': 1}}]
        Blocks = Emitter.EmitTracks(
            _MakeMediaFile(), _Policy(),
            AudioStreams=Streams, LibraryDefault='eng',
            DemucsPremixPath='/tmp/premix.wav', VocalsRmsDbfs=-62.0,
        )
        self.assertEqual(len(Blocks), 1)
        self.assertEqual(Blocks[0].Label, 'Original')

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_emit_tracks_returns_both_when_vocals_above_fallback(self):
        Emitter = _MakeEmitter()
        Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {'default': 1}}]
        Blocks = Emitter.EmitTracks(
            _MakeMediaFile(), _Policy(),
            AudioStreams=Streams, LibraryDefault='eng',
            DemucsPremixPath='/tmp/premix.wav', VocalsRmsDbfs=-30.0,
        )
        self.assertEqual(len(Blocks), 2)
        self.assertEqual(Blocks[0].Label, 'Original')
        self.assertEqual(Blocks[1].Label, 'Dialog Boost')

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_emit_tracks_track0_is_default_when_track1_skipped(self):
        Emitter = _MakeEmitter()
        Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {'default': 1}}]
        Blocks = Emitter.EmitTracks(
            _MakeMediaFile(), _Policy(),
            AudioStreams=Streams, LibraryDefault='eng',
            DemucsPremixPath='/tmp/premix.wav', VocalsRmsDbfs=-70.0,
        )
        self.assertEqual(len(Blocks), 1)
        self.assertIn('1', Blocks[0].DispositionArgs)

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def test_emit_tracks_track1_gets_default_when_emitted(self):
        Emitter = _MakeEmitter()
        Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {'default': 1}}]
        Blocks = Emitter.EmitTracks(
            _MakeMediaFile(), _Policy(),
            AudioStreams=Streams, LibraryDefault='eng',
            DemucsPremixPath='/tmp/premix.wav', VocalsRmsDbfs=-20.0,
        )
        self.assertEqual(len(Blocks), 2)
        self.assertIn('0', Blocks[0].DispositionArgs)
        self.assertIn('1', Blocks[1].DispositionArgs)


if __name__ == '__main__':
    unittest.main()
