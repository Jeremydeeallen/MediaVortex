# directive: transcode-flow-canonical | # see audio-normalization.ST3
import math
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import (
    AudioFilterEmitter,
    _AlimiterArg,
    _BuildTrack0Chain,
    _DbToLinear,
)


# directive: transcode-flow-canonical | # see audio-normalization.ST3
_ALIMITER_RE = re.compile(r"alimiter=[^,]*limit=([0-9.]+)")
_LOUDNORM_RE = re.compile(r"loudnorm=")


# directive: transcode-flow-canonical | # see audio-normalization.ST3
_DEFAULT_RULES = {
    'TargetIntegratedLufs': -23.0,
    'TargetTruePeakDbtp': -2.0,
    'SampleLimitHeadroomDb': 3.0,
    'DialogBoostTargetLufs': -20.0,
    'DialogBoostTargetLra': 5.0,
    'Track0BitratePerChannelKbps': 48,
    'Track0MinPerChannelKbps': 32,
    'Track1StereoBitrateKbps': 64,
    'Track1VocalsRmsFallbackDbfs': -50.0,
    'Track0Codec': 'opus',
    'Track1Codec': 'opus',
}


# directive: transcode-flow-canonical | # see audio-normalization.ST3
def _MediaFile(SrcI, SrcTp, SrcLra=6.0, SrcThresh=-30.0, Channels=2, Codec='eac3'):
    return {
        'SourceIntegratedLufs': SrcI,
        'SourceLoudnessRangeLU': SrcLra,
        'SourceTruePeakDbtp': SrcTp,
        'SourceIntegratedThresholdLufs': SrcThresh,
        'AudioChannels': Channels,
        'AudioCodec': Codec,
        'AudioCorruptSuspect': False,
    }


# directive: transcode-flow-canonical | # see audio-normalization.ST3
class TestAlimiterHelper(unittest.TestCase):

    def test_rejects_above_ceiling(self):
        with self.assertRaises(ValueError):
            _AlimiterArg(1.0001)

    def test_rejects_below_floor(self):
        with self.assertRaises(ValueError):
            _AlimiterArg(0.06)

    def test_accepts_exact_ceiling(self):
        Arg = _AlimiterArg(1.0)
        self.assertIn('limit=1.0000', Arg)

    def test_accepts_exact_floor(self):
        Arg = _AlimiterArg(0.0625)
        self.assertIn('limit=0.0625', Arg)

    def test_emits_full_arg_shape(self):
        Arg = _AlimiterArg(0.5623)
        self.assertEqual(
            Arg,
            'alimiter=level_in=1:level_out=1:limit=0.5623:attack=1:release=50:level=false',
        )


# directive: transcode-flow-canonical | # see audio-normalization.ST3
class TestTrack0ChainShape(unittest.TestCase):

    def test_alimiter_appears_after_loudnorm(self):
        Chain = _BuildTrack0Chain(_MediaFile(SrcI=-17.78, SrcTp=0.34), -23.0, -2.0, 3.0)
        LoudnormPos = Chain.find('loudnorm=')
        AlimiterPos = Chain.find('alimiter=')
        self.assertGreater(LoudnormPos, -1)
        self.assertGreater(AlimiterPos, LoudnormPos)

    def test_limit_matches_effective_target_tp_linear(self):
        Chain = _BuildTrack0Chain(_MediaFile(SrcI=-17.78, SrcTp=0.34), -23.0, -2.0, 3.0)
        Match = _ALIMITER_RE.search(Chain)
        self.assertIsNotNone(Match)
        Expected = _DbToLinear(-5.0)
        self.assertAlmostEqual(float(Match.group(1)), round(Expected, 4), places=4)

    def test_seinfeld_regression_stays_in_range(self):
        Chain = _BuildTrack0Chain(_MediaFile(SrcI=-17.78, SrcTp=0.34, SrcLra=8.1, SrcThresh=-28.38), -23.0, -2.0, 3.0)
        Limit = float(_ALIMITER_RE.search(Chain).group(1))
        self.assertLessEqual(Limit, 1.0)
        self.assertGreaterEqual(Limit, 0.0625)

    def test_xena_regression_stays_in_range(self):
        Chain = _BuildTrack0Chain(_MediaFile(SrcI=-17.84, SrcTp=0.24, SrcLra=6.7, SrcThresh=-28.23), -23.0, -2.0, 3.0)
        Limit = float(_ALIMITER_RE.search(Chain).group(1))
        self.assertLessEqual(Limit, 1.0)
        self.assertGreaterEqual(Limit, 0.0625)


# directive: transcode-flow-canonical | # see audio-normalization.ST3
class TestTrack0ChainMatrix(unittest.TestCase):

    def test_limit_always_in_range_across_source_matrix(self):
        SrcIntegrated = [-30.0, -23.0, -17.0, -12.0, -6.0]
        SrcTruePeak = [-6.0, -3.0, -1.0, 0.0, 0.34, 1.0, 3.0]
        for I in SrcIntegrated:
            for Tp in SrcTruePeak:
                with self.subTest(SrcI=I, SrcTp=Tp):
                    Chain = _BuildTrack0Chain(_MediaFile(SrcI=I, SrcTp=Tp), -23.0, -2.0, 3.0)
                    Match = _ALIMITER_RE.search(Chain)
                    self.assertIsNotNone(Match)
                    Limit = float(Match.group(1))
                    self.assertGreaterEqual(Limit, 0.0625)
                    self.assertLessEqual(Limit, 1.0)


if __name__ == '__main__':
    unittest.main()
