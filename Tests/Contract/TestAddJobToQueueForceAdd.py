import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService
from Features.WorkBucket.Domain.BucketKey import BucketKey


# See TranscodeQueue.feature.md C11 [BUG-0078]
class TestAddJobToQueueForceAddOverridesVmafGate(unittest.TestCase):
    """[BUG-0078] ForceAdd=True must bypass both the marginal-savings gate AND the RetranscodeDecider VMAF>=80 gate."""

    def _BuildService(self, ItemId: int = 999):
        Svc = QueueManagementBusinessService.__new__(QueueManagementBusinessService)
        Svc.DatabaseManager = MagicMock()
        FakeMediaFile = MagicMock()
        FakeMediaFile.Id = 42
        FakeMediaFile.FileName = 'ForceAdd.mkv'
        FakeMediaFile.FilePath = 'T:/Fake/ForceAdd.mkv'
        FakeMediaFile.AssignedProfile = 'FakeProfile'
        Svc.DatabaseManager.GetMediaFileById.return_value = FakeMediaFile
        Svc.DatabaseManager.DatabaseService.ExecuteQuery.return_value = []
        Svc.EvaluateQueueAdmissionForProfile = MagicMock(return_value=(False, None))
        FakeQueueItem = MagicMock()
        FakeQueueItem.Priority = 100
        Svc.CreateQueueItemFromMediaFileWithProfile = MagicMock(return_value=FakeQueueItem)
        Svc.Repository = MagicMock()
        Svc.Repository.SaveTranscodeQueueItem.return_value = ItemId
        Svc.ProfileRepository = MagicMock()
        return Svc, FakeMediaFile

    def test_force_add_true_over_vmaf_gte_80_inserts_row(self):
        Svc, _ = self._BuildService(ItemId=999)
        with patch('Features.QualityTesting.Disposition.RetranscodeDecider.RetranscodeDecider') as MockDecider, \
             patch('Features.TranscodeJob.Adjustments.AdjustmentRegistry.AdjustmentRegistry'), \
             patch('Features.AudioNormalization.AudioPolicyAdmissionGate.AudioPolicyAdmissionGate'):
            MockDecider.return_value.Decide.return_value = (False, {'VMAF': 87.44, 'Quality': 22})
            Result = Svc.AddJobToQueue(MediaFileId=42, ForceAdd=True)
        self.assertTrue(Result.get('Success'), Result)
        self.assertFalse(Result.get('Skipped', False), Result)
        self.assertEqual(Result.get('ItemId'), 999)
        Svc.Repository.SaveTranscodeQueueItem.assert_called_once()

    def test_force_add_false_over_vmaf_gte_80_returns_skipped(self):
        Svc, _ = self._BuildService()
        with patch('Features.QualityTesting.Disposition.RetranscodeDecider.RetranscodeDecider') as MockDecider, \
             patch('Features.TranscodeJob.Adjustments.AdjustmentRegistry.AdjustmentRegistry'):
            MockDecider.return_value.Decide.return_value = (False, {'VMAF': 87.44, 'Quality': 22})
            Result = Svc.AddJobToQueue(MediaFileId=42, ForceAdd=False)
        self.assertTrue(Result.get('Success'), Result)
        self.assertTrue(Result.get('Skipped'), Result)
        Svc.Repository.SaveTranscodeQueueItem.assert_not_called()


# See work-bucket.feature.md C5 -- AdmitOne status mapping for [BUG-0078]
class TestAdmitOneMapsSkippedResult(unittest.TestCase):
    """AdmitOne must map AddJobToQueue's Skipped=True result to Status='skipped', not 'queued'."""

    def _RunAdmitOne(self, AddJobResult):
        Svc = QueueAdmissionAppService.__new__(QueueAdmissionAppService)
        Svc.Db = MagicMock()
        with patch('Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService') as Qms:
            Qms.return_value.AddJobToQueue.return_value = AddJobResult
            return Svc.AdmitOne(MediaFileId=42, Bucket=BucketKey.FromUrlKey('Transcode'))

    def test_skipped_result_maps_to_status_skipped(self):
        Result = self._RunAdmitOne({'Success': True, 'Skipped': True, 'Message': 'Quality already acceptable, skipping retranscode'})
        self.assertEqual(Result.Status, 'skipped')
        self.assertEqual(Result.QueueId, 0)

    def test_success_with_item_id_maps_to_queued(self):
        Result = self._RunAdmitOne({'Success': True, 'ItemId': 777})
        self.assertEqual(Result.Status, 'queued')
        self.assertEqual(Result.QueueId, 777)

    def test_already_queued_maps_to_already_queued(self):
        Result = self._RunAdmitOne({'Success': True, 'AlreadyQueued': True, 'ItemId': 555})
        self.assertEqual(Result.Status, 'already_queued')
        self.assertEqual(Result.QueueId, 555)

    def test_error_result_maps_to_error(self):
        Result = self._RunAdmitOne({'Success': False, 'ErrorMessage': 'boom'})
        self.assertEqual(Result.Status, 'error')
        self.assertEqual(Result.QueueId, 0)


if __name__ == '__main__':
    unittest.main()
