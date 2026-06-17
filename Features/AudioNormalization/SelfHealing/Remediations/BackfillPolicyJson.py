from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class BackfillPolicyJson(IAudioVerticalRemediation):
    """Routes through AudioPolicyAdmissionGate.BackfillAllPending; idempotent."""

    Name = "BackfillPolicyJson"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        """Run BackfillAllPending once -- it covers every Pending row in a single UPDATE."""
        if not RowIds:
            return 0
        try:
            AudioPolicyAdmissionGate().BackfillAllPending()
            return len(RowIds)
        except Exception as Ex:
            LoggingService.LogException(
                "BackfillPolicyJson.Apply failed",
                Ex, self.Name, "Apply",
            )
            return 0
