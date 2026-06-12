from typing import FrozenSet, Optional, Tuple


# directive: compliance-writeback-invariant | # see compliance.C8
class ComplianceBucketResolver:
    """Pure function: map OperationsNeeded to co-mutated (IsCompliant, WorkBucket) per compliance.C8 (sole producer)."""

    # directive: compliance-writeback-invariant | # see compliance.C8
    def Resolve(self, OperationsNeeded: FrozenSet[str]) -> Tuple[bool, Optional[str]]:
        """Return (IsCompliant, WorkBucket). C3 precedence: Transcode > Remux > AudioFixOnly > SubtitleFixOnly. Empty ops -> (True, None); non-empty -> (False, Bucket). Sole producer of the (IsCompliant, WorkBucket) pair (compliance.C8)."""
        if not OperationsNeeded:
            return (True, None)
        if 'Transcode' in OperationsNeeded:
            return (False, 'Transcode')
        if 'Remux' in OperationsNeeded:
            return (False, 'Remux')
        if 'AudioFix' in OperationsNeeded:
            return (False, 'AudioFixOnly')
        if 'SubtitleFix' in OperationsNeeded:
            return (False, 'SubtitleFixOnly')
        return (True, None)
