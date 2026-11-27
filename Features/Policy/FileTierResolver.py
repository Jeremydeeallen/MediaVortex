from dataclasses import dataclass
from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Features.Profiles.GenreQualityTierRepository import GenreQualityTierRepository


GENRES_NOT_FETCHED = 'missing_input:Genres'
NO_GENRE = 'genre=none'


@dataclass(frozen=True)
# directive: movies-video-rule | # see transcode.ST4
class FileTier:
    Tier: Optional[int]
    Origin: str


# directive: movies-video-rule | # see transcode.ST4
class FileTierResolver:

    # directive: movies-video-rule
    def __init__(self, Db: Optional[DatabaseService] = None, GenreTiers: Optional[GenreQualityTierRepository] = None):
        self.Db = Db or DatabaseService()
        self.GenreTiers = GenreTiers or GenreQualityTierRepository(self.Db)

    # directive: movies-video-rule | # see transcode.ST4
    def Resolve(self, StorageRootId: Optional[int], MediaFileId: Optional[int]) -> Optional[FileTier]:
        if StorageRootId is None:
            return None
        Library = self.Db.ExecuteQuery(
            "SELECT DefaultQualityTier, GenreSource FROM StorageRoots WHERE Id = %s",
            (int(StorageRootId),),
        )
        if not Library or Library[0].get('DefaultQualityTier') is None:
            return None
        LibraryTier = int(Library[0].get('DefaultQualityTier'))
        if not Library[0].get('GenreSource'):
            return FileTier(LibraryTier, '')
        Rows = self.Db.ExecuteQuery("SELECT Genres FROM MediaFiles WHERE Id = %s", (int(MediaFileId),))
        if not Rows:
            raise ValueError(f"FileTierResolver: MediaFileId {MediaFileId} not found")
        Genres = Rows[0].get('Genres')
        if Genres is None:
            return FileTier(None, GENRES_NOT_FETCHED)
        Names = [G for G in Genres.split(',') if G]
        if not Names:
            return FileTier(LibraryTier, NO_GENRE)
        Configured = self.GenreTiers.GetTiers(Names)
        Tiers = [(LibraryTier if Configured.get(Name) is None else Configured[Name], Name) for Name in Names]
        Tier, Name = max(Tiers, key=lambda Pair: Pair[0])
        return FileTier(Tier, f'genre={Name}')
