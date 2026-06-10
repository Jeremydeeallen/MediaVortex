import unittest

from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.Disposition.Disposition import Disposition


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
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


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
class TestPostTranscodeDispositionDecider(unittest.TestCase):
    """Branch coverage of pure-function disposition decider."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_failed_transcode_returns_discard_transcodefailed(self):
        """Success=False -> Discard/TranscodeFailed regardless of other inputs."""
        Attempt = {'Success': False, 'OldSize': 1000, 'NewSize': 0, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Discard')
        self.assertEqual(Result.Reason, 'TranscodeFailed')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_quality_test_globally_disabled_returns_bypassreplace(self):
        """QualityTestEnabled=False (gate-wide) -> BypassReplace/QualityTestingGloballyDisabled."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(QualityTestEnabled=False))
        self.assertEqual(Result.Action, 'BypassReplace')
        self.assertEqual(Result.Reason, 'QualityTestingGloballyDisabled')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_quality_test_not_required_returns_bypassreplace(self):
        """Per-attempt QualityTestRequired=False -> BypassReplace/QualityTestNotRequired."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': False, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'BypassReplace')
        self.assertEqual(Result.Reason, 'QualityTestNotRequired')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_no_savings_returns_discard(self):
        """NewSize >= OldSize -> Discard/NoSavings."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 1000, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Discard')
        self.assertEqual(Result.Reason, 'NoSavings')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_no_savings_newer_larger_returns_discard(self):
        """NewSize > OldSize (encode grew the file) -> Discard/NoSavings."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 1200, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Discard')
        self.assertEqual(Result.Reason, 'NoSavings')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_below_min_returns_requeue(self):
        """VMAF below VmafAutoReplaceMinThreshold -> Requeue/VmafBelowMin (try again with adjusted CRF)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 70.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMinThreshold=80.0))
        self.assertEqual(Result.Action, 'Requeue')
        self.assertEqual(Result.Reason, 'VmafBelowMin')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_in_range_returns_replace(self):
        """VMAF in [min, max] -> Replace/VmafPassed."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Replace')
        self.assertEqual(Result.Reason, 'VmafPassed')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_at_min_boundary_returns_replace(self):
        """VMAF exactly at Min boundary -> Replace (boundary is inclusive on Min side)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 80.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMinThreshold=80.0))
        self.assertEqual(Result.Action, 'Replace')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_at_max_boundary_returns_replace(self):
        """VMAF exactly at Max boundary -> Replace (boundary is inclusive on Max side per old code)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 97.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMaxThreshold=97.0))
        self.assertEqual(Result.Action, 'Replace')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_above_max_returns_noreplace(self):
        """VMAF above Max -> NoReplace/VmafAboveMax (encode too good = source already adequate)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 99.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate(VmafAutoReplaceMaxThreshold=97.0))
        self.assertEqual(Result.Action, 'NoReplace')
        self.assertEqual(Result.Reason, 'VmafAboveMax')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_no_vmaf_yet_returns_pending(self):
        """VMAF=None with quality test required -> Pending/AwaitingVmaf."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': None}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Pending')
        self.assertEqual(Result.Reason, 'AwaitingVmaf')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_string_coerces_to_float(self):
        """VmafScore as numeric string still parses (DB / JSON path tolerance)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': '90.5'}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Replace')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_vmaf_non_numeric_string_treated_as_missing(self):
        """Unparseable VmafScore -> Pending/AwaitingVmaf (don't crash; fall to no-vmaf branch)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 'invalid'}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertEqual(Result.Action, 'Pending')
        self.assertEqual(Result.Reason, 'AwaitingVmaf')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def test_returns_disposition_value_object(self):
        """Decide returns a Disposition value object (LSP: typed return)."""
        Attempt = {'Success': True, 'OldSize': 1000, 'NewSize': 800, 'QualityTestRequired': True, 'VmafScore': 90.0}
        Result = PostTranscodeDispositionDecider().Decide(Attempt, DefaultGate())
        self.assertIsInstance(Result, Disposition)


if __name__ == '__main__':
    unittest.main()
