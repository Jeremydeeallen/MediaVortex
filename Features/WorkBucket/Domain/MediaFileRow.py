from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
# directive: work-transcode-unified
class MediaFileRow:
    """A single file row inside an expanded series."""

    Id: int
    FileName: str
    SizeGB: float
    Resolution: Optional[str]
    AudioCodec: Optional[str]
    AudioLanguages: Optional[str]
    VideoCompliantReason: Optional[str]
    ContainerCompliantReason: Optional[str]
    AudioCompliantReason: Optional[str]
    InQueue: bool

    # directive: work-transcode-unified
    def ToJson(self) -> dict:
        """JSON projection for /api/Work/<bucket>/Series/<sid>."""
        # see work-bucket.C2
        return {
            'Id': self.Id,
            'FileName': self.FileName,
            'SizeGB': self.SizeGB,
            'Resolution': self.Resolution,
            'AudioCodec': self.AudioCodec,
            'AudioLanguages': self.AudioLanguages,
            'VideoCompliantReason': self.VideoCompliantReason,
            'ContainerCompliantReason': self.ContainerCompliantReason,
            'AudioCompliantReason': self.AudioCompliantReason,
            'InQueue': self.InQueue,
        }
