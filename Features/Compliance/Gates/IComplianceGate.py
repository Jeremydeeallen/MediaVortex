from abc import ABC, abstractmethod
from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
class IComplianceGate(ABC):
    """Abstract gate -- one impl per hard-block rule; first failing gate short-circuits compliance evaluation."""

    Name: str = ""

    @abstractmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        """Read the corresponding flag on the ComplianceGates row; operator can disable any gate."""

    @abstractmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        """Return True iff this gate would block the MediaFile (engine returns ComplianceDecision with GateBlocked=self.Name)."""
