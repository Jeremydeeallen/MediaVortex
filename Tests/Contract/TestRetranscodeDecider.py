import unittest
from unittest.mock import MagicMock

from Features.QualityTesting.Disposition.RetranscodeDecider import RetranscodeDecider


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
class TestRetranscodeDecider(unittest.TestCase):
    """Verifies branch coverage of RetranscodeDecider.Decide."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def test_first_attempt_returns_should_transcode(self):
        """no prior attempt -> (True, None). Previously NameError'd on FilePath."""
        Repo = MagicMock()
        Repo.GetLatestTranscodeAttemptWithVMAF.return_value = None
        Decider = RetranscodeDecider(Repo)
        Result = Decider.Decide(MediaFileId=42)
        self.assertEqual(Result, (True, None))

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def test_preferred_attempt_skips_retranscode(self):
        """Preferred attempt exists -> skip retranscode."""
        Repo = MagicMock()
        Previous = {'PreferredAttempt': True, 'VMAF': 75.0, 'Quality': 22}
        Repo.GetLatestTranscodeAttemptWithVMAF.return_value = Previous
        Decider = RetranscodeDecider(Repo)
        Result = Decider.Decide(MediaFileId=42)
        self.assertEqual(Result, (False, Previous))

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def test_no_vmaf_returns_should_transcode(self):
        """Previous attempt has no VMAF -> retranscode (e.g. quality test never ran)."""
        Repo = MagicMock()
        Previous = {'PreferredAttempt': False, 'VMAF': None, 'Quality': 22}
        Repo.GetLatestTranscodeAttemptWithVMAF.return_value = Previous
        Decider = RetranscodeDecider(Repo)
        Result = Decider.Decide(MediaFileId=42)
        self.assertEqual(Result, (True, Previous))

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def test_high_vmaf_skips_retranscode(self):
        """VMAF >= 80 means acceptable quality -> skip."""
        Repo = MagicMock()
        Previous = {'PreferredAttempt': False, 'VMAF': 85.0, 'Quality': 22}
        Repo.GetLatestTranscodeAttemptWithVMAF.return_value = Previous
        Decider = RetranscodeDecider(Repo)
        Result = Decider.Decide(MediaFileId=42)
        self.assertEqual(Result, (False, Previous))

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def test_low_vmaf_returns_should_retranscode(self):
        """VMAF < 80 -> retranscode with adjusted CRF."""
        Repo = MagicMock()
        Previous = {'PreferredAttempt': False, 'VMAF': 70.0, 'Quality': 22}
        Repo.GetLatestTranscodeAttemptWithVMAF.return_value = Previous
        Decider = RetranscodeDecider(Repo)
        Result = Decider.Decide(MediaFileId=42)
        self.assertEqual(Result, (True, Previous))


if __name__ == '__main__':
    unittest.main()
