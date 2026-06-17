from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation
from Features.AudioNormalization.Services.AudioRemeasurementService import (
    AudioRemeasurementService,
    REASON_INVALID_LOUDNESS,
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class EnqueueRemeasurement(IAudioVerticalRemediation):
    """Calls AudioRemeasurementService.MarkForRemeasurement for each offending MediaFileId."""

    Name = "EnqueueRemeasurement"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def __init__(self, Service=None):
        """Inject service for tests; default-construct AudioRemeasurementService."""
        self._Service = Service

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        """Mark each MediaFile for re-measurement; idempotent under the existing SQL guard."""
        if not RowIds:
            return 0
        Svc = self._Service or AudioRemeasurementService()
        Ok = 0
        for MediaFileId in RowIds:
            try:
                Svc.MarkForRemeasurement(MediaFileId, REASON_INVALID_LOUDNESS)
                Ok += 1
            except Exception as Ex:
                LoggingService.LogException(
                    f"EnqueueRemeasurement.Apply failed for MediaFileId={MediaFileId}",
                    Ex, self.Name, "Apply",
                )
        return Ok
