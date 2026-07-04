from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
class BitrateLadderCell:
    Family: str
    ContentClass: str
    Resolution: str
    Tier: int
    TargetKbps: Optional[int]


@dataclass(frozen=True)
class IcqLadderCell:
    Family: str
    ContentClass: str
    Tier: int
    IcqQ: Optional[int]


# directive: transcode-flow-canonical | # see profiles.C3
class TierLadderRepository:

    # directive: transcode-flow-canonical | # see profiles.C3
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-flow-canonical | # see profiles.C3
    def GetBitrateLadder(self) -> List[BitrateLadderCell]:
        Rows = self.Db.ExecuteQuery(
            "SELECT p.Family, p.ContentClass, pt.Resolution, p.QualityTier, "
            "  MIN(pt.TargetKbps) AS targetkbps "
            "FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.Family IS NOT NULL AND p.QualityTier IS NOT NULL "
            "  AND p.ContentClass IS NOT NULL AND pt.TargetKbps IS NOT NULL "
            "GROUP BY p.Family, p.ContentClass, pt.Resolution, p.QualityTier "
            "ORDER BY p.Family, p.ContentClass, pt.Resolution, p.QualityTier"
        )
        return [
            BitrateLadderCell(
                Family=R.get('family') or '',
                ContentClass=R.get('contentclass') or '',
                Resolution=R.get('resolution') or '',
                Tier=int(R.get('qualitytier') or 0),
                TargetKbps=int(R.get('targetkbps')) if R.get('targetkbps') is not None else None,
            )
            for R in Rows
        ]

    # directive: transcode-flow-canonical | # see profiles.C3
    def GetIcqLadder(self) -> List[IcqLadderCell]:
        Rows = self.Db.ExecuteQuery(
            "SELECT p.Family, p.ContentClass, p.QualityTier, "
            "  MIN(pt.IcqQ) AS icqq "
            "FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.Family IS NOT NULL AND p.QualityTier IS NOT NULL "
            "  AND p.ContentClass IS NOT NULL AND pt.IcqQ IS NOT NULL "
            "GROUP BY p.Family, p.ContentClass, p.QualityTier "
            "ORDER BY p.Family, p.ContentClass, p.QualityTier"
        )
        return [
            IcqLadderCell(
                Family=R.get('family') or '',
                ContentClass=R.get('contentclass') or '',
                Tier=int(R.get('qualitytier') or 0),
                IcqQ=int(R.get('icqq')) if R.get('icqq') is not None else None,
            )
            for R in Rows
        ]

    # directive: transcode-flow-canonical | # see profiles.C3
    def UpdateBitrateCell(self, Family: str, ContentClass: str, Resolution: str,
                          Tier: int, TargetKbps: int) -> int:
        if TargetKbps <= 0:
            raise ValueError(f"TargetKbps must be > 0, got {TargetKbps}")
        Affected = self.Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET TargetKbps = %s "
            "WHERE Resolution = %s "
            "  AND ProfileId IN (SELECT Id FROM Profiles "
            "                    WHERE Family = %s AND ContentClass = %s AND QualityTier = %s)",
            (int(TargetKbps), Resolution, Family, ContentClass, int(Tier)),
        )
        return int(Affected or 0)

    # directive: transcode-flow-canonical | # see profiles.C3
    def UpdateIcqCell(self, Family: str, ContentClass: str, Tier: int, IcqQ: int) -> int:
        if IcqQ < 1 or IcqQ > 51:
            raise ValueError(f"IcqQ must be in [1,51], got {IcqQ}")
        Affected = self.Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET IcqQ = %s "
            "WHERE ProfileId IN (SELECT Id FROM Profiles "
            "                    WHERE Family = %s AND ContentClass = %s AND QualityTier = %s)",
            (int(IcqQ), Family, ContentClass, int(Tier)),
        )
        return int(Affected or 0)
