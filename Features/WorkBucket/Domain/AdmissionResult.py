from dataclasses import dataclass


@dataclass(frozen=True)
# directive: work-transcode-unified
class AdmissionResult:
    # see work-bucket.C4
    Inserted: int
    AlreadyQueued: int
    Total: int
    # directive: transcode-flow-canonical -- do not collapse admission-deferred / skipped / errored into AlreadyQueued; each outcome is a distinct signal
    Skipped: int = 0
    AdmissionDeferred: int = 0
    Errored: int = 0
