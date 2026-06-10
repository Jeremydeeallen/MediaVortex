# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Adjustments.AdjustmentRegistry import AdjustmentRegistry
from Features.TranscodeJob.Adjustments.CrfAdjustmentCalculator import CrfAdjustmentCalculator


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
class TestAdjustmentRegistry(unittest.TestCase):
    """Verify Phase 1 registry: 'cq' active, 'vbr' reserved (raises KeyError)."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_get_cq_returns_crf_calculator(self):
        """AdjustmentRegistry().Get('cq') returns a CrfAdjustmentCalculator instance."""
        Reg = AdjustmentRegistry()
        Calc = Reg.Get('cq')
        self.assertIsInstance(Calc, CrfAdjustmentCalculator)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def test_get_vbr_raises_keyerror(self):
        """AdjustmentRegistry().Get('vbr') raises KeyError -- NVENC slot reserved for Phase 2."""
        Reg = AdjustmentRegistry()
        with self.assertRaises(KeyError):
            Reg.Get('vbr')


if __name__ == '__main__':
    unittest.main()
