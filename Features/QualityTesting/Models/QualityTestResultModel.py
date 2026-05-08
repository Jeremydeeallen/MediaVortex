from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class QualityTestResultModel:
    """Represents quality test results using QualityTestResults table."""

    Id: Optional[int] = None
    TranscodeAttemptId: int = 0
    VMAFScore: Optional[float] = None
    TestDuration: Optional[float] = None
    PassesThreshold: Optional[bool] = None
    Rank: Optional[int] = None
    ErrorMessage: Optional[str] = None
    DateTested: Optional[datetime] = None
    FFmpegCommand: Optional[str] = None
    Status: str = "Running"  # Running, Success, Failed

    def __post_init__(self):
        if self.DateTested is None:
            self.DateTested = datetime.now(timezone.utc)

    @property
    def FileSizeMB(self) -> float:
        """Get file size in MB."""
        return self.FileSize / (1024 * 1024) if self.FileSize > 0 else 0.0

    @property
    def FileSizeGB(self) -> float:
        """Get file size in GB."""
        return self.FileSize / (1024 * 1024 * 1024) if self.FileSize > 0 else 0.0

    @property
    def IsSuccess(self) -> bool:
        """Check if the quality test was successful."""
        return self.Status == "Success" and self.VMAFScore is not None

    @property
    def IsFailed(self) -> bool:
        """Check if the quality test failed."""
        return self.Status == "Failed" or (self.ErrorMessage is not None and self.ErrorMessage != "")

    @property
    def IsRunning(self) -> bool:
        """Check if the quality test is still running."""
        return self.Status == "Running"
