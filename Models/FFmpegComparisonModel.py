from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class FFmpegComparisonModel:
    """Represents FFmpeg video comparison results."""
    
    # Source Information
    OriginalFilePath: str = ""
    TranscodedFilePath: str = ""
    OriginalFileName: str = ""
    TranscodedFileName: str = ""
    
    # Comparison Information
    ComparisonVideoPath: str = ""
    ComparisonVideoFileName: str = ""
    ComparisonType: str = "side_by_side"  # side_by_side, picture_in_picture, overlay
    Width: Optional[int] = None
    Height: Optional[int] = None
    DurationSeconds: Optional[float] = None
    
    # Generation Information
    GenerationDate: Optional[datetime] = None
    Success: bool = False
    ErrorMessage: Optional[str] = None
    
    def __post_init__(self):
        if self.GenerationDate is None:
            self.GenerationDate = datetime.now()
    
    def GetFullComparisonPath(self) -> str:
        """Get the full path to the comparison video file."""
        return self.ComparisonVideoPath
