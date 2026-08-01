import json
import os
import re
import urllib.request

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


_HTTP_TIMEOUT_SEC = 30
_SE_RX = re.compile(r'S(\d+)E(\d+)', re.IGNORECASE)


# directive: language-worker-progress-invariant
class NoAudioResolverError(Exception):
    pass


# directive: language-worker-progress-invariant
class NoAudioResolver:

    def __init__(self, SettingsRepo=None, MediaFilesRepo=None, Db=None):
        self.SettingsRepo = SettingsRepo or SystemSettingsRepository()
        self.MediaFilesRepo = MediaFilesRepo or MediaFilesRepository()
        self.Db = Db or DatabaseService()
        self.SonarrUrl = self._RequireSetting('SonarrUrl')
        self.SonarrKey = self._RequireSetting('SonarrApiKey')
        self.RadarrUrl = self._RequireSetting('RadarrUrl')
        self.RadarrKey = self._RequireSetting('RadarrApiKey')

    def _RequireSetting(self, Key):
        Val = self.SettingsRepo.GetSystemSetting(Key)
        if not Val:
            raise RuntimeError(f"NoAudioResolver: SystemSettings.{Key} is empty; set via /settings before starting")
        return Val.strip()

    # directive: language-worker-progress-invariant
    def Resolve(self, MediaFileId, LocalFilePath):
        RootName, RelPath, FileName = self._LookupMediaFile(MediaFileId)
        RegrabOutcome = self._Regrab(RootName, RelPath, FileName, MediaFileId)
        self._DeleteFile(LocalFilePath, MediaFileId)
        self.MediaFilesRepo.DeleteMediaFile(MediaFileId)
        LoggingService.LogInfo(
            f"NoAudioResolver: MediaFileId={MediaFileId} root={RootName} regrab={RegrabOutcome}",
            'NoAudioResolver', 'Resolve',
        )

    def _LookupMediaFile(self, MediaFileId):
        Rows = self.Db.ExecuteQuery(
            "SELECT sr.Name AS RootName, mf.RelativePath AS RelPath, mf.FileName AS FileName "
            "FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
            "WHERE mf.Id = %s",
            (MediaFileId,),
        )
        if not Rows:
            raise NoAudioResolverError(f"MediaFileId={MediaFileId} not found")
        R = Rows[0]
        return R['RootName'], R['RelPath'], R['FileName']

    def _Regrab(self, RootName, RelPath, FileName, MediaFileId):
        if RootName == 'media_tv':
            return self._RegrabTv(RelPath, FileName, MediaFileId)
        if RootName == 'movies':
            return self._RegrabMovie(RelPath, MediaFileId)
        LoggingService.LogWarning(
            f"NoAudioResolver: MediaFileId={MediaFileId} on StorageRoot={RootName!r} has no *arr backing; deleting without regrab",
            'NoAudioResolver', '_Regrab',
        )
        return 'skipped-no-arr'

    def _RegrabTv(self, RelPath, FileName, MediaFileId):
        FirstSlash = RelPath.find('/')
        SeriesFolder = RelPath if FirstSlash == -1 else RelPath[:FirstSlash]
        M = _SE_RX.search(FileName or '')
        if not M:
            return f'sonarr-skip-no-sxxexx:folder={SeriesFolder!r}'
        Season, Episode = int(M.group(1)), int(M.group(2))
        Series = self._GetJson(f"{self.SonarrUrl}/api/v3/series", self.SonarrKey)
        SeriesId = self._MatchFolder(Series, SeriesFolder)
        if SeriesId is None:
            return f'sonarr-skip-unmatched-series:folder={SeriesFolder!r}'
        Eps = self._GetJson(f"{self.SonarrUrl}/api/v3/episode?seriesId={SeriesId}", self.SonarrKey)
        Match = next((E for E in Eps if E.get('seasonNumber') == Season and E.get('episodeNumber') == Episode), None)
        if Match is None:
            return f'sonarr-skip-unmatched-episode:S{Season:02d}E{Episode:02d}'
        EpisodeFileId = Match.get('episodeFileId') or 0
        if EpisodeFileId:
            self._Delete(f"{self.SonarrUrl}/api/v3/episodefile/{EpisodeFileId}", self.SonarrKey)
        self._Post(
            f"{self.SonarrUrl}/api/v3/command", self.SonarrKey,
            {'name': 'EpisodeSearch', 'episodeIds': [Match['id']]},
        )
        return f'sonarr-ok:epFileId={EpisodeFileId},episodeId={Match["id"]}'

    def _RegrabMovie(self, RelPath, MediaFileId):
        FirstSlash = RelPath.find('/')
        MovieFolder = RelPath if FirstSlash == -1 else RelPath[:FirstSlash]
        Movies = self._GetJson(f"{self.RadarrUrl}/api/v3/movie", self.RadarrKey)
        MovieId, MovieFileId = self._MatchMovie(Movies, MovieFolder)
        if MovieId is None:
            return f'radarr-skip-unmatched:folder={MovieFolder!r}'
        if MovieFileId:
            self._Delete(f"{self.RadarrUrl}/api/v3/moviefile/{MovieFileId}", self.RadarrKey)
        self._Post(
            f"{self.RadarrUrl}/api/v3/command", self.RadarrKey,
            {'name': 'MoviesSearch', 'movieIds': [MovieId]},
        )
        return f'radarr-ok:movieFileId={MovieFileId},movieId={MovieId}'

    def _MatchFolder(self, Series, WantedFolder):
        Wanted = (WantedFolder or '').strip()
        for S in Series:
            Tail = self._PathTail(S.get('path') or '')
            if Tail == Wanted:
                return S.get('id')
        return None

    def _MatchMovie(self, Movies, WantedFolder):
        Wanted = (WantedFolder or '').strip()
        for M in Movies:
            Tail = self._PathTail(M.get('path') or '')
            if Tail == Wanted:
                MovieFile = M.get('movieFile') or {}
                return M.get('id'), MovieFile.get('id') or 0
        return None, 0

    def _PathTail(self, ArrPath):
        Stripped = ArrPath.rstrip('/').rstrip('\\')
        Cut = max(Stripped.rfind('/'), Stripped.rfind('\\'))
        return Stripped if Cut == -1 else Stripped[Cut + 1:]

    def _DeleteFile(self, LocalFilePath, MediaFileId):
        try:
            os.remove(LocalFilePath)
        except FileNotFoundError:
            LoggingService.LogWarning(
                f"NoAudioResolver: MediaFileId={MediaFileId} file already gone at {LocalFilePath!r}",
                'NoAudioResolver', '_DeleteFile',
            )
        except OSError as Ex:
            raise NoAudioResolverError(f"MediaFileId={MediaFileId} os.remove failed: {Ex}")

    def _GetJson(self, Url, Key):
        Req = urllib.request.Request(Url, headers={'X-Api-Key': Key})
        with urllib.request.urlopen(Req, timeout=_HTTP_TIMEOUT_SEC) as R:
            if R.status not in (200, 201):
                raise NoAudioResolverError(f"GET {Url} rc={R.status}")
            return json.loads(R.read().decode('utf-8'))

    def _Delete(self, Url, Key):
        Req = urllib.request.Request(Url, method='DELETE', headers={'X-Api-Key': Key})
        with urllib.request.urlopen(Req, timeout=_HTTP_TIMEOUT_SEC) as R:
            if R.status not in (200, 202):
                raise NoAudioResolverError(f"DELETE {Url} rc={R.status}")

    def _Post(self, Url, Key, Body):
        Req = urllib.request.Request(
            Url, method='POST', data=json.dumps(Body).encode('utf-8'),
            headers={'X-Api-Key': Key, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(Req, timeout=_HTTP_TIMEOUT_SEC) as R:
            if R.status not in (200, 201):
                raise NoAudioResolverError(f"POST {Url} rc={R.status}")
