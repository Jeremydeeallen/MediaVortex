from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


POLICY_SQL = (
    "SELECT COALESCE(PreVerticalReNormalizePolicy, 'lazy') AS Pol "
    "FROM AudioNormalizationConfig WHERE Scope = 'global' LIMIT 1"
)


VERTICAL_DEPLOY_DATE = '2026-06-17'


DETECT_SQL = (
    "WITH latest_attempt AS ("
    "  SELECT DISTINCT ON (ta.MediaFileId) "
    "    ta.MediaFileId, ta.AudioTracksEmittedJson, ta.AudioPolicyJson, ta.CompletedDate "
    "  FROM TranscodeAttempts ta "
    "  WHERE ta.Success = TRUE "
    "  ORDER BY ta.MediaFileId, ta.CompletedDate DESC NULLS LAST, ta.Id DESC"
    ") "
    "SELECT DISTINCT mf.Id FROM MediaFiles mf "
    "JOIN latest_attempt la ON la.MediaFileId = mf.Id "
    "CROSS JOIN LATERAL jsonb_array_elements(COALESCE(la.AudioTracksEmittedJson, '[]'::jsonb)) AS track "
    "WHERE mf.AudioComplete = TRUE "
    "AND la.CompletedDate >= %s::timestamp "
    "AND ABS((track->>'AchievedIntegratedLufs')::REAL - COALESCE("
    "(la.AudioPolicyJson->>'TargetIntegratedLufs')::REAL, -23.0)) > 4.0"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class ConsistencyBandDeviantWithComplete(IAudioVerticalInvariant):
    """Detects AudioComplete=true MediaFiles whose latest attempt has at least one Deviant-band track (>4 LU off target)."""

    Name = "ConsistencyBandDeviantWithComplete"

    # directive: audio-vertical-converge-to-zero | # see directive.md Z7
    def Detect(self):
        """Return MediaFiles.Id list for post-vertical AudioComplete files that drifted out of +/-4 LU. Pre-vertical artifacts (latest attempt completed before the vertical shipped) are excluded unless PreVerticalReNormalizePolicy is 'aggressive' -- they need re-transcode of a now-destroyed source, so re-queueing them lossily transcodes a transcode."""
        try:
            Db = DatabaseService()
            PolRows = Db.ExecuteQuery(POLICY_SQL)
            Policy = (PolRows[0]['pol'] if PolRows else 'lazy') or 'lazy'
            CutoffDate = '1970-01-01' if Policy == 'aggressive' else VERTICAL_DEPLOY_DATE
            Rows = Db.ExecuteQuery(DETECT_SQL, (CutoffDate,))
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "ConsistencyBandDeviantWithComplete.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
