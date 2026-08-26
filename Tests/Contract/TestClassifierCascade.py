# directive: tv-tier1-classifier-pin
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
        Svc.ProfileWriter = MagicMock()
        Svc.ProfileWriter.Assign.return_value = [MediaFileId]
        with patch('Features.ContentClassifier.ContentClassifierService._RuleMatches', return_value=True):
            Svc.ClassifyAndAssign(MediaFileId)
        return Svc.ProfileWriter.Assign

    def test_classifier_routes_through_profile_writer_on_match(self):
        Media = {'Id': 999, 'AssignedProfile': None, 'Codec': 'h264', 'VideoBitrateKbps': 4000, 'ResolutionCategory': '1080p'}
        Rule = MagicMock(RuleName='rule1', AssignProfileName='AV1 Tier 3 Better')
        Assign = self._RunClassify(999, Media, Rule)
        Assign.assert_called_once_with([999], 'AV1 Tier 3 Better', 'classifier', IfUnsetOnly=True)

    def test_classifier_routes_through_profile_writer_on_skip_sentinel(self):
        Media = {'Id': 42, 'AssignedProfile': None, 'Codec': 'av1'}
        Rule = MagicMock(RuleName='av1_skip', AssignProfileName='__skip__')
        Assign = self._RunClassify(42, Media, Rule)
        Assign.assert_called_once_with([42], None, 'classifier_skip_av1', IfUnsetOnly=True)

    def test_classifier_skips_writer_when_profile_already_set(self):
        Svc = ContentClassifierService()
        Svc.Repository = MagicMock()
        Svc.Repository.GetMediaFileForClassification.return_value = {'Id': 1, 'AssignedProfile': 'Already Set'}
        Svc.ProfileWriter = MagicMock()
        Result = Svc.ClassifyAndAssign(1)
        self.assertEqual(Result, 'Already Set')
        Svc.ProfileWriter.Assign.assert_not_called()


if __name__ == '__main__':
    unittest.main()
