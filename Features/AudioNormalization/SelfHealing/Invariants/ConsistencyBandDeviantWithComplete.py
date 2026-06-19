from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "WITH latest_attempt AS ("
    "  SELECT DISTINCT ON (ta.MediaFileId) "
    "    ta.MediaFileId, ta.AudioTracksEmittedJson, ta.AudioPolicyJson "
    "  FROM TranscodeAttempts ta "
    "  WHERE ta.Success = TRUE "
    "  ORDER BY ta.MediaFileId, ta.CompletedDate DESC NULLS LAST, ta.Id DESC"
    ") "
    "SELECT DISTINCT mf.Id FROM MediaFiles mf "
    "JOIN latest_attempt la ON la.MediaFileId = mf.Id "
    "CROSS JOIN LATERAL jsonb_array_elements(COALESCE(la.AudioTracksEmittedJson, '[]'::jsonb)) AS track "
    "WHERE mf.AudioComplete = TRUE "
    "AND ABS((track->>'AchievedIntegratedLufs')::REAL - COALESCE("
    "(la.AudioPolicyJson->>'TargetIntegratedLufs')::REAL, -23.0)) > 4.0"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class ConsistencyBandDeviantWithComplete(IAudioVerticalInvariant):
    """Detects AudioComplete=true MediaFiles whose latest attempt has at least one Deviant-band track (>4 LU off target)."""

    Name = "ConsistencyBandDeviantWithComplete"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return MediaFiles.Id list for AudioComplete files that drifted out of the +/-4 LU band."""
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "ConsistencyBandDeviantWithComplete.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
