# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Adjustments.CrfAdjustmentCalculator import CrfAdjustmentCalculator
from Features.TranscodeJob.Adjustments.KnobOverrides import KnobOverrides


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
class TestCrfAdjustmentCalculator(unittest.TestCase):
    """Verify CRF-down logic ported from AdaptiveQualityService.CalculateAdjustedCRF."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def setUp(self):
        """Build a fresh calculator per test."""
        self.Calc = CrfAdjustmentCalculator()
        self.Profile = {}
        self.Threshold = 80.0

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_vmaf_below_50_decreases_crf_by_4(self):
        """VMAF < 50 => previous_crf - 4."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 40.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 21)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_vmaf_55_decreases_crf_by_3(self):
        """VMAF 50-60 => previous_crf - 3."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 55.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 22)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_vmaf_65_decreases_crf_by_2(self):
        """VMAF 61-70 => previous_crf - 2."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 65.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 23)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_vmaf_75_decreases_crf_by_1(self):
        """VMAF 71-79 => previous_crf - 1."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 75.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 24)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_vmaf_85_decreases_crf_by_1_safety_branch(self):
        """VMAF >= 80 safety branch returns previous_crf - 1."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 85.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 24)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_floor_at_min_crf_15(self):
        """previous_crf=16, VMAF=40 floors at 15 (not 12)."""
        Result = self.Calc.Calculate({'Quality': 16, 'VMAF': 40.0}, self.Profile, self.Threshold)
        self.assertEqual(Result.CRF, 15)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_returns_knob_overrides_with_only_crf_set(self):
        """Result is KnobOverrides; BitrateKbps and MaxrateKbps are None."""
        Result = self.Calc.Calculate({'Quality': 25, 'VMAF': 65.0}, self.Profile, self.Threshold)
        self.assertIsInstance(Result, KnobOverrides)
        self.assertIsNone(Result.BitrateKbps)
        self.assertIsNone(Result.MaxrateKbps)


if __name__ == '__main__':
    unittest.main()
