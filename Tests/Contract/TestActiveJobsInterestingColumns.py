import unittest

from Features.Activity.Services.DashboardSnapshotService import _EstimateSavings, DashboardSnapshotService


# directive: worker-runtime-state | # see activity.C2
class TestActiveJobsInterestingColumns(unittest.TestCase):

    # directive: worker-runtime-state | # see activity.C2
    def test_estimate_savings_transcode_with_bitrates(self):
        Result = _EstimateSavings('Transcode', 1_000_000_000, 5000, 2500)
        self.assertEqual(Result, 500_000_000 - 1_000_000_000)

    # directive: worker-runtime-state | # see activity.C2
    def test_estimate_savings_remux_returns_none(self):
        self.assertIsNone(_EstimateSavings('Remux', 1_000_000_000, 5000, 2500))

    # directive: worker-runtime-state | # see activity.C2
    def test_estimate_savings_missing_inputs_returns_none(self):
        self.assertIsNone(_EstimateSavings('Transcode', 0, 5000, 2500))
        self.assertIsNone(_EstimateSavings('Transcode', 1_000_000_000, None, 2500))
        self.assertIsNone(_EstimateSavings('Transcode', 1_000_000_000, 5000, None))

    # directive: worker-runtime-state | # see activity.C5
    def test_snapshot_payload_carries_interesting_fields(self):
        Snap = DashboardSnapshotService().BuildSnapshot()
        Sample = Snap.ActiveJobs[0] if Snap.ActiveJobs else None
        if Sample is None:
            self.skipTest("No active jobs to inspect; live verification still required")
            return
        Names = set(vars(Sample).keys())
        for Field in ('ProcessingMode', 'SourceResolutionCategory', 'TargetResolutionCategory', 'SourceCodec', 'TargetCodec', 'EstimatedSavingsBytes'):
            self.assertIn(Field, Names, f"ActiveJobRow must carry {Field}")


if __name__ == '__main__':
    unittest.main()
