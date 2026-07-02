# directive: audio-dialog-boost-real | # see audio-normalization.C33 -- BUG-0074
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError


def _Rules():
    return {
        'Track0BitratePerChannelKbps': 48, 'Track0MinPerChannelKbps': 32,
        'Track1StereoBitrateKbps': 64, 'Track1VocalsRmsFallbackDbfs': -50,
        'TargetIntegratedLufs': -23.0, 'TargetTruePeakDbtp': -2.0,
        'SampleLimitHeadroomDb': 3.0,
        'DialogBoostTargetLufs': -20.0, 'DialogBoostTargetLra': 5.0,
        'VocalsBoostDb': 4.0, 'InstrumentalAttenDb': 3.0,
        'PremixCompressorThreshold': -20.0, 'PremixCompressorRatio': 2.5,
        'PremixCompressorMakeupDb': 3.0,
        'PremixDynaudnormFrameLen': 500, 'PremixDynaudnormGaussSize': 3,
        'Track0Codec': 'opus', 'Track1Codec': 'opus',
    }


def _RulesRepo():
    R = MagicMock()
    R.GetRules = lambda: _Rules()
    return R


def _MediaFile(Ch):
    M = MagicMock()
    M.AudioChannels = Ch
    M.Id = 91647
    M.AudioStreamLanguageDetectionsJson = None
    return M


def _Policy():
    P = MagicMock()
    P.LanguageDefault = 'eng'
    P.EnableSpeechLanguageDetection = False
    return P


_Streams = [{'index': 0, 'tags': {}, 'disposition': {}}]


class TestAudioChannelsFailLoud(unittest.TestCase):
    """BUG-0074: EmitTracks must not silently guess stereo when AudioChannels is missing."""

    def _Emitter(self):
        return AudioFilterEmitter(RulesRepo=_RulesRepo())

    def test_raises_on_null_audio_channels(self):
        with self.assertRaises(AudioPolicyUnresolvedError) as Ctx:
            self._Emitter().EmitTracks(_MediaFile(None), _Policy(), AudioStreams=_Streams, Rules=_Rules())
        self.assertEqual(Ctx.exception.PolicyName, 'AudioChannelsMissing')
        self.assertIn('91647', Ctx.exception.Reason)
        self.assertIn('BUG-0074', Ctx.exception.Reason)

    def test_raises_on_empty_string_audio_channels(self):
        with self.assertRaises(AudioPolicyUnresolvedError) as Ctx:
            self._Emitter().EmitTracks(_MediaFile('   '), _Policy(), AudioStreams=_Streams, Rules=_Rules())
        self.assertEqual(Ctx.exception.PolicyName, 'AudioChannelsMissing')

    def test_raises_on_unparseable_audio_channels(self):
        with self.assertRaises(AudioPolicyUnresolvedError) as Ctx:
            self._Emitter().EmitTracks(_MediaFile('stereo'), _Policy(), AudioStreams=_Streams, Rules=_Rules())
        self.assertEqual(Ctx.exception.PolicyName, 'AudioChannelsInvalid')

    def test_raises_on_zero_audio_channels(self):
        with self.assertRaises(AudioPolicyUnresolvedError) as Ctx:
            self._Emitter().EmitTracks(_MediaFile(0), _Policy(), AudioStreams=_Streams, Rules=_Rules())
        self.assertEqual(Ctx.exception.PolicyName, 'AudioChannelsInvalid')

    def test_emits_normally_for_valid_channels(self):
        Blocks = self._Emitter().EmitTracks(_MediaFile(6), _Policy(), AudioStreams=_Streams, Rules=_Rules())
        self.assertEqual(len(Blocks), 1)
        self.assertEqual(Blocks[0].Label, 'Original')


if __name__ == '__main__':
    unittest.main()
