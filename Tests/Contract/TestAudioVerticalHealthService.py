import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.SelfHealing.AudioVerticalHealthService import AudioVerticalHealthService
from Features.AudioNormalization.SelfHealing.AudioVerticalHealthComposition import BuildAudioVerticalHealthService


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class _StubInvariant:
    """Minimal IAudioVerticalInvariant stub returning fixed Detect output."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def __init__(self, Name, Returns=None):
        self.Name = Name
        self.Returns = Returns or []

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        return list(self.Returns)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class _StubRemediation:
    """Minimal IAudioVerticalRemediation stub recording Apply calls."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def __init__(self, Name, Result=None):
        self.Name = Name
        self.Calls = []
        self.Result = Result

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        self.Calls.append(list(RowIds))
        return self.Result if self.Result is not None else len(RowIds)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class TestAudioVerticalHealthService(unittest.TestCase):
    """H1: orchestrator runs invariant -> remediation pairs, audits each result, never raises into caller."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def test_runs_each_invariant_once_per_cycle(self):
        I1 = _StubInvariant('A', [1, 2])
        I2 = _StubInvariant('B', [])
        R1 = _StubRemediation('A')
        R2 = _StubRemediation('B')
        Svc = AudioVerticalHealthService([I1, I2], {'A': R1, 'B': R2})
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Outcomes = Svc.RunCycle()
        self.assertEqual([O['Invariant'] for O in Outcomes], ['A', 'B'])
        self.assertEqual(Outcomes[0]['Detected'], 2)
        self.assertEqual(Outcomes[0]['Remediated'], 2)
        self.assertEqual(Outcomes[1]['Detected'], 0)
        self.assertEqual(Outcomes[1]['Remediated'], 0)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def test_remediation_skipped_when_nothing_detected(self):
        I1 = _StubInvariant('A', [])
        R1 = _StubRemediation('A')
        Svc = AudioVerticalHealthService([I1], {'A': R1})
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Svc.RunCycle()
        self.assertEqual(R1.Calls, [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def test_invariant_exception_swallowed_and_audited(self):
        BoomI = _StubInvariant('A', [])
        BoomI.Detect = lambda: (_ for _ in ()).throw(RuntimeError('boom'))
        Svc = AudioVerticalHealthService([BoomI], {})
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Outcomes = Svc.RunCycle()
        self.assertEqual(Outcomes[0]['Detected'], 0)

    # directive: audio-vertical-live-evidence | # see audio-normalization.H1
    def test_remediation_batch_cap_protects_cycle_time(self):
        I1 = _StubInvariant('A', list(range(500)))
        R1 = _StubRemediation('A')
        Svc = AudioVerticalHealthService([I1], {'A': R1}, RemediationBatch=50)
        with patch(
            'Features.AudioNormalization.SelfHealing.AudioVerticalHealthService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Outcomes = Svc.RunCycle()
        self.assertEqual(len(R1.Calls[0]), 50)
        self.assertEqual(Outcomes[0]['Detected'], 500)
        self.assertEqual(Outcomes[0]['Remediated'], 50)
        self.assertIn('capped', (Outcomes[0]['Notes'] or ''))

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def test_composition_root_returns_runnable_service(self):
        Svc = BuildAudioVerticalHealthService()
        Names = [I.Name for I in Svc.Invariants]
        self.assertIn('PendingQueueWithoutPolicyJson', Names)
        self.assertIn('SuccessfulAttemptWithoutTracksEmitted', Names)
        self.assertIn('StaleOperatorReview', Names)
        self.assertIn('InvalidMeasurementWithoutRemeasure', Names)
        self.assertIn('PreVerticalTranscodedFile', Names)
        self.assertIn('ConsistencyBandDeviantWithComplete', Names)
        for N in Names:
            self.assertIn(N, Svc.Remediations)


if __name__ == '__main__':
    unittest.main()
