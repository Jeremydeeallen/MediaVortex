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
    
    # New metadata fields
    TotalFrames: Optional[int] = None
    CodecProfile: Optional[str] = None
    ColorRange: Optional[str] = None
    FieldOrder: Optional[str] = None
    HasBFrames: Optional[int] = None
    RefFrames: Optional[int] = None
    PixelFormat: Optional[str] = None
    Level: Optional[int] = None
    AudioChannels: Optional[int] = None
    AudioSampleRate: Optional[int] = None
    AudioSampleFormat: Optional[str] = None
    AudioChannelLayout: Optional[str] = None
    ContainerFormat: Optional[str] = None
    OverallBitrate: Optional[int] = None
    TranscodedByMediaVortex: Optional[bool] = None
    
    def __post_init__(self):
        if self.LastScannedDate is None:
            self.LastScannedDate = datetime.now()
