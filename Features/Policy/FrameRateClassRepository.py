# directive: target-policy-1a-tables | # see policy.W6, policy.C7 -- frame-rate classes are rows: a file's class is the first row with FrameRate <= MaxFps
from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.W6
class FrameRateClass:
    Name: str
    MaxFps: float


# directive: target-policy-1a-tables | # see policy.W6
class FrameRateClassRepository:

    # directive: target-policy-1a-tables | # see policy.W6
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.W6
    def ListClasses(self) -> List[FrameRateClass]:
        Rows = self.Db.ExecuteQuery("SELECT Name, MaxFps FROM FrameRateClasses ORDER BY MaxFps")
        return [FrameRateClass(Name=str(R['Name']), MaxFps=float(R['MaxFps'])) for R in Rows]

    # directive: target-policy-1a-tables | # see policy.W6
    def SetMaxFps(self, Name: str, MaxFps: float) -> int:
        if float(MaxFps) <= 0:
            raise ValueError(f"MaxFps must be > 0, got {MaxFps}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE FrameRateClasses SET MaxFps = %s WHERE Name = %s", (float(MaxFps), Name),
        ) or 0)
