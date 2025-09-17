from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class VMAFFrameData:
    """Represents VMAF data for a single frame."""
    
    FrameNumber: int = 0
    VMAFScore: float = 0.0
    IntegerADM2: float = 0.0
    IntegerADMScale0: float = 0.0
    IntegerADMScale1: float = 0.0
    IntegerADMScale2: float = 0.0
    IntegerADMScale3: float = 0.0
    IntegerMotion2: float = 0.0
    IntegerMotion: float = 0.0
    IntegerVIFScale0: float = 0.0
    IntegerVIFScale1: float = 0.0
    IntegerVIFScale2: float = 0.0
    IntegerVIFScale3: float = 0.0


@dataclass
class VMAFPooledMetrics:
    """Represents pooled VMAF metrics across all frames."""
    
    MetricName: str = ""
    MinValue: float = 0.0
    MaxValue: float = 0.0
    MeanValue: float = 0.0
    HarmonicMean: float = 0.0


@dataclass
class FFmpegVMAFComparisonModel:
    """Represents FFmpeg VMAF comparison results."""
    
    # Source Information
    OriginalFilePath: str = ""
    TranscodedFilePath: str = ""
    OriginalFileName: str = ""
    TranscodedFileName: str = ""
    
    # VMAF Configuration
    QualityWidth: int = 1280
    QualityHeight: int = 720
    FPS: float = 0.0
    VMAFVersion: str = "3.0.0"
    
    # VMAF Results
    VMAFResultsPath: str = ""
    VMAFResultsFileName: str = ""
    OverallVMAFScore: float = 0.0
    
    # Frame Data
    FrameData: List[VMAFFrameData] = None
    TotalFrames: int = 0
    
    # Pooled Metrics
    PooledMetrics: List[VMAFPooledMetrics] = None
    
    # Generation Information
    GenerationDate: Optional[datetime] = None
    Success: bool = False
    ErrorMessage: Optional[str] = None
    
    def __post_init__(self):
        if self.FrameData is None:
            self.FrameData = []
        if self.PooledMetrics is None:
            self.PooledMetrics = []
        if self.GenerationDate is None:
            self.GenerationDate = datetime.now()
    
    def GetFullVMAFResultsPath(self) -> str:
        """Get the full path to the VMAF results file."""
        return self.VMAFResultsPath
    
    def GetAverageVMAFScore(self) -> float:
        """Calculate average VMAF score from frame data."""
        if not self.FrameData:
            return 0.0
        return sum(frame.VMAFScore for frame in self.FrameData) / len(self.FrameData)
    
    def GetVMAFScoreRange(self) -> tuple:
        """Get min and max VMAF scores from frame data."""
        if not self.FrameData:
            return (0.0, 0.0)
        scores = [frame.VMAFScore for frame in self.FrameData]
        return (min(scores), max(scores))
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert model to dictionary for JSON response."""
        return {
            'OriginalFilePath': self.OriginalFilePath,
            'TranscodedFilePath': self.TranscodedFilePath,
            'OriginalFileName': self.OriginalFileName,
            'TranscodedFileName': self.TranscodedFileName,
            'QualityWidth': self.QualityWidth,
            'QualityHeight': self.QualityHeight,
            'FPS': self.FPS,
            'VMAFVersion': self.VMAFVersion,
            'VMAFResultsPath': self.VMAFResultsPath,
            'VMAFResultsFileName': self.VMAFResultsFileName,
            'OverallVMAFScore': self.OverallVMAFScore,
            'TotalFrames': self.TotalFrames,
            'AverageVMAFScore': self.GetAverageVMAFScore(),
            'VMAFScoreRange': self.GetVMAFScoreRange(),
            'GenerationDate': self.GenerationDate,
            'Success': self.Success,
            'ErrorMessage': self.ErrorMessage
        }
