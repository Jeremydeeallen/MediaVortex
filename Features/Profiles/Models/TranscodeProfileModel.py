from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TranscodeProfileModel:
    """Represents a transcoding profile with its settings."""
    
    Id: Optional[int] = None
    ProfileName: str = ""
    Description: str = ""
    CreatedDate: Optional[datetime] = None
    LastModified: Optional[datetime] = None
    
    # Profile-level FFmpeg settings (apply to all resolutions)
    Codec: str = "libsvtav1"  # Video codec (libsvtav1, libx265, libx264, libvpx-vp9)
    Preset: int = 6  # Encoding preset (0-13, higher = slower but better quality)
    FilmGrain: int = 10  # Film grain level (0-50, 0=off)
    YadifMode: int = 1  # Deinterlacing mode (0=off, 1=on, 2=spatial, 3=temporal)
    YadifParity: int = 1  # Deinterlacing parity (0=auto, 1=top, -1=bottom)
    YadifDeint: int = 1  # Deinterlacing type (0=all, 1=interlaced)
    UseNvidiaHardware: int = 0  # 0=software, 1=NVIDIA hardware
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now()
        if self.LastModified is None:
            self.LastModified = datetime.now()
