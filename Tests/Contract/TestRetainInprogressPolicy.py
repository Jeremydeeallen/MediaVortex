# directive: transcode-flow-canonical | # see transcode.ST7
import unittest

from Features.QualityTesting.Disposition.RetainInprogressPolicy import RetainInprogressPolicy


# directive: transcode-flow-canonical | # see transcode.ST7
class TestRetainInprogressPolicy(unittest.TestCase):

    # directive: transcode-flow-canonical | # see transcode.ST7
    def setUp(self):
        self.Policy = RetainInprogressPolicy()

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_test_mode_retains(self):
        """TestMode retains inprogress for A/B test comparison."""
        self.assertTrue(self.Policy.ShouldRetain('TestMode'))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_transcode_failed_does_not_retain(self):
        """TranscodeFailed cleans up (broken output)."""
        self.assertFalse(self.Policy.ShouldRetain('TranscodeFailed'))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_below_min_does_not_retain(self):
        """VmafBelowMin cleans up (Requeue schedules new attempt)."""
        self.assertFalse(self.Policy.ShouldRetain('VmafBelowMin'))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_compliance_gate_failed_does_not_retain(self):
        """ComplianceGateFailed cleans up (staged file is non-compliant; keeping it is misleading)."""
        self.assertFalse(self.Policy.ShouldRetain('ComplianceGateFailed'))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_empty_reason_does_not_retain(self):
        """Missing reason cleans up (safe default)."""
        self.assertFalse(self.Policy.ShouldRetain(''))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_unknown_reason_does_not_retain(self):
        """Unknown reason cleans up (open-closed: unknown reasons default to safe)."""
        self.assertFalse(self.Policy.ShouldRetain('BogusReason'))


if __name__ == '__main__':
    unittest.main()
