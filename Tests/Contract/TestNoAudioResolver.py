import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.NoAudioResolver import NoAudioResolver, NoAudioResolverError


def _MakeSettings(SonarrUrl='http://sonarr.test/sonarr', SonarrKey='sk',
                  RadarrUrl='http://radarr.test/radarr', RadarrKey='rk'):
    Repo = MagicMock()
    Repo.GetSystemSetting.side_effect = lambda K: {
        'SonarrUrl': SonarrUrl,
        'SonarrApiKey': SonarrKey,
        'RadarrUrl': RadarrUrl,
        'RadarrApiKey': RadarrKey,
    }.get(K)
    return Repo


def _MakeDb(RootName='media_tv', RelPath='SeriesFolder/Season 01/Show S01E05.mkv', FileName='Show S01E05.mkv'):
    Db = MagicMock()
    Db.ExecuteQuery.return_value = [{'RootName': RootName, 'RelPath': RelPath, 'FileName': FileName}]
    return Db


# directive: language-worker-progress-invariant C5
class TestNoAudioResolverEnvFailLoud(unittest.TestCase):

    def test_missing_sonarr_url_raises(self):
        Settings = _MakeSettings(SonarrUrl='')
        with self.assertRaises(RuntimeError) as Ctx:
            NoAudioResolver(SettingsRepo=Settings, MediaFilesRepo=MagicMock(), Db=MagicMock())
        self.assertIn('SonarrUrl', str(Ctx.exception))

    def test_missing_sonarr_key_raises(self):
        Settings = _MakeSettings(SonarrKey='')
        with self.assertRaises(RuntimeError) as Ctx:
            NoAudioResolver(SettingsRepo=Settings, MediaFilesRepo=MagicMock(), Db=MagicMock())
        self.assertIn('SonarrApiKey', str(Ctx.exception))

    def test_missing_radarr_url_raises(self):
        Settings = _MakeSettings(RadarrUrl='')
        with self.assertRaises(RuntimeError) as Ctx:
            NoAudioResolver(SettingsRepo=Settings, MediaFilesRepo=MagicMock(), Db=MagicMock())
        self.assertIn('RadarrUrl', str(Ctx.exception))

    def test_missing_radarr_key_raises(self):
        Settings = _MakeSettings(RadarrKey='')
        with self.assertRaises(RuntimeError) as Ctx:
            NoAudioResolver(SettingsRepo=Settings, MediaFilesRepo=MagicMock(), Db=MagicMock())
        self.assertIn('RadarrApiKey', str(Ctx.exception))


# directive: language-worker-progress-invariant C3
class TestNoAudioResolverRouting(unittest.TestCase):

    def _MakeResolver(self, RootName, RelPath='folder/file.mkv', FileName='file.mkv'):
        Repo = MagicMock()
        R = NoAudioResolver(
            SettingsRepo=_MakeSettings(),
            MediaFilesRepo=Repo,
            Db=_MakeDb(RootName=RootName, RelPath=RelPath, FileName=FileName),
        )
        R._DeleteFile = MagicMock()
        return R, Repo

    def test_media_tv_routes_to_sonarr(self):
        R, Repo = self._MakeResolver('media_tv', 'MyShow/Season 01/MyShow S01E05.mkv', 'MyShow S01E05.mkv')
        R._RegrabTv = MagicMock(return_value='sonarr-ok')
        R._RegrabMovie = MagicMock()
        R.Resolve(42, '/mnt/tv/MyShow/Season 01/MyShow S01E05.mkv')
        R._RegrabTv.assert_called_once()
        R._RegrabMovie.assert_not_called()
        Repo.DeleteMediaFile.assert_called_once_with(42)

    def test_movies_routes_to_radarr(self):
        R, Repo = self._MakeResolver('movies', 'MyMovie (2020)/MyMovie.mkv', 'MyMovie.mkv')
        R._RegrabMovie = MagicMock(return_value='radarr-ok')
        R._RegrabTv = MagicMock()
        R.Resolve(42, '/mnt/movies/MyMovie (2020)/MyMovie.mkv')
        R._RegrabMovie.assert_called_once()
        R._RegrabTv.assert_not_called()
        Repo.DeleteMediaFile.assert_called_once_with(42)

    def test_other_root_skips_arr_but_still_deletes(self):
        R, Repo = self._MakeResolver('xxx', 'stuff/thing.mkv', 'thing.mkv')
        R._RegrabTv = MagicMock()
        R._RegrabMovie = MagicMock()
        R.Resolve(42, '/mnt/xxx/stuff/thing.mkv')
        R._RegrabTv.assert_not_called()
        R._RegrabMovie.assert_not_called()
        Repo.DeleteMediaFile.assert_called_once_with(42)


