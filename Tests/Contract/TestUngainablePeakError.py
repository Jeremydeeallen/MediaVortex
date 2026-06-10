# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
"""Verify UngainablePeakError typed exception carries diagnostic context and is a RuntimeError subclass."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.UngainablePeakError import UngainablePeakError


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
class TestUngainablePeakError(unittest.TestCase):
    """C6: UngainablePeakError typed exception with diagnostic attributes."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
    def test_instantiation_with_all_fields(self):
        """UngainablePeakError accepts the five diagnostic positional arguments."""
        Err = UngainablePeakError(MediaFileId=12345, SourceIntegratedLufs=-30.5, Gain=7.5, PredictedPeak=4.5, TargetTp=-2)
        self.assertIsInstance(Err, UngainablePeakError)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
    def test_attribute_access(self):
        """Diagnostic attributes are accessible after construction."""
        Err = UngainablePeakError(MediaFileId=12345, SourceIntegratedLufs=-30.5, Gain=7.5, PredictedPeak=4.5, TargetTp=-2)
        self.assertEqual(Err.MediaFileId, 12345)
        self.assertEqual(Err.SourceIntegratedLufs, -30.5)
        self.assertEqual(Err.Gain, 7.5)
        self.assertEqual(Err.PredictedPeak, 4.5)
        self.assertEqual(Err.TargetTp, -2)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
    def test_is_runtimeerror_subclass(self):
        """UngainablePeakError isinstance RuntimeError so existing catch-RuntimeError sites still work."""
        Err = UngainablePeakError(MediaFileId=1, SourceIntegratedLufs=-30.0, Gain=7.0, PredictedPeak=4.0, TargetTp=-2)
        self.assertIsInstance(Err, RuntimeError)
        self.assertTrue(issubclass(UngainablePeakError, RuntimeError))


if __name__ == '__main__':
    unittest.main()
