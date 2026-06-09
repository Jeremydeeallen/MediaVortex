from abc import ABC, abstractmethod
from typing import Any
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
class IComplianceOperation(ABC):
    """Abstract operation -- one impl per operation name; ISP/LSP-compatible with ComplianceRuleEngine."""

    Name: str = ""

    @abstractmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: Any) -> OperationResult:
        """Decide whether this operation applies; return OperationResult with Applies + structured Reasons."""
