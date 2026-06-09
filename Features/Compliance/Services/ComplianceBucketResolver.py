from typing import FrozenSet, Optional


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C14
class ComplianceBucketResolver:
    """Pure function: map OperationsNeeded set to a single WorkBucket -- see compliance-solid-refactor.C14 for precedence rules."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C14
    def Resolve(self, OperationsNeeded: FrozenSet[str]) -> Optional[str]:
        """Return 'Transcode' / 'Remux' / 'AudioFixOnly' / 'SubtitleFixOnly' / None per C14 precedence."""
        if not OperationsNeeded:
            return None
        if 'Transcode' in OperationsNeeded:
            return 'Transcode'
        if 'Remux' in OperationsNeeded:
            return 'Remux'
        if 'AudioFix' in OperationsNeeded:
            return 'AudioFixOnly'
        if 'SubtitleFix' in OperationsNeeded:
            return 'SubtitleFixOnly'
        return None
