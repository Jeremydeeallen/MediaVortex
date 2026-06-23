import unittest
from datetime import datetime

from WorkerService.WorkerStateReporter import WorkerStateReporter


# directive: worker-runtime-state | # see admin-workers.C11
class _CapturingDb:

    # directive: worker-runtime-state | # see admin-workers.C11
    def __init__(self):
        self.Calls = []

    # directive: worker-runtime-state | # see admin-workers.C11
    def ExecuteNonQuery(self, Sql, Params=None):
        self.Calls.append((Sql, Params))


# directive: worker-runtime-state | # see admin-workers.C11
class TestFaultedStateOnCrashRecovery(unittest.TestCase):

    # directive: worker-runtime-state | # see admin-workers.C11
    def test_transition_writes_faulted_state_with_reason(self):
        Db = _CapturingDb()
        Reporter = WorkerStateReporter(Db, 'I9-2024', Clock=lambda: datetime(2026, 6, 23, 12, 0, 0))
        Reporter.Transition('Faulted:RuntimeError')
        self.assertEqual(len(Db.Calls), 1)
        Sql, Params = Db.Calls[0]
        self.assertIn('UPDATE Workers SET RuntimeState', Sql)
        self.assertEqual(Params[0], 'Faulted:RuntimeError')
        self.assertIsNone(Params[1])

    # directive: worker-runtime-state | # see admin-workers.C11
    def test_subsequent_initializing_transition_clears_faulted(self):
        Db = _CapturingDb()
        Reporter = WorkerStateReporter(Db, 'I9-2024', Clock=lambda: datetime(2026, 6, 23, 12, 0, 0))
        Reporter.Transition('Faulted:RuntimeError')
        Reporter.Transition('Initializing')
        self.assertEqual(len(Db.Calls), 2)
        _Sql, Params = Db.Calls[1]
        self.assertEqual(Params[0], 'Initializing')


if __name__ == '__main__':
    unittest.main()
