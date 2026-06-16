from typing import List, Optional
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTiersRepository import ResolutionTiersRepository


# directive: resolution-types | # see resolution-types.C14
class ResolutionTierRegistry:
    """Per-batch registry over the ResolutionTiers table. Snapshot loaded on construction (db-is-authority: a new request/batch builds a new registry; tier table edits take effect on next batch). FromDims uses max(Width, Height) as the SOLE classification discriminant -- orientation-agnostic."""

    # directive: resolution-types | # see resolution-types.C14
    def __init__(self, Repository: Optional[ResolutionTiersRepository] = None):
        Repo = Repository or ResolutionTiersRepository()
        self._Tiers: List[ResolutionTier] = Repo.GetAll()
        if not self._Tiers:
            raise RuntimeError("ResolutionTiers table is empty; run Scripts/SQLScripts/AddResolutionTiersTable.py")
        self._ByName = {T.Name: T for T in self._Tiers}
        self._ByRankDesc = sorted(self._Tiers, key=lambda T: -T.Rank)
        self._LowestRank = min(self._Tiers, key=lambda T: T.Rank)

    @property
    # directive: resolution-types | # see resolution-types.C14
    def All(self) -> List[ResolutionTier]:
        return list(self._Tiers)

    # directive: resolution-types | # see resolution-types.C14
    def FromDims(self, Width: int, Height: int) -> ResolutionTier:
        """Bucket on max(Width, Height) -- works for landscape, portrait, square, ultra-wide, letterbox. Walks tiers high-rank-first; returns the highest tier whose MinLongEdge <= longedge. Falls back to the lowest tier (T480p) for tiny inputs."""
        if Width <= 0 or Height <= 0:
            return self._LowestRank
        LongEdge = Width if Width >= Height else Height
        for T in self._ByRankDesc:
            if LongEdge >= T.MinLongEdge:
                return T
        return self._LowestRank

    # directive: resolution-types | # see resolution-types.C14
    def FromCategory(self, Category: Optional[str]) -> Optional[ResolutionTier]:
        """Map legacy category strings ('1080p', '720p', '4k', etc.) onto a tier by name. Returns None on unknown/empty input."""
        if Category is None:
            return None
        C = Category.strip()
        if not C:
            return None
        if C in self._ByName:
            return self._ByName[C]
        Cl = C.lower()
        for T in self._Tiers:
            if T.Name.lower() == Cl or T.Name.lower() == 't' + Cl:
                return T
        if Cl in ('4k', 'uhd'):
            return self._ByName.get('T2160p')
        if Cl.endswith('p'):
            Synth = 'T' + Cl
            return self._ByName.get(Synth)
        return None

    # directive: resolution-types | # see resolution-types.C14
    def Get(self, Name: str) -> Optional[ResolutionTier]:
        """Direct lookup by tier name (e.g. 'T1080p')."""
        return self._ByName.get(Name)
