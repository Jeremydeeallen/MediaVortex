from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
# directive: profile-row-lookup | # see profile-tier-ladder.S4
class LibraryDefaultTier:
    StorageRootId: int
    Name: str
    DefaultQualityTier: Optional[int]
    DefaultContentClass: Optional[str]


# directive: tv-video-rule-tier1 | # see transcode.ST4
class LibraryDefaultTierRepository:

    # directive: tv-video-rule-tier1
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: tv-video-rule-tier1, profile-row-lookup | # see profile-tier-ladder.S4
    def ListLibraries(self) -> List[LibraryDefaultTier]:
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, Name, DefaultQualityTier, DefaultContentClass FROM StorageRoots ORDER BY Id"
        )
        return [
            LibraryDefaultTier(
                StorageRootId=int(R.get('Id')),
                Name=R.get('Name'),
                DefaultQualityTier=int(R.get('DefaultQualityTier')) if R.get('DefaultQualityTier') is not None else None,
                DefaultContentClass=R.get('DefaultContentClass'),
            )
            for R in Rows
        ]

    # directive: profile-row-lookup | # see profile-tier-ladder.S4
    def SetDefaultContentClass(self, StorageRootId: int, ContentClass: Optional[str]) -> int:
        if ContentClass is not None and ContentClass not in ('live_action', 'animation'):
            raise ValueError(f"DefaultContentClass must be live_action, animation or None, got {ContentClass!r}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE StorageRoots SET DefaultContentClass = %s WHERE Id = %s",
            (ContentClass, int(StorageRootId)),
        ) or 0)

    # directive: movies-video-rule | # see video-encoding.C4
    def ListGenreSourcedLibraryIds(self) -> List[int]:
        Rows = self.Db.ExecuteQuery("SELECT Id FROM StorageRoots WHERE GenreSource IS NOT NULL ORDER BY Id")
        return [int(R.get('Id')) for R in Rows]

    # directive: tv-video-rule-tier1
    def SetDefaultQualityTier(self, StorageRootId: int, Tier: Optional[int]) -> int:
        if Tier is not None and not (1 <= int(Tier) <= 5):
            raise ValueError(f"DefaultQualityTier must be 1-5 or None, got {Tier!r}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE StorageRoots SET DefaultQualityTier = %s WHERE Id = %s",
            (int(Tier) if Tier is not None else None, int(StorageRootId)),
        ) or 0)
