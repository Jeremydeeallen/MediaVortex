# directive: transcode-flow-canonical
import unittest

from Core.Database.DatabaseService import DatabaseService
from Features.ServiceControl.AttemptAbandonmentSweeper import AttemptAbandonmentSweeper


SENTINEL_FILE_STALE = '_test-sweeper-stale.mkv'
SENTINEL_FILE_ALIVE = '_test-sweeper-alive.mkv'
SENTINEL_FILE_INVARIANT = '_test-inflight-guard.mkv'
SENTINEL_OWNER_STALE = '_test-sweeper-owner-stale'
SENTINEL_OWNER_ALIVE = '_test-sweeper-owner-alive'


# directive: transcode-flow-canonical
class TestAbandonmentSweeper(unittest.TestCase):
    """Live-DB contract: cross-worker terminal write path is bounded to heartbeat-stale + Offline owners; idempotent; only-stale-owner scope."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls._Reset()
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, Enabled, AcceptsInterlaced, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Offline', TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, NOW() - INTERVAL '10 minutes'), "
            "       (%s, 'linux', 'Online',  TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, NOW())",
            (SENTINEL_OWNER_STALE, SENTINEL_OWNER_ALIVE),
        )
        cls.Db.ExecuteNonQuery("INSERT INTO MediaFiles (FileName) VALUES (%s), (%s)", (SENTINEL_FILE_STALE, SENTINEL_FILE_ALIVE))
        Rows = cls.Db.ExecuteQuery("SELECT FileName, Id FROM MediaFiles WHERE FileName IN (%s, %s)", (SENTINEL_FILE_STALE, SENTINEL_FILE_ALIVE))
        Ids = {R['FileName']: R['Id'] for R in Rows}
        cls.MfidStale = Ids[SENTINEL_FILE_STALE]
        cls.MfidAlive = Ids[SENTINEL_FILE_ALIVE]

    @classmethod
    def tearDownClass(cls):
        cls._Reset()

    @classmethod
    def _Reset(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId IN (SELECT Id FROM MediaFiles WHERE FileName IN (%s, %s, %s))", (SENTINEL_FILE_STALE, SENTINEL_FILE_ALIVE, SENTINEL_FILE_INVARIANT))
        cls.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE FileName IN (%s, %s, %s)", (SENTINEL_FILE_STALE, SENTINEL_FILE_ALIVE, SENTINEL_FILE_INVARIANT))
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName IN (%s, %s)", (SENTINEL_OWNER_STALE, SENTINEL_OWNER_ALIVE))

    def setUp(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId IN (%s, %s)", (self.MfidStale, self.MfidAlive))
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, AttemptDate, Success, ProfileName, StorageRootId, RelativePath) "
            "VALUES (%s, %s, NOW(), NULL, 'test-profile', 1, 'test/sweeper-stale.mkv'), "
            "       (%s, %s, NOW(), NULL, 'test-profile', 1, 'test/sweeper-alive.mkv')",
            (self.MfidStale, SENTINEL_OWNER_STALE, self.MfidAlive, SENTINEL_OWNER_ALIVE),
        )

    def test_only_stale_and_offline_owner_attempts_released(self):
        Result = AttemptAbandonmentSweeper(self.Db).SweepStaleOwners(AbandonmentMinutes=5)
        self.assertGreaterEqual(int(Result['AbandonedCount']), 1)
        StaleRow = self.Db.ExecuteQuery("SELECT Success, ErrorMessage FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MfidStale,))[0]
        AliveRow = self.Db.ExecuteQuery("SELECT Success, ErrorMessage FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MfidAlive,))[0]
        self.assertEqual(bool(StaleRow.get('Success')), False)
        self.assertEqual((StaleRow.get('ErrorMessage') or '').strip(), 'owner_abandoned')
        self.assertIsNone(AliveRow.get('Success'))

    def test_idempotent_second_sweep_no_op_for_already_abandoned(self):
        AttemptAbandonmentSweeper(self.Db).SweepStaleOwners(AbandonmentMinutes=5)
        Second = AttemptAbandonmentSweeper(self.Db).SweepStaleOwners(AbandonmentMinutes=5)
        self.assertEqual(int(Second['AbandonedCount']), 0)

    def test_online_owner_never_swept_even_when_heartbeat_stale(self):
        self.Db.ExecuteNonQuery("UPDATE Workers SET Status = 'Online', LastHeartbeat = NOW() - INTERVAL '10 minutes' WHERE WorkerName = %s", (SENTINEL_OWNER_STALE,))
        try:
            AttemptAbandonmentSweeper(self.Db).SweepStaleOwners(AbandonmentMinutes=5)
            StaleRow = self.Db.ExecuteQuery("SELECT Success FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MfidStale,))[0]
            self.assertIsNone(StaleRow.get('Success'))
        finally:
            self.Db.ExecuteNonQuery("UPDATE Workers SET Status = 'Offline', LastHeartbeat = NOW() - INTERVAL '10 minutes' WHERE WorkerName = %s", (SENTINEL_OWNER_STALE,))


# directive: transcode-flow-canonical
class TestSingleInflightInvariant(unittest.TestCase):
    """Live-DB contract: partial UNIQUE index refuses a second Success-NULL attempt on the same MediaFileId."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId IN (SELECT Id FROM MediaFiles WHERE FileName = %s)", (SENTINEL_FILE_INVARIANT,))
        cls.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE FileName = %s", (SENTINEL_FILE_INVARIANT,))
        cls.Db.ExecuteNonQuery("INSERT INTO MediaFiles (FileName) VALUES (%s)", (SENTINEL_FILE_INVARIANT,))
        Row = cls.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE FileName = %s", (SENTINEL_FILE_INVARIANT,))[0]
        cls.Mfid = Row['Id']

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (cls.Mfid,))
        cls.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (cls.Mfid,))

    def setUp(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (self.Mfid,))
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, AttemptDate, Success, ProfileName, StorageRootId, RelativePath) "
            "VALUES (%s, %s, NOW(), NULL, 'test-profile', 1, 'test/inflight-guard.mkv')",
            (self.Mfid, '_test-owner-A'),
        )

    def test_second_inflight_attempt_refused_by_db(self):
        import psycopg2
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            self.Db.ExecuteNonQuery(
                "INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, AttemptDate, Success, ProfileName, StorageRootId, RelativePath) "
                "VALUES (%s, %s, NOW(), NULL, 'test-profile', 1, 'test/inflight-guard.mkv')",
                (self.Mfid, '_test-owner-B'),
            )

    def test_terminal_attempt_frees_the_slot(self):
        self.Db.ExecuteNonQuery("UPDATE TranscodeAttempts SET Success = TRUE WHERE MediaFileId = %s", (self.Mfid,))
        Affected = self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, AttemptDate, Success, ProfileName, StorageRootId, RelativePath) "
            "VALUES (%s, %s, NOW(), NULL, 'test-profile', 1, 'test/inflight-guard.mkv')",
            (self.Mfid, '_test-owner-B'),
        )
        self.assertGreaterEqual(int(Affected or 0), 1)


if __name__ == '__main__':
    unittest.main()
