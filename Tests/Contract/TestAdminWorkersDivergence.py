import unittest

from Features.Admin.Workers.AdminWorkersRepository import _DeriveDivergence


# directive: worker-runtime-state | # see admin-workers.C6
class TestAdminWorkersDivergence(unittest.TestCase):

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_fresh_compatible_pair_no_divergence(self):
        # Fresh heartbeat + compatible intent/state = no divergence.
        self.assertFalse(_DeriveDivergence('Online', 'Idle', 10, 300))
        self.assertFalse(_DeriveDivergence('Online', 'Encoding', 5, 300))
        self.assertFalse(_DeriveDivergence('Online', 'ClaimingJob', 5, 300))
        self.assertFalse(_DeriveDivergence('Online', 'Scanning', 5, 300))
        self.assertFalse(_DeriveDivergence('Online', 'Initializing', 5, 300))
        self.assertFalse(_DeriveDivergence('Paused', 'Paused', 5, 300))
        self.assertFalse(_DeriveDivergence('Paused', 'Draining', 5, 300))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_fresh_intent_mismatch_diverges(self):
        # Fresh heartbeat + incompatible intent/state = divergence.
        self.assertTrue(_DeriveDivergence('Online', 'Paused', 10, 300))
        self.assertTrue(_DeriveDivergence('Online', 'Draining', 10, 300))
        self.assertTrue(_DeriveDivergence('Paused', 'Encoding', 10, 300))
        self.assertTrue(_DeriveDivergence('Paused', 'Idle', 10, 300))
        self.assertTrue(_DeriveDivergence('Online', 'Faulted:mountfail', 10, 300))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_stale_heartbeat_is_offline_not_diverge(self):
        # Stale heartbeat = offline (gray dot). Never diverge regardless of intent/state pair.
        self.assertFalse(_DeriveDivergence('Online', 'Idle', 400, 300))
        self.assertFalse(_DeriveDivergence('Online', 'Paused', 400, 300))
        self.assertFalse(_DeriveDivergence('Paused', 'Encoding', 400, 300))
        self.assertFalse(_DeriveDivergence('Online', None, 400, 300))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_null_heartbeat_is_not_diverge(self):
        # Never-heartbeated worker (no signal at all) is not diverge either.
        self.assertFalse(_DeriveDivergence('Online', 'Idle', None, 300))
        self.assertFalse(_DeriveDivergence('Online', 'Paused', None, 300))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_fresh_no_truth_is_not_diverge(self):
        # Fresh heartbeat but worker has not yet reported RuntimeState = not diverge.
        self.assertFalse(_DeriveDivergence('Online', None, 10, 300))
        self.assertFalse(_DeriveDivergence('Online', '', 10, 300))

    # directive: worker-runtime-state | # see admin-workers.C6
    def test_empty_status_returns_false(self):
        self.assertFalse(_DeriveDivergence('', 'Idle', 10, 300))
        self.assertFalse(_DeriveDivergence(None, 'Idle', 10, 300))


if __name__ == '__main__':
    unittest.main()
