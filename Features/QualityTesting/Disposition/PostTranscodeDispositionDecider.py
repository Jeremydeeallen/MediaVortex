from typing import Any, Dict, Optional

from Features.QualityTesting.Disposition.Disposition import Disposition


# directive: transcode-flow-canonical | # see transcode.ST7
class PostTranscodeDispositionDecider:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def __init__(self, SmartConfidenceRepo=None):
        self.SmartConfidenceRepo = SmartConfidenceRepo

    # directive: transcode-flow-canonical | # see transcode.ST7
    def Decide(self, Attempt: Dict[str, Any], GateConfig: Dict[str, Any]) -> Disposition:
        Success = bool(Attempt.get('Success'))
        if not Success:
            return Disposition(Action='Reject', Reason='TranscodeFailed')

        OldSize = Attempt.get('OldSize') or 0
        NewSize = Attempt.get('NewSize') or 0
        if NewSize and OldSize and NewSize >= OldSize:
            return Disposition(Action='Reject', Reason='NoSavings')

        # C16 restore: global QualityTestEnabled=False short-circuits to Replace regardless of per-attempt flag
        if not self._QualityTestGloballyEnabled(GateConfig):
            return Disposition(Action='Replace', Reason='QualityTestingGloballyDisabled')

        if not bool(Attempt.get('QualityTestRequired')):
            return Disposition(Action='Replace', Reason='QualityTestNotRequired')

        VmafScore = self._ParseFloat(Attempt.get('VmafScore'))
        if VmafScore is not None:
            MinThreshold = float(GateConfig.get('VmafAutoReplaceMinThreshold', 80.0))
            MaxThreshold = float(GateConfig.get('VmafAutoReplaceMaxThreshold', 97.0))
            if VmafScore < MinThreshold:
                return Disposition(Action='Requeue', Reason='VmafBelowMin')
            if VmafScore <= MaxThreshold:
                return Disposition(Action='Replace', Reason='VmafPassed')
            return Disposition(Action='Reject', Reason='VmafAboveMax')

        # C14 SmartConfidenceSkip: consult rolling bucket stats before falling through to VMAF admission
        SmartSkip = self._MaybeSmartConfidenceSkip(Attempt, GateConfig)
        if SmartSkip is not None:
            return SmartSkip

        return Disposition(Action='Pending', Reason='AwaitingVmaf')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _QualityTestGloballyEnabled(self, GateConfig: Dict[str, Any]) -> bool:
        Value = GateConfig.get('QualityTestEnabled')
        if Value is None:
            return True
        return bool(Value)

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _MaybeSmartConfidenceSkip(self, Attempt: Dict[str, Any], GateConfig: Dict[str, Any]) -> Optional[Disposition]:
        if self.SmartConfidenceRepo is None:
            return None
        BucketKey = Attempt.get('BucketKey')
        if BucketKey is None:
            return None
        Stats = self.SmartConfidenceRepo.LookupBucket(BucketKey)
        MinCount = int(GateConfig.get('MinConfidenceSampleCount', 10))
        MinRate = float(GateConfig.get('MinConfidencePassRate', 0.95))
        Sigma = float(GateConfig.get('SigmaMargin', 2.0))
        MinThreshold = float(GateConfig.get('VmafAutoReplaceMinThreshold', 80.0))
        if Stats.SampleCount < MinCount:
            return None
        if Stats.PassRate is None or Stats.PassRate < MinRate:
            return None
        if Stats.VmafMean is None or Stats.VmafStdDev is None:
            return None
        LowerBound = Stats.VmafMean - Sigma * Stats.VmafStdDev
        if LowerBound < MinThreshold:
            return None
        return Disposition(Action='Replace', Reason='QualityTestConfident')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _ParseFloat(self, Value) -> Optional[float]:
        if Value is None:
            return None
        try:
            return float(Value)
        except (TypeError, ValueError):
            return None
