import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.SelfHealing.AudioVerticalHealthService import AudioVerticalHealthService


# directive: audio-vertical-phase-1-completion | # see directive.md P2
class _StubInvariant:
    """Returns a fixed Detect list."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def __init__(self, Name, Returns):
        self.Name = Name
        self.Returns = list(Returns or [])

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def Detect(self):
        return list(self.Returns)


# directive: audio-vertical-phase-1-completion | # see directive.md P2
class _StubRemediation:
    """Records every Apply call so the test can assert it was (or was not) invoked."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def __init__(self, Name):
        self.Name = Name
        self.Calls = []

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def Apply(self, RowIds):
        self.Calls.append(list(RowIds))
        return len(RowIds)


# directive: audio-vertical-phase-1-completion | # see directive.md P2
class TestH1FixtureDryRun(unittest.TestCase):
    """DryRun runs Detect but never Remediation.Apply; audit row carries the DRY_RUN prefix."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def test_dry_run_skips_remediation_apply(self):
        Inv = _StubInvariant('A', [1, 2, 3, 4, 5])
        Rem = _StubRemediation('A')
        Svc = AudioVerticalHealthService([Inv], {'A': Rem}, DryRun=True)
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            MockDb.return_value = MagicMock()
            Svc.RunCycle()
        self.assertEqual(Rem.Calls, [], "DryRun must never invoke Remediation.Apply")

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def test_dry_run_audit_row_carries_prefix(self):
        Inv = _StubInvariant('B', [10, 20])
        Rem = _StubRemediation('B')
        Svc = AudioVerticalHealthService([Inv], {'B': Rem}, DryRun=True)
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            MockDb.return_value = MagicMock()
            Outcomes = Svc.RunCycle()
        self.assertEqual(Outcomes[0]['Detected'], 2)
        self.assertEqual(Outcomes[0]['Remediated'], 0)
        self.assertIn('DRY_RUN: would have remediated 2', Outcomes[0]['Notes'] or '')

    # directive: audio-vertical-phase-1-completion | # see directive.md P2
    def test_dry_run_false_runs_normally(self):
        Inv = _StubInvariant('C', [100, 200])
        Rem = _StubRemediation('C')
        Svc = AudioVerticalHealthService([Inv], {'C': Rem}, DryRun=False)
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            MockDb.return_value = MagicMock()
            Outcomes = Svc.RunCycle()
        self.assertEqual(Rem.Calls, [[100, 200]])
        self.assertEqual(Outcomes[0]['Remediated'], 2)
        self.assertIsNone(Outcomes[0]['Notes'])


if __name__ == '__main__':
    unittest.main()
