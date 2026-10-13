# directive: movies-video-rule | # see video-encoding.C1
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Core.Database.DatabaseService import DatabaseService
from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
from Features.ContentClassifier.MovieGenreSyncService import MovieGenreSyncService
from Features.Profiles.FileTierResolver import FileTier, FileTierResolver
from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: movies-video-rule | # see video-encoding.C1
class _ResolverDb:

    # directive: movies-video-rule | # see video-encoding.C1
    def __init__(self, LibraryTier, GenreSource, Genres):
        self.Library = [{'DefaultQualityTier': LibraryTier, 'GenreSource': GenreSource}]
        self.File = [{'Genres': Genres}]

    # directive: movies-video-rule | # see video-encoding.C1
    def ExecuteQuery(self, Sql, Params=None):
        return self.Library if 'FROM StorageRoots' in Sql else self.File


# directive: movies-video-rule | # see video-encoding.C1
def _Resolve(LibraryTier=2, GenreSource='radarr', Genres='', GenreTiers=None):
    Repo = Mock(**{'GetTiers.return_value': GenreTiers or {}})
    return FileTierResolver(Db=_ResolverDb(LibraryTier, GenreSource, Genres), GenreTiers=Repo).Resolve(2, 10)


# directive: movies-video-rule | # see video-encoding.C1
class TestFileTierResolver(unittest.TestCase):

    # directive: movies-video-rule | # see video-encoding.C1
    def test_library_without_default_tier_has_no_file_tier(self):
        self.assertIsNone(_Resolve(LibraryTier=None))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_library_without_genre_source_uses_library_tier(self):
        self.assertEqual(_Resolve(LibraryTier=1, GenreSource=None, Genres=None), FileTier(1, ''))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_genres_not_fetched_is_undecided(self):
        self.assertEqual(_Resolve(Genres=None), FileTier(None, 'missing_input:Genres'))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_movie_with_no_genre_takes_library_default(self):
        self.assertEqual(_Resolve(Genres=''), FileTier(2, 'genre=none'))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_highest_genre_tier_wins(self):
        Resolved = _Resolve(Genres='Comedy,Action,Romance', GenreTiers={'Comedy': 1, 'Action': 3, 'Romance': 1})
        self.assertEqual(Resolved, FileTier(3, 'genre=Action'))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_genre_without_tier_counts_as_library_default(self):
        Resolved = _Resolve(Genres='Drama,Crime', GenreTiers={'Drama': 1, 'Crime': None})
        self.assertEqual(Resolved, FileTier(2, 'genre=Crime'))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_all_low_genres_give_low_tier(self):
        self.assertEqual(_Resolve(Genres='Romance,Comedy', GenreTiers={'Romance': 1, 'Comedy': 1}), FileTier(1, 'genre=Romance'))


