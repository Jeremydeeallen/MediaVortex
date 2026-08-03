import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ContentClassifier.ContentClassifierService import ContentClassifierService


class TestClassifierCascade(unittest.TestCase):

    def _RunClassify(self, MediaFileId, MediaRow, MatchedRule):
        Svc = ContentClassifierService()
        Svc.Repository = MagicMock()
        Svc.Repository.GetMediaFileForClassification.return_value = MediaRow
        Svc.Repository.GetActiveRules.return_value = [MatchedRule]
        Svc.Repository.WriteAssignment = MagicMock()
        with patch('Features.ContentClassifier.ContentClassifierService._RuleMatches', return_value=True), \
             patch('Features.ContentClassifier.ContentClassifierService.QueueManagementBusinessService') as QmbsCls:
            QmbsInstance = QmbsCls.return_value
            QmbsInstance.RecomputeForFiles = MagicMock()
            Svc.ClassifyAndAssign(MediaFileId)
            return Svc.Repository.WriteAssignment, QmbsInstance.RecomputeForFiles

    def test_classifier_cascade_fires_on_match(self):
        Media = {'Id': 999, 'AssignedProfile': None, 'Codec': 'h264', 'VideoBitrateKbps': 4000, 'ResolutionCategory': '1080p'}
        Rule = MagicMock(RuleName='rule1', AssignProfileName='AV1 Tier 3 Better')
        WriteAssignment, RecomputeForFiles = self._RunClassify(999, Media, Rule)
        WriteAssignment.assert_called_once_with(999, 'AV1 Tier 3 Better', 'classifier')
        RecomputeForFiles.assert_called_once_with([999])

    def test_classifier_cascade_fires_on_skip_sentinel(self):
        Media = {'Id': 42, 'AssignedProfile': None, 'Codec': 'av1'}
        Rule = MagicMock(RuleName='av1_skip', AssignProfileName='__skip__')
        WriteAssignment, RecomputeForFiles = self._RunClassify(42, Media, Rule)
        WriteAssignment.assert_called_once_with(42, None, 'classifier_skip_av1')
        RecomputeForFiles.assert_called_once_with([42])

    def test_classifier_no_cascade_when_sticky_guard_skips(self):
        Svc = ContentClassifierService()
        Svc.Repository = MagicMock()
        Svc.Repository.GetMediaFileForClassification.return_value = {'Id': 1, 'AssignedProfile': 'Already Set'}
        Svc.Repository.WriteAssignment = MagicMock()
        with patch('Features.ContentClassifier.ContentClassifierService.QueueManagementBusinessService') as QmbsCls:
            QmbsInstance = QmbsCls.return_value
            QmbsInstance.RecomputeForFiles = MagicMock()
            Result = Svc.ClassifyAndAssign(1)
            self.assertEqual(Result, 'Already Set')
            Svc.Repository.WriteAssignment.assert_not_called()
            QmbsInstance.RecomputeForFiles.assert_not_called()


if __name__ == '__main__':
    unittest.main()
