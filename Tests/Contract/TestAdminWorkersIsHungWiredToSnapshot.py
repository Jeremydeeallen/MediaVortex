import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Core.Database.DatabaseService import DatabaseService
from Features.Admin.Workers.AdminWorkersRepository import AdminWorkersRepository


# directive: worker-runtime-state
class TestAdminWorkersIsHungWiredToSnapshot(unittest.TestCase):

    def setUp(self):
        self.Db = DatabaseService()
        self.WorkerName = 'wakko-worker-1'
        self.SyntheticErrorMessage = 'synthetic-c10-test-regression'
        self.AttemptId = None

    def tearDown(self):
        if self.AttemptId is not None:
            self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE Id = %s", (self.AttemptId,))
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RuntimeState = NULL, CurrentAttemptId = NULL, LastRuntimeStateUpdate = NULL "
            "WHERE WorkerName = %s",
            (self.WorkerName,),
        )

    def test_IsHung_True_When_Worker_Encoding_With_Stale_Rs_Age(self):
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (AttemptDate, Success, ErrorMessage, WorkerName, ProfileName) "
            "VALUES (NOW(), NULL, %s, %s, 'TEST_C10_REGRESSION')",
            (self.SyntheticErrorMessage, self.WorkerName),
        )
        Row = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeAttempts WHERE ErrorMessage = %s ORDER BY Id DESC LIMIT 1",
            (self.SyntheticErrorMessage,),
        )
        self.AttemptId = int(Row[0]['id'])

        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RuntimeState = 'Encoding', CurrentAttemptId = %s, "
            "LastRuntimeStateUpdate = NOW() - INTERVAL '700 seconds' WHERE WorkerName = %s",
            (self.AttemptId, self.WorkerName),
        )

        Tiles = AdminWorkersRepository().GetTiles()
        Match = [T for T in Tiles if T.get('WorkerName') == self.WorkerName]
        self.assertEqual(len(Match), 1, f"Expected one tile for {self.WorkerName}")
        Tile = Match[0]
        self.assertEqual(Tile.get('RuntimeState'), 'Encoding')
        self.assertGreater(Tile.get('RuntimeStateAgeSec') or 0, 600)
        self.assertTrue(Tile.get('IsHung'), f"IsHung must be True when RuntimeState=Encoding and rs_age>threshold; tile={dict(Tile)}")


if __name__ == '__main__':
    unittest.main()
