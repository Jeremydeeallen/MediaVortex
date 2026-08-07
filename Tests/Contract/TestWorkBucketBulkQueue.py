# directive: work-bucket-bulk-queue | # see work-bucket.C11
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService


def _Bucket(Name='Transcode', Mode='Transcode'):
    return BucketKey(
        UrlKey=Name, BucketName=Name, ProcessingMode=Mode,
        Title=Name, Subtitle='', Icon='fas fa-film', AllowsBulkQueue=True,
    )


class TestWorkBucketBulkQueue(unittest.TestCase):
    """C1-C4: bulk-queue endpoint + AdmitBulk tally + idempotence."""

    def test_bulkqueue_route_registered_on_blueprint(self):
        from flask import Flask
        from Features.WorkBucket.WorkBucketController import WorkBucketController
        App = Flask(__name__)
        App.register_blueprint(WorkBucketController().Blueprint)
        Rules = [(str(R), sorted(R.methods)) for R in App.url_map.iter_rules() if 'BulkQueue' in str(R)]
        self.assertTrue(len(Rules) > 0, 'BulkQueue route not registered')
        (RulePath, Methods) = Rules[0]
        self.assertIn('/api/Work/', RulePath)
        self.assertIn('BulkQueue', RulePath)
        self.assertIn('POST', Methods)

    def test_admit_bulk_tally_sums_to_total(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = [{'id': 1}, {'id': 2}, {'id': 3}, {'id': 4}, {'id': 5}]
        Svc = QueueAdmissionAppService(Db=Db)
        Bucket = _Bucket()
        StatusByFile = {
            1: {'Success': True, 'ItemId': 100},
            2: {'AlreadyQueued': True, 'ItemId': 101},
            3: {'Skipped': True, 'Message': 'quality ok'},
            4: {'AdmissionDeferred': True, 'Message': 'ungainable'},
            5: {'Success': False, 'Message': 'boom'},
        }
        import Features.TranscodeQueue.QueueManagementBusinessService as QmbsMod
        Real = QmbsMod.QueueManagementBusinessService
        try:
            class _StubQmbs:
                def AddJobToQueue(self, MediaFileId, ProcessingMode, ForceAdd, QualityTier=None):
                    return StatusByFile[MediaFileId]
            QmbsMod.QueueManagementBusinessService = _StubQmbs
            Result = Svc.AdmitBulk(Bucket, StorageRootId=1, QualityTier=2)
        finally:
            QmbsMod.QueueManagementBusinessService = Real
        self.assertEqual(Result.Total, 5)
        self.assertEqual(Result.Inserted, 1)
        self.assertEqual(Result.AlreadyQueued, 1)
        self.assertEqual(Result.Skipped, 1)
        self.assertEqual(Result.AdmissionDeferred, 1)
        self.assertEqual(Result.Errored, 1)
        self.assertEqual(
            Result.Inserted + Result.AlreadyQueued + Result.Skipped + Result.AdmissionDeferred + Result.Errored,
            Result.Total,
        )

    def test_admit_bulk_idempotence_second_call_all_already_queued(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = [{'id': 1}, {'id': 2}]
        Svc = QueueAdmissionAppService(Db=Db)
        Bucket = _Bucket()
        import Features.TranscodeQueue.QueueManagementBusinessService as QmbsMod
        Real = QmbsMod.QueueManagementBusinessService
        try:
            class _StubQmbs:
                def AddJobToQueue(self, MediaFileId, ProcessingMode, ForceAdd, QualityTier=None):
                    return {'AlreadyQueued': True, 'ItemId': MediaFileId + 100}
            QmbsMod.QueueManagementBusinessService = _StubQmbs
            Result = Svc.AdmitBulk(Bucket, StorageRootId=1, QualityTier=2)
        finally:
            QmbsMod.QueueManagementBusinessService = Real
        self.assertEqual(Result.Total, 2)
        self.assertEqual(Result.Inserted, 0)
        self.assertEqual(Result.AlreadyQueued, 2)

    def test_admit_bulk_query_filters_by_bucket_and_storage_root(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = []
        Svc = QueueAdmissionAppService(Db=Db)
        Bucket = _Bucket(Name='AudioFix', Mode='AudioFix')
        Svc.AdmitBulk(Bucket, StorageRootId=3, QualityTier=2)
        (Sql, Params) = Db.ExecuteQuery.call_args[0]
        self.assertIn('WorkBucket', Sql)
        self.assertIn('StorageRootId', Sql)
        self.assertEqual(Params, ('AudioFix', 3))


if __name__ == '__main__':
    unittest.main()
