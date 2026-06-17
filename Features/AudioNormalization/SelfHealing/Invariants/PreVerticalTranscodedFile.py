from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


VERTICAL_DEPLOY_DATE = '2026-06-17'


POLICY_SQL = (
    "SELECT COALESCE(PreVerticalReNormalizePolicy, 'lazy') AS Pol "
    "FROM AudioNormalizationConfig WHERE Scope = 'global' LIMIT 1"
)


DETECT_SQL = (
    "SELECT Id FROM MediaFiles "
    "WHERE TranscodedByMediaVortex = TRUE "
    "AND AudioLanguages = 'und' "
    "AND COALESCE(LastModifiedDate, '1970-01-01'::timestamp) < %s::timestamp"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class PreVerticalTranscodedFile(IAudioVerticalInvariant):
    """Detects pre-vertical TranscodedByMediaVortex files; gated by AudioNormalizationConfig.PreVerticalReNormalizePolicy."""

    Name = "PreVerticalTranscodedFile"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return MediaFiles.Id list when policy != 'none' AND vertical-deploy-cutoff is in the past."""
        try:
            PolRows = DatabaseService().ExecuteQuery(POLICY_SQL)
            Policy = (PolRows[0]['pol'] if PolRows else 'lazy') or 'lazy'
            if Policy == 'none':
                return []
            if Policy == 'lazy':
                return []
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL, (VERTICAL_DEPLOY_DATE,))
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "PreVerticalTranscodedFile.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
