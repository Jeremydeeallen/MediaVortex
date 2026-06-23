import unittest
import time

from Core.Database.DatabaseService import DatabaseService


# directive: activity-admin-and-worker-telemetry
class TestWorkerSelfReportResilience(unittest.TestCase):

    # directive: activity-admin-and-worker-telemetry
    def test_at_least_one_worker_heartbeat_advances_in_window(self):
        Db = DatabaseService()
        Pre = Db.ExecuteQuery(
            "SELECT WorkerName, LastHeartbeat FROM Workers "
            "WHERE Enabled = TRUE AND Status IN ('Online','Paused') "
            "AND LastHeartbeat IS NOT NULL ORDER BY WorkerName"
        )
        if not Pre:
            self.skipTest("No live workers to observe; resilience test requires at least one Online/Paused worker")
            return
        PreMap = {R['workername']: R['lastheartbeat'] for R in Pre}
        time.sleep(45)
        Post = Db.ExecuteQuery(
            "SELECT WorkerName, LastHeartbeat FROM Workers "
            "WHERE WorkerName = ANY(%s)",
            (list(PreMap.keys()),),
        )
        PostMap = {R['workername']: R['lastheartbeat'] for R in Post}
        Advanced = [N for N in PreMap if PostMap.get(N) and PostMap[N] > PreMap[N]]
        self.assertGreater(
            len(Advanced), 0,
            "No worker advanced its LastHeartbeat in a 45s window. "
            "Worker self-report telemetry is the contract -- heartbeats must continue independent of WebService."
        )


if __name__ == '__main__':
    unittest.main()
