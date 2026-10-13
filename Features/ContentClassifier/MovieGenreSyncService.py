from typing import Optional

from Core.Arr.RadarrClient import RadarrClient
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
from Features.Profiles.GenreQualityTierRepository import GenreQualityTierRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


_RADARR_SOURCE = 'radarr'
_RECOMPUTE_BATCH = 500


# directive: movies-video-rule | # see ingest.ST3
class MovieGenreSyncService:

    # directive: movies-video-rule
    def __init__(self, Db: Optional[DatabaseService] = None, Radarr: Optional[RadarrClient] = None,
                 Classifier: Optional[ContentClassifierService] = None,
                 GenreTiers: Optional[GenreQualityTierRepository] = None):
        self.Db = Db or DatabaseService()
        self.Radarr = Radarr
        self.Classifier = Classifier
        self.GenreTiers = GenreTiers or GenreQualityTierRepository(self.Db)

    # directive: movies-video-rule | # see ingest.ST3
    def _RadarrClient(self) -> RadarrClient:
        if self.Radarr is not None:
            return self.Radarr
        Settings = SystemSettingsRepository()
        return RadarrClient(Settings.GetSystemSetting('RadarrUrl'), Settings.GetSystemSetting('RadarrApiKey'))

    # directive: movies-video-rule | # see ingest.ST3
    def SyncMissing(self) -> int:
        Rows = self.Db.ExecuteQuery(
            "SELECT mf.Id, split_part(mf.RelativePath, '/', 1) AS Folder, sr.GenreSource "
            "FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
            "WHERE sr.GenreSource IS NOT NULL AND mf.Genres IS NULL ORDER BY mf.Id"
        )
        if not Rows:
            return 0
        Unknown = sorted({R.get('GenreSource') for R in Rows} - {_RADARR_SOURCE})
        if Unknown:
            raise ValueError(f"MovieGenreSyncService: unsupported StorageRoots.GenreSource {Unknown}")
        Index = RadarrClient.FolderIndex(self._RadarrClient().ListMovies())
        IdsByGenres = {}
        for R in Rows:
            Movie = Index.get((R.get('Folder') or '').strip())
            Genres = ','.join(Movie.get('genres') or []) if Movie is not None else ''
            IdsByGenres.setdefault(Genres, []).append(int(R.get('Id')))
        self.GenreTiers.RegisterGenres(sorted({G for Genres in IdsByGenres for G in Genres.split(',') if G}))
        Ids = []
        for Genres, Group in IdsByGenres.items():
            self.Db.ExecuteNonQuery("UPDATE MediaFiles SET Genres = %s WHERE Id = ANY(%s)", (Genres, Group))
            Ids.extend(Group)
        Classifier = self.Classifier or ContentClassifierService()
        Reassigned = Classifier.ReassignTierProfiles(Ids)
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Recompute = QueueManagementBusinessService()
        for I in range(0, len(Ids), _RECOMPUTE_BATCH):
            Recompute.RecomputeForFiles(Ids[I:I + _RECOMPUTE_BATCH])
        LoggingService.LogInfo(
            f"Genres recorded for {len(Ids)} files ({len(IdsByGenres.get('', []))} with no Radarr genre); {Reassigned} profiles reassigned",
            "MovieGenreSyncService", "SyncMissing",
        )
        return len(Ids)
