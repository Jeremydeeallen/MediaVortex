# directive: target-policy-1a-tables | # see policy.W3, policy.C7 -- LadderCells keyed (tier, class, source resolution, frame-rate class); read fresh per call
from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.W3
class LadderCell:
    Id: int
    QualityTier: int
    ContentClass: str
    SourceResolution: str
    FrameRateClass: str
    TargetResolution: str
    TargetKbps: int
    IcqQ: Optional[int]


_COLUMNS = "Id, QualityTier, ContentClass, SourceResolution, FrameRateClass, TargetResolution, TargetKbps, IcqQ"


# directive: target-policy-1a-tables | # see policy.W3
def _Cell(R) -> LadderCell:
    return LadderCell(
        Id=int(R['Id']), QualityTier=int(R['QualityTier']), ContentClass=str(R['ContentClass']),
        SourceResolution=str(R['SourceResolution']), FrameRateClass=str(R['FrameRateClass']),
        TargetResolution=str(R['TargetResolution']), TargetKbps=int(R['TargetKbps']),
        IcqQ=None if R['IcqQ'] is None else int(R['IcqQ']),
    )


# directive: target-policy-1a-tables | # see policy.W3
class LadderCellRepository:

    # directive: target-policy-1a-tables | # see policy.W3
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.W3
    def ListCells(self) -> List[LadderCell]:
        Rows = self.Db.ExecuteQuery(
            f"SELECT {_COLUMNS} FROM LadderCells ORDER BY ContentClass, FrameRateClass, QualityTier, SourceResolution"
        )
        return [_Cell(R) for R in Rows]

    # directive: target-policy-1a-tables | # see policy.W3
    def Get(self, QualityTier: int, ContentClass: str, SourceResolution: str, FrameRateClass: str) -> Optional[LadderCell]:
        Rows = self.Db.ExecuteQuery(
            f"SELECT {_COLUMNS} FROM LadderCells WHERE QualityTier = %s AND ContentClass = %s AND SourceResolution = %s AND FrameRateClass = %s",
            (int(QualityTier), ContentClass, SourceResolution, FrameRateClass),
        )
        return _Cell(Rows[0]) if Rows else None

    # directive: target-policy-1a-tables | # see policy.W3
    def Update(self, QualityTier: int, ContentClass: str, SourceResolution: str, FrameRateClass: str,
               TargetResolution: str, TargetKbps: int, IcqQ: Optional[int]) -> int:
        if int(TargetKbps) <= 0:
            raise ValueError(f"TargetKbps must be > 0, got {TargetKbps}")
        if IcqQ is not None and not (1 <= int(IcqQ) <= 51):
            raise ValueError(f"IcqQ must be in [1, 51] or None, got {IcqQ}")
        if not TargetResolution:
            raise ValueError("TargetResolution is required")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE LadderCells SET TargetResolution = %s, TargetKbps = %s, IcqQ = %s "
            "WHERE QualityTier = %s AND ContentClass = %s AND SourceResolution = %s AND FrameRateClass = %s",
            (TargetResolution, int(TargetKbps), None if IcqQ is None else int(IcqQ),
             int(QualityTier), ContentClass, SourceResolution, FrameRateClass),
        ) or 0)
