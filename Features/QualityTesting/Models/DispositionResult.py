from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DispositionResult:
    """Output of DecidePostTranscodeDisposition.

    Disposition is one of: Pending, Replace, BypassReplace, NoReplace, Requeue, Discard.
    Reason is from a closed enum (see post-transcode-disposition.feature.md criterion 10).
    AuditPayload captures the input values the decision was made from -- written to
    Logs.AdditionalData on the single rolled-up INFO line per decision.
    """
    Disposition: str = "Pending"
    Reason: str = ""
    AuditPayload: Dict[str, Any] = field(default_factory=dict)
