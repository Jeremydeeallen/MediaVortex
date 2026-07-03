from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DispositionResult:
    """Output of DecidePostTranscodeDisposition. Disposition is one of: Pending, Replace, Reject, NoReplace, Requeue, Discard."""
    Disposition: str = "Pending"
    Reason: str = ""
    AuditPayload: Dict[str, Any] = field(default_factory=dict)
