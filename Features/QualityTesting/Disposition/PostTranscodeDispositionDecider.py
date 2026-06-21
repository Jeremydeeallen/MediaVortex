from typing import Dict, Any
from Features.QualityTesting.Disposition.Disposition import Disposition


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
class PostTranscodeDispositionDecider:
    """Pure-function decider: given a transcode attempt + gate config, returns a Disposition."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C5
    def Decide(self, Attempt: Dict[str, Any], GateConfig: Dict[str, Any]) -> Disposition:
        """Return the Disposition for a completed transcode attempt under the given gate config."""
        Success = bool(Attempt.get('Success'))
        if not Success:
            return Disposition(Action='Discard', Reason='TranscodeFailed')

        if not bool(Attempt.get('QualityTestRequired')):
            return Disposition(Action='BypassReplace', Reason='QualityTestNotRequired')

        OldSize = Attempt.get('OldSize') or 0
        NewSize = Attempt.get('NewSize') or 0
        if NewSize and OldSize and NewSize >= OldSize:
            return Disposition(Action='Discard', Reason='NoSavings')

        if not GateConfig.get('QualityTestEnabled', True):
            return Disposition(Action='BypassReplace', Reason='QualityTestingGloballyDisabled')

        VmafScore = Attempt.get('VmafScore')
        if VmafScore is not None:
            try:
                Score = float(VmafScore)
            except (TypeError, ValueError):
                Score = None
            if Score is not None:
                MinThreshold = float(GateConfig.get('VmafAutoReplaceMinThreshold', 80.0))
                MaxThreshold = float(GateConfig.get('VmafAutoReplaceMaxThreshold', 97.0))
                if Score < MinThreshold:
                    return Disposition(Action='Requeue', Reason='VmafBelowMin')
                if Score <= MaxThreshold:
                    return Disposition(Action='Replace', Reason='VmafPassed')
                return Disposition(Action='NoReplace', Reason='VmafAboveMax')

        return Disposition(Action='Pending', Reason='AwaitingVmaf')
