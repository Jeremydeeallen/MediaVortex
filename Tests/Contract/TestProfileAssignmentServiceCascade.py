# directive: tv-tier1-classifier-pin
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.MediaFiles.ProfileAssignmentService import ProfileAssignmentService


class TestProfileAssignmentServiceCascade(unittest.TestCase):

    def test_assign_writes_then_cascades_on_written_ids(self):
        Repo = MagicMock()
        Repo.WriteAssignedProfile.return_value = [10, 20]
        with patch('Features.MediaFiles.ProfileAssignmentService.MediaFilesRepository', return_value=Repo), \
             patch('Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService') as QmbsCls:
            QmbsInstance = QmbsCls.return_value
            QmbsInstance.RecomputeForFiles = MagicMock()
            Svc = ProfileAssignmentService(Repo=Repo)
            Result = Svc.Assign([10, 20, 30], 'AV1 Tier 1 Efficient', 'test_source', IfUnsetOnly=True)
            self.assertEqual(Result, [10, 20])
            Repo.WriteAssignedProfile.assert_called_once_with([10, 20, 30], 'AV1 Tier 1 Efficient', 'test_source', IfUnsetOnly=True)
            QmbsInstance.RecomputeForFiles.assert_called_once_with([10, 20])

    def test_assign_skips_cascade_when_repo_wrote_zero(self):
        Repo = MagicMock()
        Repo.WriteAssignedProfile.return_value = []
        with patch('Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService') as QmbsCls:
            QmbsInstance = QmbsCls.return_value
            QmbsInstance.RecomputeForFiles = MagicMock()
            Svc = ProfileAssignmentService(Repo=Repo)
            Result = Svc.Assign([99], 'AV1 Tier 2 Good', 'series', IfUnsetOnly=True)
            self.assertEqual(Result, [])
            QmbsInstance.RecomputeForFiles.assert_not_called()

    def test_assign_empty_input_returns_empty_no_calls(self):
        Repo = MagicMock()
        Repo.WriteAssignedProfile.return_value = []
        with patch('Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService') as QmbsCls:
            QmbsInstance = QmbsCls.return_value
            QmbsInstance.RecomputeForFiles = MagicMock()
            Svc = ProfileAssignmentService(Repo=Repo)
            self.assertEqual(Svc.Assign([], 'X', 'y'), [])
            QmbsInstance.RecomputeForFiles.assert_not_called()


if __name__ == '__main__':
    unittest.main()
