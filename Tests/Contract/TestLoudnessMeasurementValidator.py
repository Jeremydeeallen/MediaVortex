import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.LoudnessMeasurementValidator import LoudnessMeasurementValidator


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
def _Mf(**Kwargs):
    """Build a MediaFile-shaped stub from keyword args; defaults populate to a valid measurement."""
    Defaults = {
        'SourceIntegratedLufs': -23.5,
        'SourceLoudnessRangeLU': 9.0,
        'SourceTruePeakDbtp': -1.5,
        'SourceIntegratedThresholdLufs': -33.0,
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class TestLoudnessMeasurementValidator(unittest.TestCase):
    """C13: invalid measurement when any of 4 cols NULL OR SourceIntegratedLufs <= -60."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_valid_when_all_four_present_and_above_floor(self):
        V = LoudnessMeasurementValidator()
        self.assertTrue(V.IsValid(_Mf()))
        self.assertIsNone(V.Reason(_Mf()))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_invalid_when_integrated_null(self):
        V = LoudnessMeasurementValidator()
        self.assertFalse(V.IsValid(_Mf(SourceIntegratedLufs=None)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_invalid_when_lra_null(self):
        V = LoudnessMeasurementValidator()
        self.assertFalse(V.IsValid(_Mf(SourceLoudnessRangeLU=None)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_invalid_when_true_peak_null(self):
        V = LoudnessMeasurementValidator()
        self.assertFalse(V.IsValid(_Mf(SourceTruePeakDbtp=None)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_invalid_when_threshold_null(self):
        V = LoudnessMeasurementValidator()
        self.assertFalse(V.IsValid(_Mf(SourceIntegratedThresholdLufs=None)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_invalid_at_silence_floor(self):
        V = LoudnessMeasurementValidator()
        self.assertFalse(V.IsValid(_Mf(SourceIntegratedLufs=-70.0)))
        self.assertFalse(V.IsValid(_Mf(SourceIntegratedLufs=-60.0)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_valid_just_above_floor(self):
        V = LoudnessMeasurementValidator()
        self.assertTrue(V.IsValid(_Mf(SourceIntegratedLufs=-59.5)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_reason_is_stable_string(self):
        V = LoudnessMeasurementValidator()
        self.assertEqual(V.Reason(_Mf(SourceIntegratedLufs=-70.0)), 'invalid_loudness_measurement')


if __name__ == '__main__':
    unittest.main()
