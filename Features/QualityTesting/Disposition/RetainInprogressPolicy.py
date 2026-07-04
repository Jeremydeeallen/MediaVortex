# directive: transcode-flow-canonical | # see transcode.ST7
from typing import Set


# directive: transcode-flow-canonical | # see transcode.ST7
class RetainInprogressPolicy:
    """Reason -> RetainInprogress mapping. Operator-hold semantics decoupled from Disposition value object."""

    RETAIN_REASONS: Set[str] = frozenset({
        'TestMode',
    })

    # directive: transcode-flow-canonical | # see transcode.ST7
    def ShouldRetain(self, Reason: str) -> bool:
        """True iff the .inprogress artifact should stay on disk for operator inspection."""
        return Reason in self.RETAIN_REASONS