# directive: movies-video-rule | # see video-encoding.C1
class TestMoviesVideoVerdict(unittest.TestCase):

    # directive: movies-video-rule | # see video-encoding.C1
    def _Vert(self, Resolved):
        self.Tiers = Mock(**{'GetTierEncodeKbps.return_value': 3000})
        return VideoVertical(
            Db=Mock(), RepoMgr=Mock(),
            Thresholds=Mock(**{'GetMultiplier.return_value': 2.0}),
            Tiers=self.Tiers,
            FileTiers=Mock(**{'Resolve.return_value': Resolved}),
        )

    # directive: movies-video-rule | # see video-encoding.C1
    def _Mf(self, Kbps, **Overrides):
        Fields = dict(Id=10, StorageRootId=2, Codec='h264', VideoBitrateKbps=Kbps, ResolutionCategory='1080p',
                      AssignedProfile='AV1 Tier 1 Efficient', ContainerFormat='mkv')
        Fields.update(Overrides)
        return SimpleNamespace(**Fields)

    # directive: movies-video-rule | # see video-encoding.C1
    def test_reason_names_tier_and_deciding_genre(self):
        Ok, Reason = self._Vert(FileTier(3, 'genre=Action')).Evaluate(self._Mf(6001))
        self.assertFalse(Ok)
        self.assertEqual(Reason, 'source_above_ceiling:6001>6000(tier=3:3000*2.0,genre=Action)')

    # directive: movies-video-rule | # see video-encoding.C1
    def test_at_ceiling_is_compliant(self):
        Ok, Reason = self._Vert(FileTier(2, 'genre=none')).Evaluate(self._Mf(6000))
        self.assertTrue(Ok)
        self.assertEqual(Reason, 'source_at_or_below_ceiling:6000<=6000(tier=2:3000*2.0,genre=none)')

    # directive: movies-video-rule | # see video-encoding.C1
    def test_genres_not_fetched_leaves_video_undecided(self):
        Ok, Reason = self._Vert(FileTier(None, 'missing_input:Genres')).Evaluate(self._Mf(9000))
        self.assertIsNone(Ok)
        self.assertEqual(Reason, 'missing_input:Genres')

    # directive: movies-video-rule | # see video-encoding.C1
    def test_profile_and_codec_play_no_part(self):
        Vert = self._Vert(FileTier(3, 'genre=Action'))
        Same = Vert.Evaluate(self._Mf(7000, Codec='av1', AssignedProfile='AV1 Tier 3 Better'))
        Other = Vert.Evaluate(self._Mf(7000, Codec='h264', AssignedProfile=None))
        self.assertEqual(Same, Other)
        self.Tiers.GetProfileCodec.assert_not_called()
        self.Tiers.GetProfileTarget.assert_not_called()


# directive: movies-video-rule | # see classifier.C9
class TestMoviesTierProfile(unittest.TestCase):

    # directive: movies-video-rule | # see classifier.C9
    def _Service(self, Resolved, Rows=None):
        Writer = Mock(**{'Assign.side_effect': lambda Ids, *A, **K: list(Ids)})
        Svc = ContentClassifierService(ProfileWriter=Writer)
        Svc.Repository = Mock(**{
            'GetMediaFileForClassification.return_value': {'Id': 10, 'StorageRootId': 2, 'AssignedProfile': None},
            'GetActiveRules.side_effect': AssertionError('rules must not be walked for a tiered library'),
        })
        Svc.FileTiers = Mock(**{'Resolve.side_effect': Resolved if callable(Resolved) else (lambda *A: Resolved)})
        Svc.Tiers = Mock(**{'GetTierProfileName.side_effect': lambda Tier: f'Profile{Tier}'})
        Svc.Db = Mock(**{'ExecuteQuery.return_value': Rows or []})
        return Svc, Writer

    # directive: movies-video-rule | # see classifier.C9
    def test_unprofiled_movie_gets_genre_tier_profile(self):
        Svc, Writer = self._Service(FileTier(3, 'genre=Action'))
        self.assertEqual(Svc.ClassifyAndAssign(10), 'Profile3')
        Writer.Assign.assert_called_once_with([10], 'Profile3', 'genre_tier', IfUnsetOnly=True)

    # directive: movies-video-rule | # see classifier.C9
    def test_movie_waiting_for_genres_gets_no_profile(self):
        Svc, Writer = self._Service(FileTier(None, 'missing_input:Genres'))
        self.assertIsNone(Svc.ClassifyAndAssign(10))
        Writer.Assign.assert_not_called()

    # directive: movies-video-rule | # see classifier.C9
    def test_reassign_moves_only_files_whose_tier_profile_differs(self):
        Rows = [
            {'Id': 1, 'StorageRootId': 2, 'AssignedProfile': 'Profile2'},
            {'Id': 2, 'StorageRootId': 2, 'AssignedProfile': 'Profile3'},
            {'Id': 3, 'StorageRootId': 2, 'AssignedProfile': None},
        ]
        Svc, Writer = self._Service(lambda Root, Id: FileTier(3, 'genre=Action') if Id != 3 else FileTier(1, 'genre=Comedy'), Rows)
        self.assertEqual(Svc.ReassignTierProfiles([1, 2, 3]), 2)
        Writer.Assign.assert_any_call([1], 'Profile3', 'genre_tier')
        Writer.Assign.assert_any_call([3], 'Profile1', 'genre_tier')
        self.assertEqual(Writer.Assign.call_count, 2)

    # directive: movies-video-rule | # see classifier.C9
    def test_reassign_query_excludes_operator_set_profiles(self):
        Svc, _ = self._Service(FileTier(3, 'genre=Action'))
        Svc.ReassignTierProfiles([1])
        Sql, Params = Svc.Db.ExecuteQuery.call_args[0]
        self.assertIn('GenreSource IS NOT NULL', Sql)
        self.assertEqual(Params[1], ['operator', 'series', 'root_folder', 'manual_sql'])


