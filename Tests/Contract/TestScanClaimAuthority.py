# directive: transcode-flow-canonical
import unittest
import uuid

from Core.Database.DatabaseService import DatabaseService


SENTINEL_ROOTFOLDER_REL = '_test-scan-claim-root'
SENTINEL_STORAGE_ROOT_ID = 1


# directive: transcode-flow-canonical
class TestScanJobsOneActivePerRoot(unittest.TestCase):
    """Live-DB contract: partial UNIQUE index refuses a second Pending/Running ScanJobs row on the same (StorageRootId, RelativePath)."""

    @classmethod
    def setUpClass(cls):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Reset()
        WorkerContext.Initialize(WorkerName='I9-2024', Platform='windows')
        cls.Db = DatabaseService()
        cls._Reset()

    @classmethod
    def tearDownClass(cls):
        cls._Reset()

    @classmethod
    def _Reset(cls):
        cls.Db.ExecuteNonQuery(
            "DELETE FROM ScanJobs WHERE StorageRootId = %s AND RelativePath = %s",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_ROOTFOLDER_REL),
        )

    def setUp(self):
        self._Reset()
        self.FirstJobId = str(uuid.uuid4())
        self.Db.ExecuteNonQuery(
            "INSERT INTO ScanJobs (JobId, StorageRootId, RelativePath, Recursive, Status, StartTime, LastUpdated, ScanType, WorkerName) "
            "VALUES (%s, %s, %s, TRUE, 'Running', NOW(), NOW(), 'File', %s)",
            (self.FirstJobId, SENTINEL_STORAGE_ROOT_ID, SENTINEL_ROOTFOLDER_REL, '_test-owner-A'),
        )

    def test_second_active_scan_refused_by_db(self):
        import psycopg2
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            self.Db.ExecuteNonQuery(
                "INSERT INTO ScanJobs (JobId, StorageRootId, RelativePath, Recursive, Status, StartTime, LastUpdated, ScanType, WorkerName) "
                "VALUES (%s, %s, %s, TRUE, 'Running', NOW(), NOW(), 'File', %s)",
                (str(uuid.uuid4()), SENTINEL_STORAGE_ROOT_ID, SENTINEL_ROOTFOLDER_REL, '_test-owner-B'),
            )

    def test_terminal_scan_frees_the_slot(self):
        self.Db.ExecuteNonQuery("UPDATE ScanJobs SET Status = 'Completed', EndTime = NOW() WHERE JobId = %s", (self.FirstJobId,))
        Affected = self.Db.ExecuteNonQuery(
            "INSERT INTO ScanJobs (JobId, StorageRootId, RelativePath, Recursive, Status, StartTime, LastUpdated, ScanType, WorkerName) "
            "VALUES (%s, %s, %s, TRUE, 'Running', NOW(), NOW(), 'File', %s)",
            (str(uuid.uuid4()), SENTINEL_STORAGE_ROOT_ID, SENTINEL_ROOTFOLDER_REL, '_test-owner-B'),
        )
        self.assertGreaterEqual(int(Affected or 0), 1)

    def test_create_scan_job_returns_true_on_win_false_on_race(self):
        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
        self.Db.ExecuteNonQuery("UPDATE ScanJobs SET Status = 'Completed', EndTime = NOW() WHERE JobId = %s", (self.FirstJobId,))
        Business = FileScanningBusinessService()
        JobA = str(uuid.uuid4())
        JobB = str(uuid.uuid4())
        # Real T:\ canonical form so Path.FromLegacyString resolves to StorageRootId=1
        RootDisplay = f"T:\\{SENTINEL_ROOTFOLDER_REL}"
        WonA = Business.CreateScanJob(JobA, RootDisplay, True, WorkerName='_test-owner-A')
        WonB = Business.CreateScanJob(JobB, RootDisplay, True, WorkerName='_test-owner-B')
        Rows = self.Db.ExecuteQuery("SELECT StorageRootId, RelativePath FROM ScanJobs WHERE JobId = %s", (JobA,))
        self.assertTrue(WonA)
        # If Path.FromLegacyString parsed (Sid non-NULL), claim must refuse WonB. If it failed to parse both rows carry NULL StorageRootId and both win -- fail loud with the parse gap surfaced.
        self.assertIsNotNone(Rows[0].get('StorageRootId'), f"Test presupposes Path parse produces non-NULL StorageRootId; got NULL. RootDisplay={RootDisplay!r}")
        self.assertFalse(WonB)


if __name__ == '__main__':
    unittest.main()
