from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
class ComplianceThreshold:
    ResolutionCategory: str
    Multiplier: float


# directive: video-compliance-multiplier | # see video-encoding.C1
class VideoComplianceThresholdsRepository:

    # directive: video-compliance-multiplier
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: video-compliance-multiplier | # see video-encoding.DS1
    def GetMultiplier(self, ResolutionCategory: str) -> float:
        Rows = self.Db.ExecuteQuery(
            "SELECT Multiplier FROM VideoComplianceThresholds WHERE ResolutionCategory = %s",
            (ResolutionCategory,),
        )
        if not Rows:
            raise RuntimeError(
                f"VideoComplianceThresholds has no row for ResolutionCategory={ResolutionCategory!r} -- "
                "seed migration AddVideoComplianceThresholds_2026_07_26.py not applied"
            )
        Value = Rows[0].get('multiplier')
        if Value is None:
            raise RuntimeError(
                f"VideoComplianceThresholds.Multiplier IS NULL for ResolutionCategory={ResolutionCategory!r}"
            )
        return float(Value)

    # directive: video-compliance-multiplier | # see video-encoding.C4
    def GetAll(self) -> List[ComplianceThreshold]:
        Rows = self.Db.ExecuteQuery(
            "SELECT ResolutionCategory, Multiplier FROM VideoComplianceThresholds "
            "ORDER BY ResolutionCategory"
        )
        return [
            ComplianceThreshold(
                ResolutionCategory=R.get('resolutioncategory') or '',
                Multiplier=float(R.get('multiplier')),
            )
            for R in Rows
        ]

    # directive: video-compliance-multiplier | # see video-encoding.C4
    def UpsertAll(self, Thresholds: List[ComplianceThreshold]) -> int:
        Affected = 0
        for T in Thresholds:
            if T.Multiplier <= 0:
                raise ValueError(f"Multiplier must be > 0, got {T.Multiplier} for {T.ResolutionCategory}")
            N = self.Db.ExecuteNonQuery(
                "INSERT INTO VideoComplianceThresholds (ResolutionCategory, Multiplier, LastUpdated) "
                "VALUES (%s, %s, NOW()) "
                "ON CONFLICT (ResolutionCategory) DO UPDATE "
                "SET Multiplier = EXCLUDED.Multiplier, LastUpdated = NOW()",
                (T.ResolutionCategory, T.Multiplier),
            )
            Affected += int(N or 0)
        return Affected
