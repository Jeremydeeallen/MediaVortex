from dataclasses import dataclass


@dataclass(frozen=True)
# directive: work-transcode-unified | # see work-bucket.C5
class AdmitOneResult:
    """Result of a single-row admission to TranscodeQueue."""

    Status: str
    QueueId: int
