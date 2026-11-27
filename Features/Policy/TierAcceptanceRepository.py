# directive: target-policy-1a-tables | # see policy.W5 -- the tier rows of Profiles carry the acceptance recipe; read fresh per call
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService

TIER_ROWS = "Family = 'ANY' AND QualityLabel IS NOT NULL AND QualityTier IS NOT NULL"


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.W5
class TierAcceptance:
    ProfileId: int
    ProfileName: str
    QualityTier: int
    QualityLabel: str
    QualityTestRequired: bool
    VmafMin: Optional[float]
    VmafMax: Optional[float]
    HeldFrameDetectionThreshold: Optional[float]
    HeldFrameP25Min: Optional[float]
    HeldFrameMeanMin: Optional[float]
    LiveActionP10Min: Optional[float]


_EDITABLE = frozenset({'QualityLabel', 'QualityTestRequired', 'VmafMin', 'VmafMax', 'HeldFrameDetectionThreshold',
                       'HeldFrameP25Min', 'HeldFrameMeanMin', 'LiveActionP10Min'})
_SELECT = (
    "SELECT Id, ProfileName, QualityTier, QualityLabel, QualityTestRequired, VmafMin, VmafMax, "
    "HeldFrameDetectionThreshold, HeldFrameP25Min, HeldFrameMeanMin, LiveActionP10Min FROM Profiles"
)


# directive: target-policy-1a-tables | # see policy.W5
def _OptFloat(V) -> Optional[float]:
    return None if V is None else float(V)


# directive: target-policy-1a-tables | # see policy.W5
def _Row(R) -> TierAcceptance:
    return TierAcceptance(
        ProfileId=int(R['Id']), ProfileName=str(R['ProfileName']), QualityTier=int(R['QualityTier']),
        QualityLabel=str(R['QualityLabel']), QualityTestRequired=bool(R['QualityTestRequired']),
        VmafMin=_OptFloat(R['VmafMin']), VmafMax=_OptFloat(R['VmafMax']),
        HeldFrameDetectionThreshold=_OptFloat(R['HeldFrameDetectionThreshold']),
        HeldFrameP25Min=_OptFloat(R['HeldFrameP25Min']), HeldFrameMeanMin=_OptFloat(R['HeldFrameMeanMin']),
        LiveActionP10Min=_OptFloat(R['LiveActionP10Min']),
    )


# directive: target-policy-1a-tables | # see policy.W5
class TierAcceptanceRepository:

    # directive: target-policy-1a-tables | # see policy.W5
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.W5
    def ListTiers(self) -> List[TierAcceptance]:
        Rows = self.Db.ExecuteQuery(f"{_SELECT} WHERE {TIER_ROWS} ORDER BY QualityTier")
        return [_Row(R) for R in Rows]

    # directive: target-policy-1a-tables | # see policy.W5
    def Get(self, QualityTier: int) -> Optional[TierAcceptance]:
        Rows = self.Db.ExecuteQuery(f"{_SELECT} WHERE {TIER_ROWS} AND QualityTier = %s", (int(QualityTier),))
        return _Row(Rows[0]) if Rows else None

    # directive: target-policy-1a-tables | # see policy.W5
    def Update(self, QualityTier: int, Changes: Dict[str, Any]) -> int:
        Unknown = sorted(set(Changes) - _EDITABLE)
        if Unknown:
            raise ValueError(f"Tier acceptance has no editable column(s) {Unknown}")
        if not Changes:
            return 0
        Names = sorted(Changes)
        SetClause = ', '.join(f"{N} = %s" for N in Names)
        return int(self.Db.ExecuteNonQuery(
            f"UPDATE Profiles SET {SetClause} WHERE {TIER_ROWS} AND QualityTier = %s",
            tuple(Changes[N] for N in Names) + (int(QualityTier),),
        ) or 0)
