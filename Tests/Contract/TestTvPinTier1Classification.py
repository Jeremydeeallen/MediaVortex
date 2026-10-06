# directive: tv-video-rule-tier1 | # see classifier.C9
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.ContentClassifier.ContentClassifierService import ContentClassifierService


# directive: tv-video-rule-tier1 | # see classifier.C9
class TestTvPinTier1Classification(unittest.TestCase):

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def _TieredLibraryId(self):
        Rows = DatabaseService().ExecuteQuery("SELECT Id FROM StorageRoots WHERE DefaultQualityTier = 1 ORDER BY Id LIMIT 1")
        self.assertTrue(Rows, 'no library has DefaultQualityTier = 1')
        return int(Rows[0].get('Id'))

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def _Service(self, Media):
        Writer = Mock()
        Svc = ContentClassifierService(ProfileWriter=Writer)
        Svc.Repository = Mock(**{
            'GetMediaFileForClassification.return_value': Media,
            'GetActiveRules.side_effect': AssertionError('rules must not be walked for a library with a default tier'),
        })
        return Svc, Writer

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def test_unprofiled_av1_file_in_tiered_library_gets_tier_profile(self):
        Svc, Writer = self._Service({'Id': 5, 'StorageRootId': self._TieredLibraryId(), 'AssignedProfile': None,
                                     'Codec': 'av1', 'VideoBitrateKbps': 5967, 'ResolutionCategory': '1080p'})
        self.assertEqual(Svc.ClassifyAndAssign(5), 'AV1 Tier 1 Efficient')
        Writer.Assign.assert_called_once_with([5], 'AV1 Tier 1 Efficient', 'library_default_tier', IfUnsetOnly=True)

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def test_existing_profile_is_left_alone(self):
        Svc, Writer = self._Service({'Id': 5, 'StorageRootId': self._TieredLibraryId(), 'AssignedProfile': 'AV1 Tier 2 Good'})
        self.assertEqual(Svc.ClassifyAndAssign(5), 'AV1 Tier 2 Good')
        Writer.Assign.assert_not_called()

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def test_no_rule_names_a_tiered_library_path(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS N FROM ContentClassificationRules r "
            "JOIN StorageRoots sr ON sr.DefaultQualityTier IS NOT NULL "
            " AND starts_with(r.FolderPathPattern, sr.CanonicalPrefix)"
        )
        self.assertEqual(int(Rows[0].get('N')), 0)

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def test_no_unprofiled_probed_file_in_tiered_library(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS N FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
            "WHERE sr.DefaultQualityTier IS NOT NULL AND mf.AssignedProfile IS NULL AND mf.ResolutionCategory IS NOT NULL"
        )
        self.assertEqual(int(Rows[0].get('N')), 0)


if __name__ == '__main__':
    unittest.main()
