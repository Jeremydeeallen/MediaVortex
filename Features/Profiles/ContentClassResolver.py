from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Features.Profiles.GenreQualityTierRepository import GenreQualityTierRepository


# directive: profile-row-lookup | # see profile-tier-ladder.C10
class ContentClassResolver:

    # directive: profile-row-lookup | # see profile-tier-ladder.C10
    def __init__(self, Db: Optional[DatabaseService] = None, GenreTiers: Optional[GenreQualityTierRepository] = None):
        self.Db = Db or DatabaseService()
        self.GenreTiers = GenreTiers or GenreQualityTierRepository(self.Db)

    # directive: profile-row-lookup | # see profile-tier-ladder.C10 -- first genre with a class wins, else the library default, else None (reported as missing_input, never substituted)
    def Resolve(self, StorageRootId: Optional[int], MediaFileId: Optional[int]) -> Optional[str]:
        if StorageRootId is None:
            return None
        Library = self.Db.ExecuteQuery("SELECT DefaultContentClass FROM StorageRoots WHERE Id = %s", (int(StorageRootId),))
        if not Library:
            raise ValueError(f"ContentClassResolver: StorageRootId {StorageRootId} not found")
        if MediaFileId is not None:
            Rows = self.Db.ExecuteQuery("SELECT Genres FROM MediaFiles WHERE Id = %s", (int(MediaFileId),))
            if not Rows:
                raise ValueError(f"ContentClassResolver: MediaFileId {MediaFileId} not found")
            Genres = Rows[0].get('Genres')
            Names = [G for G in Genres.split(',') if G] if Genres else []
            if Names:
                Classes = self.GenreTiers.GetClasses(Names)
                for Name in Names:
                    if Classes.get(Name):
                        return Classes[Name]
        return Library[0].get('DefaultContentClass')
