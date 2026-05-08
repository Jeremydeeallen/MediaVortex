from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timezone


@dataclass
class FFmpegScreenshotModel:
    """Represents FFmpeg screenshot generation results."""
    
    # Source Information
    SourceFilePath: str = ""
    SourceFileName: str = ""
    
    # Screenshot Information
    ScreenshotPath: str = ""
    ScreenshotFileName: str = ""
    TimestampSeconds: float = 0.0
    Width: Optional[int] = None
    Height: Optional[int] = None
    Format: str = "jpg"  # jpg, png, etc.
    
    # Generation Information
    GenerationDate: Optional[datetime] = None
    Success: bool = False
    ErrorMessage: Optional[str] = None
    
    def __post_init__(self):
        if self.GenerationDate is None:
            self.GenerationDate = datetime.now(timezone.utc)
    
    def GetFullScreenshotPath(self) -> str:
        """Get the full path to the screenshot file."""
        return self.ScreenshotPath


@dataclass
class FFmpegScreenshotBatchModel:
    """Represents batch screenshot generation results."""
    
    # Source Information
    SourceFilePath: str = ""
    SourceFileName: str = ""
    
    # Batch Information
    Screenshots: List[FFmpegScreenshotModel] = None
    TotalScreenshots: int = 0
    SuccessfulScreenshots: int = 0
    FailedScreenshots: int = 0
    
    # Generation Information
    GenerationDate: Optional[datetime] = None
    Success: bool = False
    ErrorMessage: Optional[str] = None
    
    def __post_init__(self):
        if self.Screenshots is None:
            self.Screenshots = []
        if self.GenerationDate is None:
            self.GenerationDate = datetime.now(timezone.utc)
    
    def AddScreenshot(self, Screenshot: FFmpegScreenshotModel):
        """Add a screenshot to the batch."""
        self.Screenshots.append(Screenshot)
        self.TotalScreenshots += 1
        if Screenshot.Success:
            self.SuccessfulScreenshots += 1
        else:
            self.FailedScreenshots += 1
