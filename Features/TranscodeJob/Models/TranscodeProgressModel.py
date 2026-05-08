from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranscodeProgressModel:
    """Represents real-time transcoding progress using TranscodeProgress table."""
    
    Id: Optional[int] = None
    TranscodeAttemptId: int = 0
    CurrentPhase: str = "Starting"
    ProgressPercent: int = 0
    CurrentFrame: int = 0
    TotalFrameCount: int = 0
    CurrentFPS: float = 0.0
    CurrentBitrate: str = "0kbits/s"
    CurrentTime: str = "00:00:00"
    CurrentSpeed: str = "0x"
    FFmpegOutput: str = ""
    LastProgressUpdate: Optional[datetime] = None
    
    def __post_init__(self):
        if self.LastProgressUpdate is None:
            self.LastProgressUpdate = datetime.now(timezone.utc)
