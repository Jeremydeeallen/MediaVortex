import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService

TierOne = 'AV1 Tier 1 Efficient'


# directive: profile-row-lookup | # see profile-tier-ladder.C10
class _FakeDb:
    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def __init__(self, Rows):
        self.Rows = Rows

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def ExecuteQuery(self, Query, Parameters=()):
        for Needle, Result in self.Rows:
            if Needle in Query:
                return Result
        raise AssertionError(f'unexpected query: {Query}')


# directive: profile-row-lookup | # see profile-tier-ladder.C10
class TestContentClassSchema(unittest.TestCase):

    # directive: profile-row-lookup | # see profile-tier-ladder.S4
    def test_both_class_columns_exist_with_check(self):
        Db = DatabaseService()
        for Table, Column in (('storageroots', 'defaultcontentclass'), ('genrequalitytiers', 'contentclass')):
            Cols = Db.ExecuteQuery(
                "SELECT is_nullable FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                (Table, Column))
            self.assertEqual(len(Cols), 1, f'{Table}.{Column} missing')
            self.assertEqual(Cols[0]['is_nullable'], 'YES')
            Checks = Db.ExecuteQuery(
                "SELECT pg_get_constraintdef(c.oid) AS Def FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE t.relname = %s AND c.contype = 'c' AND pg_get_constraintdef(c.oid) ILIKE %s",
                (Table, f'%{Column}%'))
            self.assertEqual(len(Checks), 1, f'{Table}.{Column} has no CHECK')
            self.assertIn("'live_action'", Checks[0]['Def'])
            self.assertIn("'animation'", Checks[0]['Def'])


# directive: profile-row-lookup | # see profile-tier-ladder.C10
class TestContentClassResolver(unittest.TestCase):

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def _Resolve(self, LibraryDefault, Genres, GenreClasses):
        from Features.Profiles.ContentClassResolver import ContentClassResolver
        Db = _FakeDb([
            ('FROM StorageRoots', [{'DefaultContentClass': LibraryDefault}]),
            ('FROM MediaFiles', [{'Genres': Genres}]),
            ('FROM GenreQualityTiers', [{'Genre': G, 'ContentClass': C} for G, C in GenreClasses.items()]),
        ])
        return ContentClassResolver(Db).Resolve(1, 42)

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def test_first_genre_with_a_class_wins(self):
        self.assertEqual(self._Resolve('live_action', 'Comedy,Animation,Family', {'Animation': 'animation'}), 'animation')

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def test_library_default_when_no_genre_has_a_class(self):
        self.assertEqual(self._Resolve('live_action', 'Comedy,Drama', {}), 'live_action')
        self.assertEqual(self._Resolve('live_action', None, {}), 'live_action')

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def test_none_when_nothing_is_configured(self):
        self.assertIsNone(self._Resolve(None, None, {}))


# directive: profile-row-lookup | # see profile-tier-ladder.C9
class TestGetProfileRow(unittest.TestCase):

    # directive: profile-row-lookup | # see profile-tier-ladder.S5
    def test_row_is_chosen_by_profile_class_and_resolution(self):
        from Features.Profiles.TierLadderRepository import TierLadderRepository
        Repo = TierLadderRepository(DatabaseService())
        Live = Repo.GetProfileRow(TierOne, 'live_action', '1080p')
        Anim = Repo.GetProfileRow(TierOne, 'animation', '1080p')
        self.assertEqual(Live.TranscodeDownTo, '720p')
        self.assertEqual(Anim.TranscodeDownTo, '1080p')
        self.assertEqual(Live.ProfileName, TierOne)
        self.assertEqual(Live.Codec, 'av1')
        self.assertIsNone(Repo.GetProfileRow(TierOne, 'live_action', '4320p'))

    # directive: profile-row-lookup | # see profile-tier-ladder.S5
    def test_encode_row_is_the_row_at_the_target_resolution(self):
        from Features.Profiles.TierLadderRepository import TierLadderRepository
        Repo = TierLadderRepository(DatabaseService())
        Encode = Repo.GetEncodeRow(TierOne, 'live_action', '1920x1080')
        self.assertEqual(Encode.Resolution, '720p')
        self.assertEqual(Encode.TargetKbps, 1000)
        self.assertEqual(Repo.GetProfileTarget(TierOne, 'live_action', '1080p'), 1000)
        self.assertEqual(Repo.GetEncodeRow(TierOne, 'animation', '1080p').Resolution, '1080p')

    # directive: profile-row-lookup | # see profile-tier-ladder.C9 -- admission, command, estimate and compliance read one row
    def test_four_consumers_agree_on_the_row(self):
        from Core.Models.MediaFileModel import MediaFileModel
        from Features.Profiles.EncoderKnobRepository import EncoderKnobRepository
        from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        from Features.VideoEncoding.VideoVertical import VideoVertical
        Mf = MediaFileModel(StorageRootId=1, AssignedProfile=TierOne, Resolution='1920x1080', ResolutionCategory='1080p',
                            Codec='hevc', VideoBitrateKbps=6000, SizeMB=3000, DurationMinutes=45)
        Knobs = EncoderKnobRepository().GetEncoderKnobsForProfile(TierOne, 'live_action', '1920x1080')
        self.assertEqual((Knobs.TargetResolution, Knobs.TargetKbps), ('720p', 1000))
        Effective = EffectiveProfileResolver().Resolve(Mf)
        self.assertEqual((Effective.TargetResolutionCategory.Name, Effective.TargetVideoKbps), ('T720p', 1000))
        Blocked, Reason = QueueManagementBusinessService().EvaluateQueueAdmissionForProfile(Mf, TierOne)
        self.assertFalse(Reason.startswith('Upscale'), Reason)
        Compliant, Why = VideoVertical().Evaluate(Mf)
        self.assertIn('class=live_action', Why)
        self.assertIn(':1000*', Why)

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def test_missing_class_is_reported_not_substituted(self):
        from Core.Models.MediaFileModel import MediaFileModel
        from Features.VideoEncoding.VideoVertical import VideoVertical
        from unittest.mock import Mock
        Mf = MediaFileModel(StorageRootId=1, AssignedProfile=TierOne, ResolutionCategory='1080p', VideoBitrateKbps=6000)
        Vert = VideoVertical(Db=Mock(), RepoMgr=Mock(), Thresholds=Mock(), Tiers=Mock(),
                             FileTiers=Mock(**{'Resolve.return_value': None}), Classes=Mock(**{'Resolve.return_value': None}))
        self.assertEqual(Vert.Evaluate(Mf), (None, 'missing_input:ContentClass'))

    # directive: profile-row-lookup | # see profile-tier-ladder.C9
    def test_duplicate_lookups_are_gone(self):
        Files = subprocess.run(['git', 'ls-files', '*.py'], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
        Names = re.compile(r'GetProfileMaxTarget|GetProfileSettingsForTargetResolution|GetProfileQualityForTargetResolution|_ResolveTargetResolution')
        Hits = []
        for Rel in Files:
            if Rel.endswith('TestProfileRowLookup.py'):
                continue
            Text = (REPO_ROOT / Rel).read_text(encoding='utf-8', errors='replace')
            Hits += [f'{Rel}:{N}' for N, Line in enumerate(Text.splitlines(), 1) if Names.search(Line)]
        self.assertEqual(Hits, [])
        for Rel in ('Features/Profiles/EffectiveProfileResolver.py', 'Features/Profiles/EncoderKnobRepository.py'):
            self.assertNotIn('FROM ProfileThresholds', (REPO_ROOT / Rel).read_text(encoding='utf-8'), Rel)


if __name__ == '__main__':
    unittest.main()
