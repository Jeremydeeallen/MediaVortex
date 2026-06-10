# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4

from typing import Dict, Any
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Adjustments.AdjustmentCalculator import AdjustmentCalculator
from Features.TranscodeJob.Adjustments.KnobOverrides import KnobOverrides


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
class CrfAdjustmentCalculator(AdjustmentCalculator):
    """Adjusts CRF downward based on prior VMAF gap; clamps to MinCRF floor."""

    MinCRF = 15

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def Calculate(self, PreviousAttempt: Dict[str, Any], ProfileSettings: Dict[str, Any], GateThreshold: float) -> KnobOverrides:
        """Compute next CRF by reducing previous CRF per VMAF bucket; floor at MinCRF=15."""
        PreviousCrf = PreviousAttempt['Quality']
        VmafScore = PreviousAttempt['VMAF']

        if VmafScore < 50:
            Adjustment = 4
            Reason = "VMAF < 50"
        elif VmafScore < 61:
            Adjustment = 3
            Reason = "VMAF 50-60"
        elif VmafScore < 71:
            Adjustment = 2
            Reason = "VMAF 61-70"
        elif VmafScore < 80:
            Adjustment = 1
            Reason = "VMAF 71-79"
        else:
            Adjustment = 1
            Reason = "VMAF >= 80 (should not retranscode)"
            LoggingService.LogWarning(f"CrfAdjustmentCalculator called with VMAF >= 80 ({VmafScore}). Should skip retranscode.", "CrfAdjustmentCalculator", "Calculate")

        NewCrf = PreviousCrf - Adjustment

        if NewCrf < self.MinCRF:
            LoggingService.LogWarning(f"Calculated CRF {NewCrf} is below minimum {self.MinCRF}, enforcing minimum", "CrfAdjustmentCalculator", "Calculate")
            NewCrf = self.MinCRF

        LoggingService.LogInfo(f"CRF adjustment: {PreviousCrf} -> {NewCrf} (adjustment: -{Adjustment}, reason: {Reason}, VMAF: {VmafScore:.2f})", "CrfAdjustmentCalculator", "Calculate")

        return KnobOverrides(CRF=NewCrf, BitrateKbps=None, MaxrateKbps=None)
