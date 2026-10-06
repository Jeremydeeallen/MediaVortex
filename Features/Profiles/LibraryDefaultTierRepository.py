from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
class LibraryDefaultTier:
    StorageRootId: int
    Name: str
    DefaultQualityTier: Optional[int]


# directive: tv-video-rule-tier1 | # see transcode.ST4
class LibraryDefaultTierRepository:

    # directive: tv-video-rule-tier1
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: tv-video-rule-tier1 | # see transcode.ST4
    def GetDefaultQualityTier(self, StorageRootId: Optional[int]) -> Optional[int]:
        if StorageRootId is None:
            return None
        Rows = self.Db.ExecuteQuery(
            "SELECT DefaultQualityTier FROM StorageRoots WHERE Id = %s",
            (int(StorageRootId),),
        )
        if not Rows:
            return None
        Value = Rows[0].get('DefaultQualityTier')
        return int(Value) if Value is not None else None

    # directive: tv-video-rule-tier1
    def ListLibraries(self) -> List[LibraryDefaultTier]:
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, Name, DefaultQualityTier FROM StorageRoots ORDER BY Id"
        )
        return [
            LibraryDefaultTier(
                StorageRootId=int(R.get('Id')),
                Name=R.get('Name'),
                DefaultQualityTier=int(R.get('DefaultQualityTier')) if R.get('DefaultQualityTier') is not None else None,
            )
            for R in Rows
        ]

    # directive: tv-video-rule-tier1
    def SetDefaultQualityTier(self, StorageRootId: int, Tier: Optional[int]) -> int:
        if Tier is not None and not (1 <= int(Tier) <= 5):
            raise ValueError(f"DefaultQualityTier must be 1-5 or None, got {Tier!r}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE StorageRoots SET DefaultQualityTier = %s WHERE Id = %s",
            (int(Tier) if Tier is not None else None, int(StorageRootId)),
        ) or 0)