# directive: language-worker-progress-invariant C2
class TestNoAudioResolverOrdering(unittest.TestCase):

    def test_regrab_then_disk_delete_then_db_cascade(self):
        Repo = MagicMock()
        R = NoAudioResolver(
            SettingsRepo=_MakeSettings(),
            MediaFilesRepo=Repo,
            Db=_MakeDb(),
        )
        Order = []
        R._RegrabTv = MagicMock(side_effect=lambda *A, **K: Order.append('regrab') or 'ok')
        R._DeleteFile = MagicMock(side_effect=lambda *A, **K: Order.append('disk'))
        Repo.DeleteMediaFile.side_effect = lambda *A, **K: Order.append('cascade')
        R.Resolve(42, '/mnt/tv/foo/bar.mkv')
        self.assertEqual(Order, ['regrab', 'disk', 'cascade'])


# directive: language-worker-progress-invariant C2
class TestNoAudioResolverHttpShape(unittest.TestCase):

    def test_sonarr_flow_calls_delete_and_search(self):
        Db = _MakeDb(RootName='media_tv', RelPath='Silo/Season 01/Silo S01E05.mkv', FileName='Silo S01E05.mkv')
        R = NoAudioResolver(SettingsRepo=_MakeSettings(), MediaFilesRepo=MagicMock(), Db=Db)
        R._GetJson = MagicMock(side_effect=[
            [{'id': 100, 'path': '/data/tv/Silo'}],
            [{'id': 555, 'seasonNumber': 1, 'episodeNumber': 5, 'episodeFileId': 777}],
        ])
        R._Delete = MagicMock()
        R._Post = MagicMock()
        R._DeleteFile = MagicMock()
        R.Resolve(42, '/mnt/tv/Silo/Season 01/Silo S01E05.mkv')
        R._Delete.assert_called_once()
        DeleteUrl = R._Delete.call_args.args[0]
        self.assertIn('/api/v3/episodefile/777', DeleteUrl)
        R._Post.assert_called_once()
        PostBody = R._Post.call_args.args[2]
        self.assertEqual(PostBody['name'], 'EpisodeSearch')
        self.assertEqual(PostBody['episodeIds'], [555])

    def test_radarr_flow_calls_delete_and_search(self):
        Db = _MakeDb(RootName='movies', RelPath='Dune (2021)/Dune.mkv', FileName='Dune.mkv')
        R = NoAudioResolver(SettingsRepo=_MakeSettings(), MediaFilesRepo=MagicMock(), Db=Db)
        R._GetJson = MagicMock(return_value=[
            {'id': 200, 'path': '/data/movies/Dune (2021)', 'movieFile': {'id': 888}},
        ])
        R._Delete = MagicMock()
        R._Post = MagicMock()
        R._DeleteFile = MagicMock()
        R.Resolve(42, '/mnt/movies/Dune (2021)/Dune.mkv')
        R._Delete.assert_called_once()
        DeleteUrl = R._Delete.call_args.args[0]
        self.assertIn('/api/v3/moviefile/888', DeleteUrl)
        R._Post.assert_called_once()
        PostBody = R._Post.call_args.args[2]
        self.assertEqual(PostBody['name'], 'MoviesSearch')
        self.assertEqual(PostBody['movieIds'], [200])


if __name__ == '__main__':
    unittest.main()
