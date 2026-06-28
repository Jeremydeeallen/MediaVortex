from dataclasses import dataclass


@dataclass(frozen=True)
# directive: work-transcode-unified
class AdmissionResult:
    # see work-bucket.C4
    Inserted: int
    AlreadyQueued: int
    Total: int
