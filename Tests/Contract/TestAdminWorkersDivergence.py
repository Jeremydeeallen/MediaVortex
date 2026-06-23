import unittest

from Features.Admin.Workers.AdminWorkersRepository import _DeriveDivergence


# directive: worker-runtime-state | # see admin-workers.C6
class TestAdminWorkersDivergence(unittest.TestCase):

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_fresh_compatible_pair_no_divergence(self):
        self.assertFalse(_DeriveDivergence('Online', 'Idle', 10, 60))
        self.assertFalse(_DeriveDivergence('Online', 'Encoding', 5, 60))
        self.assertFalse(_DeriveDivergence('Paused', 'Paused', 5, 60))
        self.assertFalse(_DeriveDivergence('Paused', 'Draining', 5, 60))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_stale_runtime_under_online_intent_diverges(self):
        self.assertTrue(_DeriveDivergence('Online', 'Idle', 120, 60))
        self.assertTrue(_DeriveDivergence('Online', None, 120, 60))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_active_disagreement_persists_past_threshold(self):
        self.assertTrue(_DeriveDivergence('Online', 'Paused', 120, 60))
        self.assertTrue(_DeriveDivergence('Paused', 'Encoding', 120, 60))
        self.assertTrue(_DeriveDivergence('Online', 'Faulted:mountfail', 120, 60))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_active_disagreement_within_threshold_does_not_fire(self):
        self.assertFalse(_DeriveDivergence('Paused', 'Encoding', 10, 60))
        self.assertFalse(_DeriveDivergence('Online', 'Paused', 5, 60))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_empty_status_returns_false(self):
        self.assertFalse(_DeriveDivergence('', 'Idle', 10, 60))
        self.assertFalse(_DeriveDivergence(None, 'Idle', 10, 60))


if __name__ == '__main__':
    unittest.main()
