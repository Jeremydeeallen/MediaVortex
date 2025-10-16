from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TranscodeAttemptModel:
    """Represents individual transcoding attempts using TranscodeAttempts table."""
    
    Id: Optional[int] = None
    FilePath: str = ""
    AttemptDate: Optional[datetime] = None
    Quality: int = 0
    OldSizeBytes: int = 0
    NewSizeBytes: int = 0
    Success: Optional[bool] = None
    SizeReductionBytes: int = 0
    SizeReductionPercent: float = 0.0
    ErrorMessage: Optional[str] = None
    TranscodeDurationSeconds: float = 0.0
    FfpmpegCommand: Optional[str] = None
    AudioBitrateKbps: Optional[int] = None
    VideoBitrateKbps: Optional[int] = None
    ProfileName: Optional[str] = None
    VMAF: Optional[float] = None
    QualityTestRequired: int = 1  # Default to 1 (required)
    QualityTestCompleted: int = 0  # Default to 0 (not completed)
    FileReplaced: bool = False
    FileReplacedDate: Optional[datetime] = None
    ReplacementType: Optional[str] = None
    
    def __post_init__(self):
        if self.AttemptDate is None:
            self.AttemptDate = datetime.now()
    
    @property
    def OldSizeMB(self) -> float:
        """Get original file size in MB."""
        return self.OldSizeBytes / (1024 * 1024) if self.OldSizeBytes > 0 else 0.0
    
    @property
    def NewSizeMB(self) -> float:
        """Get transcoded file size in MB."""
        return self.NewSizeBytes / (1024 * 1024) if self.NewSizeBytes > 0 else 0.0
    
    @property
    def OldSizeGB(self) -> float:
        """Get original file size in GB."""
        return self.OldSizeBytes / (1024 * 1024 * 1024) if self.OldSizeBytes > 0 else 0.0
    
    @property
    def NewSizeGB(self) -> float:
        """Get transcoded file size in GB."""
        return self.NewSizeBytes / (1024 * 1024 * 1024) if self.NewSizeBytes > 0 else 0.0
    
    @property
    def CompressionRatio(self) -> float:
        """Calculate compression ratio (original/new)."""
        if self.NewSizeBytes > 0 and self.OldSizeBytes > 0:
            return self.OldSizeBytes / self.NewSizeBytes
        return 0.0
    
    @property
    def IsCompressed(self) -> bool:
        """Check if file was compressed (smaller than original)."""
        return self.NewSizeBytes < self.OldSizeBytes
    
    @property
    def TranscodeDurationMinutes(self) -> float:
        """Get transcoding duration in minutes."""
        return self.TranscodeDurationSeconds / 60.0 if self.TranscodeDurationSeconds > 0 else 0.0
    
    @property
    def VMAFQualityRating(self) -> str:
        """Get VMAF quality rating as a descriptive string."""
        if self.VMAF is None:
            return "Not measured"
        elif self.VMAF >= 90:
            return "Excellent"
        elif self.VMAF >= 80:
            return "Good"
        elif self.VMAF >= 70:
            return "Fair"
        elif self.VMAF >= 60:
            return "Poor"
        else:
            return "Very Poor"
    
    def CalculateSizeReduction(self):
        """Calculate size reduction metrics."""
        if self.OldSizeBytes > 0 and self.NewSizeBytes > 0:
            self.SizeReductionBytes = self.OldSizeBytes - self.NewSizeBytes
            self.SizeReductionPercent = (self.SizeReductionBytes / self.OldSizeBytes) * 100.0
        else:
            self.SizeReductionBytes = 0
            self.SizeReductionPercent = 0.0
