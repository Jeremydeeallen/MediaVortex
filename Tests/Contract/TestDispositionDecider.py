import unittest

from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.Disposition.Disposition import Disposition


# directive: transcode-flow-canonical | # see transcode.ST7
def DefaultGate(**Overrides):
    """Build a GateConfig dict with sane defaults; override specific fields per test."""
    Cfg = {
        'QualityTestEnabled': True,
        'VmafAutoReplaceMinThreshold': 80.0,
        'VmafAutoReplaceMaxThreshold': 97.0,
        'WhenVmafUnavailable': 'block',
    }
    Cfg.update(Overrides)
    return Cfg


# directive: transcode-flow-canonical | # see transcode.ST7
class TestPostTranscodeDispositionDecider(unittest.TestCase):
    """Branch coverage of pure-function disposition decider."""

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_failed_transcode_returns_reject_transcodefailed(self):
        """Success=False -> Reject/TranscodeFailed regardless of other inputs."""
        Attempt = {'Success': False, 'OldSize': 1000, 'NewSize': 0, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Reject')
        self.assertEqual(Result.Reason, 'TranscodeFailed')

    # directive: transcode-flow-canonical | # see transcode.ST7 -- C16 global-off restore
    def test_global_off_returns_replace_qualitytestinggloballydisabled(self):
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(QualityTestEnabled=False))
        self.assertEqual(Result.Action, 'Replace')
        self.assertEqual(Result.Reason, 'QualityTestingGloballyDisabled')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_quality_test_not_required_returns_replace(self):
        """Per-attempt QualityTestRequired=False -> Replace/QualityTestNotRequired (StreamCopy already verified inline via checksum)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': False, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Replace')
        self.assertEqual(Result.Reason, 'QualityTestNotRequired')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_savings_returns_reject(self):
        """NewSize >= OldSize -> Reject/NoSavings."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 1000, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Reject')
        self.assertEqual(Result.Reason, 'NoSavings')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_savings_newer_larger_returns_reject(self):
        """NewSize > OldSize (encode grew the file) -> Reject/NoSavings."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 1200, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Reject')
        self.assertEqual(Result.Reason, 'NoSavings')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_below_min_returns_requeue(self):
        """VMAF below VmafAutoReplaceMinThreshold -> Requeue/VmafBelowMin (dispatcher schedules new attempt)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 70.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMinThreshold=80.0))
        self.assertEqual(Result.Action, 'Requeue')
        self.assertEqual(Result.Reason, 'VmafBelowMin')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_in_range_returns_replace(self):
        """VMAF in [min, max] -> Replace/VmafPassed."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Replace')
        self.assertEqual(Result.Reason, 'VmafPassed')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_at_min_boundary_returns_replace(self):
        """VMAF at Min boundary -> Replace (inclusive)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 80.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMinThreshold=80.0))
        self.assertEqual(Result.Action, 'Replace')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_at_max_boundary_returns_replace(self):
        """VMAF at Max boundary -> Replace (inclusive)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 97.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMaxThreshold=97.0))
        self.assertEqual(Result.Action, 'Replace')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_above_max_returns_reject(self):
        """VMAF above Max -> Reject/VmafAboveMax (encode too good = source already adequate)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 99.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMaxThreshold=97.0))
        self.assertEqual(Result.Action, 'Reject')
        self.assertEqual(Result.Reason, 'VmafAboveMax')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_vmaf_yet_returns_pending(self):
        """VMAF=None with quality test required -> Pending/AwaitingVmaf."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Pending')
        self.assertEqual(Result.Reason, 'AwaitingVmaf')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_string_coerces_to_float(self):
        """VmafScore as numeric string still parses (DB / JSON path tolerance)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': '90.5'}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Replace')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_vmaf_non_numeric_string_treated_as_missing(self):
        """Unparseable VmafScore -> Pending/AwaitingVmaf."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 'invalid'}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Pending')
        self.assertEqual(Result.Reason, 'AwaitingVmaf')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_returns_disposition_value_object(self):
        """Decide returns a Disposition value object (LSP: typed return)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertIsInstance(Result, Disposition)

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_bypass_replace_action_ever_returned(self):
        """Guard: no combination of inputs returns Action='BypassReplace' (C6 retirement)."""
        Cases = [
            {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': False, 'VmafScore': None},
            {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': None},
            {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 90.0},
            {'Success': False, 'OldSize': 1000, 'NewSize': 0, 'QualityTestRequired': True, 'VmafScore': None},
        ]
        for Case in Cases:
            for Enabled in (True, False):
                Result = PostTranscodeDispositionDecider().Decide(Case, DefaultGate(QualityTestEnabled=Enabled))
                self.assertNotEqual(Result.Action, 'BypassReplace', f"Decider returned BypassReplace on case {Case} QualityTestEnabled={Enabled}")


if __name__ == '__main__':
    unittest.main()
