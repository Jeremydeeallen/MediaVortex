from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: transcode-flow-canonical -- SSOT remediation for NULL compliance flags; calls the same RecomputeForFiles bulk path used by scan / post-transcode / config-change so behaviour is byte-identical
class RecomputeCompliance(IAudioVerticalRemediation):

    Name = "RecomputeCompliance"

    def Apply(self, RowIds):
        if not RowIds:
            return 0
        try:
            QueueManagementBusinessService().RecomputeForFiles(list(RowIds))
            return len(RowIds)
        except Exception as Ex:
            LoggingService.LogException("RecomputeCompliance.Apply failed", Ex, self.Name, "Apply")
            return 0
