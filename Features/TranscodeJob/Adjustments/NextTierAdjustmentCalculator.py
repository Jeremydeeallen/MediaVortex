from dataclasses import dataclass
from typing import Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
class NextTierProfile:
    ProfileId: int
    ProfileName: str
    Family: str
    QualityTier: int
    ContentClass: str
    TargetResolutionCategory: str


# directive: transcode-flow-canonical | # see transcode.ST7
class NextTierAdjuster:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-flow-canonical | # see transcode.ST7
    def Get(self, CurrentProfileName: Optional[str]) -> Optional[NextTierProfile]:
        if not CurrentProfileName:
            return None
        Row = self.Db.ExecuteQuery(
            "SELECT Family, QualityTier, ContentClass, TargetResolutionCategory "
            "FROM Profiles WHERE ProfileName = %s",
            (CurrentProfileName,),
        )
        if not Row:
            return None
        Cur = Row[0]
        Family = Cur.get('family')
        Tier = Cur.get('qualitytier')
        ContentClass = Cur.get('contentclass')
        Target = Cur.get('targetresolutioncategory')
        if not (Family and Tier is not None and ContentClass and Target):
            return None
        NextRow = self.Db.ExecuteQuery(
            "SELECT Id, ProfileName, Family, QualityTier, ContentClass, TargetResolutionCategory "
            "FROM Profiles "
            "WHERE Family = %s AND ContentClass = %s AND TargetResolutionCategory = %s "
            "  AND QualityTier > %s AND Active = TRUE "
            "ORDER BY QualityTier LIMIT 1",
            (Family, ContentClass, Target, int(Tier)),
        )
        if not NextRow:
            return None
        N = NextRow[0]
        return NextTierProfile(
            ProfileId=int(N['id']),
            ProfileName=N['profilename'],
            Family=N['family'],
            QualityTier=int(N['qualitytier']),
            ContentClass=N['contentclass'],
            TargetResolutionCategory=N['targetresolutioncategory'],
        )
