from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
class TranscodeRulesRepository(BaseRepository):
    """Single-row scalar config for the Transcode operation; always reads/writes Id=1; no caching (db-is-authority)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def Get(self) -> TranscodeRulesModel:
        """Read the Id=1 row fresh per call; fall back to dataclass defaults if missing."""
        try:
            Rows = self.ExecuteQuery("SELECT Id, ResolutionExceedsProfileTarget, AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, LastUpdated FROM TranscodeRules WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("TranscodeRules row Id=1 missing -- returning defaults; run AddComplianceRuleTables.py", "TranscodeRulesRepository", "Get")
                return TranscodeRulesModel()
            R = Rows[0]
            return TranscodeRulesModel(
                Id=R['Id'],
                ResolutionExceedsProfileTarget=R['ResolutionExceedsProfileTarget'],
                AcceptableVideoCodecsCsv=R['AcceptableVideoCodecsCsv'],
                EstimatedSavingsMBThreshold=R['EstimatedSavingsMBThreshold'],
                PreventUpscale=R['PreventUpscale'],
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "TranscodeRulesRepository", "Get")
            return TranscodeRulesModel()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def Update(self, ResolutionExceedsProfileTarget: Optional[bool] = None,
               AcceptableVideoCodecsCsv: Optional[str] = None,
               EstimatedSavingsMBThreshold: Optional[int] = None,
               PreventUpscale: Optional[bool] = None) -> bool:
        """Update non-None scalars on the Id=1 row; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if ResolutionExceedsProfileTarget is not None:
                Sets.append("ResolutionExceedsProfileTarget = %s"); Values.append(ResolutionExceedsProfileTarget)
            if AcceptableVideoCodecsCsv is not None:
                Sets.append("AcceptableVideoCodecsCsv = %s"); Values.append(AcceptableVideoCodecsCsv)
            if EstimatedSavingsMBThreshold is not None:
                Sets.append("EstimatedSavingsMBThreshold = %s"); Values.append(int(EstimatedSavingsMBThreshold))
            if PreventUpscale is not None:
                Sets.append("PreventUpscale = %s"); Values.append(PreventUpscale)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = "UPDATE TranscodeRules SET " + ", ".join(Sets) + " WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "TranscodeRulesRepository", "Update")
            return False
