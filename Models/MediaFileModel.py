from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MediaFileModel:
    """Represents individual media files with metadata."""
    
    Id: Optional[int] = None
    SeasonId: Optional[int] = None
    FilePath: str = ""
    FileName: str = ""
    SizeMB: float = 0.0
    VideoBitrateKbps: Optional[int] = None
    AudioBitrateKbps: Optional[int] = None
    Resolution: Optional[str] = None
    Codec: Optional[str] = None
    DurationMinutes: Optional[float] = None
    FrameRate: Optional[float] = None
    LastScannedDate: Optional[datetime] = None
    CompressionPotential: Optional[str] = None
    AssignedProfile: Optional[str] = None
    IsInterlaced: Optional[bool] = None
    ResolutionCategory: Optional[str] = None
    FileModificationTime: Optional[datetime] = None
    
    
    def __post_init__(self):
        if self.LastScannedDate is None:
            self.LastScannedDate = datetime.now()
