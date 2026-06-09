from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Models.RemuxRulesModel import RemuxRulesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C3
class RemuxRulesRepository(BaseRepository):
    """Single-row scalar config for the Remux operation; always reads/writes Id=1; no caching (db-is-authority)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C3
    def Get(self) -> RemuxRulesModel:
        """Read the Id=1 row fresh per call; fall back to dataclass defaults if missing."""
        try:
            Rows = self.ExecuteQuery("SELECT Id, AcceptableContainersCsv, AcceptableAudioCodecsMp4Csv, RequireAudioNormalized, LastUpdated FROM RemuxRules WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("RemuxRules row Id=1 missing -- returning defaults; run AddComplianceRuleTables.py", "RemuxRulesRepository", "Get")
                return RemuxRulesModel()
            R = Rows[0]
            return RemuxRulesModel(
                Id=R['Id'],
                AcceptableContainersCsv=R['AcceptableContainersCsv'],
                AcceptableAudioCodecsMp4Csv=R['AcceptableAudioCodecsMp4Csv'],
                RequireAudioNormalized=R['RequireAudioNormalized'],
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "RemuxRulesRepository", "Get")
            return RemuxRulesModel()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C3
    def Update(self, AcceptableContainersCsv: Optional[str] = None,
               AcceptableAudioCodecsMp4Csv: Optional[str] = None,
               RequireAudioNormalized: Optional[bool] = None) -> bool:
        """Update non-None scalars on the Id=1 row; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if AcceptableContainersCsv is not None:
                Sets.append("AcceptableContainersCsv = %s"); Values.append(AcceptableContainersCsv)
            if AcceptableAudioCodecsMp4Csv is not None:
                Sets.append("AcceptableAudioCodecsMp4Csv = %s"); Values.append(AcceptableAudioCodecsMp4Csv)
            if RequireAudioNormalized is not None:
                Sets.append("RequireAudioNormalized = %s"); Values.append(RequireAudioNormalized)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = "UPDATE RemuxRules SET " + ", ".join(Sets) + " WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "RemuxRulesRepository", "Update")
            return False
