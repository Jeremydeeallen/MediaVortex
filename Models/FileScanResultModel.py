from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class FileScanResultModel:
    """Represents scan operation results."""
    
    Id: Optional[int] = None
    RootFolderId: Optional[int] = None
    ScanStartTime: Optional[datetime] = None
    ScanEndTime: Optional[datetime] = None
    TotalFilesFound: int = 0
    TotalFilesProcessed: int = 0
    TotalFilesSkipped: int = 0
    TotalFilesWithErrors: int = 0
    TotalSizeGB: float = 0.0
    ScanStatus: str = "Pending"  # Pending, InProgress, Completed, Failed, Cancelled
    ErrorMessage: Optional[str] = None
    ProcessId: Optional[int] = None
    
    def __post_init__(self):
        if self.ScanStartTime is None:
            self.ScanStartTime = datetime.now()
    
    @property
    def DurationMinutes(self) -> Optional[float]:
        """Calculate scan duration in minutes."""
        if self.ScanStartTime and self.ScanEndTime:
            duration = self.ScanEndTime - self.ScanStartTime
            return duration.total_seconds() / 60.0
        return None
    
    @property
    def IsCompleted(self) -> bool:
        """Check if scan is completed successfully."""
        return self.ScanStatus == "Completed"
    
    @property
    def HasErrors(self) -> bool:
        """Check if scan encountered any errors."""
        return self.TotalFilesWithErrors > 0 or self.ErrorMessage is not None
