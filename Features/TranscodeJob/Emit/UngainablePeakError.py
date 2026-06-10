from typing import Optional


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
class UngainablePeakError(RuntimeError):
    """Raised when source loudness measurements imply a fixed-gain encode would clip; caller defers disposition rather than crashing the job."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C6
    def __init__(self, MediaFileId: Optional[int], SourceIntegratedLufs: float, Gain: float, PredictedPeak: float, TargetTp: float):
        """Stash diagnostic context; format the message in the same shape as the legacy RuntimeError so log greps still find it."""
        Msg = (
            f"BuildAudioFilters: ungainable peak for MediaFileId={MediaFileId} "
            f"(SourceIntegratedLufs={SourceIntegratedLufs:.2f}, gain={Gain:+.2f} dB, "
            f"predicted_peak={PredictedPeak:+.2f} dBTP > target_TP={TargetTp} dBTP). "
            f"The admission gate in QueueManagementBusinessService should have deferred "
            f"this file with AdmissionDeferReason='ungainable_peak'. "
            f"linear-loudnorm.feature.md: 'Linear or refused -- never quietly different.'"
        )
        super().__init__(Msg)
        self.MediaFileId = MediaFileId
        self.SourceIntegratedLufs = SourceIntegratedLufs
        self.Gain = Gain
        self.PredictedPeak = PredictedPeak
        self.TargetTp = TargetTp
