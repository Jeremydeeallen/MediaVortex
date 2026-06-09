from typing import List, Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
class ComplianceGateChain:
    """Applies the registered gates in order; first failing gate short-circuits and names the block."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def __init__(self, Gates: List[IComplianceGate]):
        self.Gates = Gates

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def Apply(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile], GatesConfig: ComplianceGatesModel) -> Optional[str]:
        """Return the Name of the first enabled gate that blocks, or None if all gates pass (compliance evaluation proceeds)."""
        for Gate in self.Gates:
            if not Gate.IsEnabled(GatesConfig):
                continue
            if Gate.Blocks(Mf, Profile):
                return Gate.Name
        return None