# directive: movies-video-rule | # see ingest.ST3
class TestMovieGenreSync(unittest.TestCase):

    # directive: movies-video-rule | # see ingest.ST3
    def _Service(self, Rows, Movies=None, RadarrError=None):
        self.Db = Mock(**{'ExecuteQuery.return_value': Rows})
        self.Radarr = Mock()
        if RadarrError is not None:
            self.Radarr.ListMovies.side_effect = RadarrError
        else:
            self.Radarr.ListMovies.return_value = Movies or []
        self.Classifier = Mock(**{'ReassignTierProfiles.return_value': 0})
        self.GenreTiers = Mock()
        return MovieGenreSyncService(Db=self.Db, Radarr=self.Radarr, Classifier=self.Classifier, GenreTiers=self.GenreTiers)

    # directive: movies-video-rule | # see ingest.ST3
    def test_nothing_missing_makes_no_radarr_call(self):
        self.assertEqual(self._Service([]).SyncMissing(), 0)
        self.Radarr.ListMovies.assert_not_called()
        self.Db.ExecuteNonQuery.assert_not_called()

    # directive: movies-video-rule | # see ingest.ST3
    def test_records_genres_then_reassigns_and_recomputes(self):
        Rows = [
            {'Id': 1, 'Folder': 'Heat (1995)', 'GenreSource': 'radarr'},
            {'Id': 2, 'Folder': 'Not In Radarr (2001)', 'GenreSource': 'radarr'},
        ]
        Movies = [{'path': '/movies/Heat (1995)', 'genres': ['Action', 'Crime']}]
        Svc = self._Service(Rows, Movies)
        with patch('Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService') as Qm:
            self.assertEqual(Svc.SyncMissing(), 2)
            Qm.return_value.RecomputeForFiles.assert_called_once_with([1, 2])
        Writes = {Call[0][1][0]: Call[0][1][1] for Call in self.Db.ExecuteNonQuery.call_args_list}
        self.assertEqual(Writes, {'Action,Crime': [1], '': [2]})
        self.GenreTiers.RegisterGenres.assert_called_once_with(['Action', 'Crime'])
        self.Classifier.ReassignTierProfiles.assert_called_once_with([1, 2])

    # directive: movies-video-rule | # see ingest.ST3
    def test_radarr_failure_raises_and_writes_nothing(self):
        Svc = self._Service([{'Id': 1, 'Folder': 'Heat (1995)', 'GenreSource': 'radarr'}], RadarrError=OSError('unreachable'))
        with self.assertRaises(OSError):
            Svc.SyncMissing()
        self.Db.ExecuteNonQuery.assert_not_called()

    # directive: movies-video-rule | # see ingest.ST3
    def test_unknown_genre_source_raises(self):
        with self.assertRaises(ValueError):
            self._Service([{'Id': 1, 'Folder': 'X', 'GenreSource': 'sonarr'}]).SyncMissing()


_FILE_TIER_CTE = (
    "WITH FileTier AS ("
    "  SELECT mf.Id, mf.ResolutionCategory, mf.VideoBitrateKbps, mf.VideoCompliant, mf.VideoCompliantReason, "
    "         COALESCE((SELECT MAX(COALESCE(g.QualityTier, sr.DefaultQualityTier)) "
    "                   FROM unnest(string_to_array(mf.Genres, ',')) AS x(Genre) "
    "                   LEFT JOIN GenreQualityTiers g ON g.Genre = x.Genre "
    "                   WHERE x.Genre <> ''), sr.DefaultQualityTier) AS Tier "
    "  FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
    "  WHERE sr.GenreSource IS NOT NULL AND sr.DefaultQualityTier IS NOT NULL AND mf.Genres IS NOT NULL) "
)


