from typing import List
from Core.Database.BaseRepository import BaseRepository
from Core.Resolution.ResolutionTier import ResolutionTier


# directive: resolution-types | # see resolution-types.C2
class ResolutionTiersRepository(BaseRepository):
    """Fresh DB read of the ResolutionTiers table. Per db-is-authority: no instance cache; every Get() hits the DB. Used by ResolutionTierRegistry."""

    # directive: resolution-types | # see resolution-types.C2
    def GetAll(self) -> List[ResolutionTier]:
        """Return all tiers sorted by Rank ascending."""
        Rows = self.ExecuteQuery(
            "SELECT Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank "
            "FROM ResolutionTiers ORDER BY Rank ASC"
        )
        return [
            ResolutionTier(
                Name=R['Name'],
                MinLongEdge=int(R['MinLongEdge']),
                CanonicalWidth=int(R['CanonicalWidth']),
                CanonicalHeight=int(R['CanonicalHeight']),
                Rank=int(R['Rank']),
            )
            for R in Rows
        ]
