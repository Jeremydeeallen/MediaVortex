from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class AlertOperatorReview(IAudioVerticalRemediation):
    """Logs a warning naming the offending MediaFileIds so the operator can investigate via the Review tab."""

    Name = "AlertOperatorReview"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        """Emit a single WARNING summarizing the count + first 10 ids; return the count of alerts (always RowIds count)."""
        if not RowIds:
            return 0
        Preview = ', '.join(str(I) for I in RowIds[:10])
        Suffix = '' if len(RowIds) <= 10 else f' ... +{len(RowIds) - 10} more'
        LoggingService.LogWarning(
            f"Stale operator-review queue: {len(RowIds)} files held >30d. Ids: {Preview}{Suffix}",
            self.Name, "Apply",
        )
        return len(RowIds)