# directive: movies-video-rule | # see video-encoding.C1
class TestMoviesVideoRuleLive(unittest.TestCase):

    # directive: movies-video-rule | # see video-encoding.C1
    def _Count(self, Sql):
        return int(DatabaseService().ExecuteQuery(Sql)[0].get('N'))

    # directive: movies-video-rule | # see video-encoding.C1
    def test_stored_verdicts_match_the_genre_tier_rule(self):
        self.assertEqual(self._Count(
            _FILE_TIER_CTE +
            "SELECT COUNT(*) AS N FROM FileTier ft "
            "JOIN Profiles p ON p.Family = 'ANY' AND p.QualityTier = ft.Tier AND p.QualityLabel IS NOT NULL "
            "JOIN ProfileThresholds src ON src.ProfileId = p.Id AND src.ContentClass = 'live_action' AND src.Resolution = ft.ResolutionCategory "
            "JOIN ProfileThresholds tgt ON tgt.ProfileId = p.Id AND tgt.ContentClass = 'live_action' "
            "  AND tgt.Resolution = CASE WHEN src.TranscodeDownTo IN ('', 'No downscaling') THEN src.Resolution ELSE src.TranscodeDownTo END "
            "JOIN VideoComplianceThresholds m ON m.ResolutionCategory = ft.ResolutionCategory "
            "WHERE ft.VideoBitrateKbps > 0 AND ft.VideoCompliantReason IS DISTINCT FROM 'non_video_scope' "
            "  AND ft.VideoCompliant IS DISTINCT FROM (ft.VideoBitrateKbps <= ROUND(tgt.TargetKbps * m.Multiplier))"
        ), 0)

    # directive: movies-video-rule | # see video-encoding.C1
    def test_stored_reason_names_the_genre_tier(self):
        self.assertEqual(self._Count(
            _FILE_TIER_CTE +
            "SELECT COUNT(*) AS N FROM FileTier ft "
            "WHERE starts_with(ft.VideoCompliantReason, 'source_') "
            "  AND (position('(tier=' || ft.Tier || ':' in ft.VideoCompliantReason) = 0 "
            "       OR position(',genre=' in ft.VideoCompliantReason) = 0)"
        ), 0)

    # directive: movies-video-rule | # see video-encoding.C1
    def test_no_genre_sourced_row_judged_by_codec_or_profile(self):
        self.assertEqual(self._Count(
            "SELECT COUNT(*) AS N FROM MediaFiles mf "
            "JOIN StorageRoots sr ON sr.Id = mf.StorageRootId AND sr.GenreSource IS NOT NULL AND sr.DefaultQualityTier IS NOT NULL "
            "WHERE starts_with(mf.VideoCompliantReason, 'source_codec_matches_target') "
            "   OR mf.VideoCompliantReason = 'missing_input:AssignedProfile' "
            "   OR position('(profile=' in mf.VideoCompliantReason) > 0"
        ), 0)

    # directive: movies-video-rule | # see classifier.C9
    def test_non_operator_profiles_follow_the_genre_tier(self):
        self.assertEqual(self._Count(
            _FILE_TIER_CTE +
            "SELECT COUNT(*) AS N FROM FileTier ft JOIN MediaFiles mf ON mf.Id = ft.Id "
            "JOIN Profiles p ON p.Family = 'ANY' AND p.QualityTier = ft.Tier AND p.QualityLabel IS NOT NULL "
            "WHERE COALESCE(mf.AssignedProfileSource, '') NOT IN ('operator', 'series', 'root_folder', 'manual_sql') "
            "  AND mf.AssignedProfile IS DISTINCT FROM p.ProfileName"
        ), 0)


if __name__ == '__main__':
    unittest.main()
