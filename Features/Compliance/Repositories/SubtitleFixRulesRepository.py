from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Models.SubtitleFixRulesModel import SubtitleFixRulesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C5
class SubtitleFixRulesRepository(BaseRepository):
    """Single-row scalar config for the SubtitleFix operation; always reads/writes Id=1; no caching (db-is-authority)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C5
    def Get(self) -> SubtitleFixRulesModel:
        """Read the Id=1 row fresh per call; fall back to dataclass defaults if missing."""
        try:
            Rows = self.ExecuteQuery("SELECT Id, Enabled, MovTextRequiredForMp4, NonNativeSubtitleFormatsCsv, RequireForcedSubtitlesPresent, LastUpdated FROM SubtitleFixRules WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("SubtitleFixRules row Id=1 missing -- returning defaults; run AddComplianceRuleTables.py", "SubtitleFixRulesRepository", "Get")
                return SubtitleFixRulesModel()
            R = Rows[0]
            return SubtitleFixRulesModel(
                Id=R['Id'],
                Enabled=R['Enabled'],
                MovTextRequiredForMp4=R['MovTextRequiredForMp4'],
                NonNativeSubtitleFormatsCsv=R['NonNativeSubtitleFormatsCsv'],
                RequireForcedSubtitlesPresent=R['RequireForcedSubtitlesPresent'],
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "SubtitleFixRulesRepository", "Get")
            return SubtitleFixRulesModel()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C5
    def Update(self, Enabled: Optional[bool] = None,
               MovTextRequiredForMp4: Optional[bool] = None,
               NonNativeSubtitleFormatsCsv: Optional[str] = None,
               RequireForcedSubtitlesPresent: Optional[bool] = None) -> bool:
        """Update non-None scalars on the Id=1 row; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if Enabled is not None:
                Sets.append("Enabled = %s"); Values.append(Enabled)
            if MovTextRequiredForMp4 is not None:
                Sets.append("MovTextRequiredForMp4 = %s"); Values.append(MovTextRequiredForMp4)
            if NonNativeSubtitleFormatsCsv is not None:
                Sets.append("NonNativeSubtitleFormatsCsv = %s"); Values.append(NonNativeSubtitleFormatsCsv)
            if RequireForcedSubtitlesPresent is not None:
                Sets.append("RequireForcedSubtitlesPresent = %s"); Values.append(RequireForcedSubtitlesPresent)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = "UPDATE SubtitleFixRules SET " + ", ".join(Sets) + " WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "SubtitleFixRulesRepository", "Update")
            return False
