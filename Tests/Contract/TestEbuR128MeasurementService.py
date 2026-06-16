import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Measurement.EbuR128MeasurementService import (
    ParseSummary,
    LoudnessResult,
    EbuR128MeasurementService,
)


SAMPLE_SUMMARY = (
    "[Parsed_ebur128_0 @ 0x55] Summary:\n"
    "\n"
    "  Integrated loudness:\n"
    "    I:         -23.5 LUFS\n"
    "    Threshold: -33.5 LUFS\n"
    "\n"
    "  Loudness range:\n"
    "    LRA:        9.0 LU\n"
    "    Threshold: -43.5 LUFS\n"
    "    LRA low:  -28.0 LUFS\n"
    "    LRA high: -19.0 LUFS\n"
    "\n"
    "  True peak:\n"
    "    Peak:      -1.5 dBFS\n"
)


PROGRESS_BEFORE_SUMMARY = (
    "[Parsed_ebur128_0 @ 0x55] t: 1.00  I: -70.0 LUFS  LRA: 0.0 LU  Peak: -inf dBFS\n"
    "[Parsed_ebur128_0 @ 0x55] t: 5.00  I: -25.0 LUFS  LRA: 5.0 LU  Peak: -3.0 dBFS\n"
    + SAMPLE_SUMMARY
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
class TestParseSummary(unittest.TestCase):
    """C21 absorption: ParseSummary anchors on the Summary block, not first-match progress lines."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_summary_block_produces_canonical_values(self):
        R = ParseSummary(SAMPLE_SUMMARY)
        self.assertIsInstance(R, LoudnessResult)
        self.assertAlmostEqual(R.IntegratedLufs, -23.5)
        self.assertAlmostEqual(R.LoudnessRangeLU, 9.0)
        self.assertAlmostEqual(R.TruePeakDbtp, -1.5)
        self.assertAlmostEqual(R.IntegratedThresholdLufs, -33.5)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_progress_lines_are_ignored(self):
        R = ParseSummary(PROGRESS_BEFORE_SUMMARY)
        self.assertAlmostEqual(R.IntegratedLufs, -23.5)
        self.assertAlmostEqual(R.LoudnessRangeLU, 9.0)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_returns_none_when_summary_absent_and_no_match(self):
        self.assertIsNone(ParseSummary("not a valid ebur128 stderr"))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_falls_back_to_last_occurrences_without_summary_block(self):
        Stderr = (
            "Integrated loudness:\n"
            "    I:         -19.0 LUFS\n"
            "    Threshold: -29.0 LUFS\n"
            "LRA: 7.0 LU\n"
            "Peak: -2.0 dBFS\n"
        )
        R = ParseSummary(Stderr)
        self.assertIsNotNone(R)
        self.assertAlmostEqual(R.IntegratedLufs, -19.0)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
class TestEbuR128MeasurementServiceImport(unittest.TestCase):
    """C21: the absorbed service is importable at the new path with the renamed class."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_class_importable(self):
        self.assertTrue(callable(EbuR128MeasurementService))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def test_default_timeout_is_ten_minutes(self):
        self.assertEqual(EbuR128MeasurementService.DEFAULT_TIMEOUT_SECONDS, 600)


if __name__ == '__main__':
    unittest.main()
