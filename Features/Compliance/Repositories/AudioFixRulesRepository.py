from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Models.AudioFixRulesModel import AudioFixRulesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C4
class AudioFixRulesRepository(BaseRepository):
    """Single-row scalar config for the AudioFix operation; always reads/writes Id=1; no caching (db-is-authority)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C4
    def Get(self) -> AudioFixRulesModel:
        """Read the Id=1 row fresh per call; fall back to dataclass defaults if missing."""
        try:
            Rows = self.ExecuteQuery("SELECT Id, TargetLoudnessLufs, ToleranceLufs, RequireLufsMeasured, LastUpdated FROM AudioFixRules WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("AudioFixRules row Id=1 missing -- returning defaults; run AddComplianceRuleTables.py", "AudioFixRulesRepository", "Get")
                return AudioFixRulesModel()
            R = Rows[0]
            return AudioFixRulesModel(
                Id=R['Id'],
                TargetLoudnessLufs=R['TargetLoudnessLufs'],
                ToleranceLufs=float(R['ToleranceLufs']),
                RequireLufsMeasured=R['RequireLufsMeasured'],
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "AudioFixRulesRepository", "Get")
            return AudioFixRulesModel()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C4
    def Update(self, TargetLoudnessLufs: Optional[int] = None,
               ToleranceLufs: Optional[float] = None,
               RequireLufsMeasured: Optional[bool] = None) -> bool:
        """Update non-None scalars on the Id=1 row; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if TargetLoudnessLufs is not None:
                Sets.append("TargetLoudnessLufs = %s"); Values.append(int(TargetLoudnessLufs))
            if ToleranceLufs is not None:
                Sets.append("ToleranceLufs = %s"); Values.append(float(ToleranceLufs))
            if RequireLufsMeasured is not None:
                Sets.append("RequireLufsMeasured = %s"); Values.append(RequireLufsMeasured)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = "UPDATE AudioFixRules SET " + ", ".join(Sets) + " WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "AudioFixRulesRepository", "Update")
            return False
