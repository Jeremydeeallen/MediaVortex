from datetime import datetime
from typing import Optional


class VMAFQueueModel:
    """Model for VMAF quality analysis queue items."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.TranscodeAttemptId: int = 0
        self.OriginalFilePath: str = ""
        self.TranscodedFilePath: str = ""
        self.FileName: str = ""
        self.Status: str = "Pending"  # Pending, Running, Completed, Failed
        self.Priority: int = 0
        self.DateAdded: Optional[datetime] = None
        self.DateStarted: Optional[datetime] = None
        self.DateCompleted: Optional[datetime] = None
        self.VMAFScore: Optional[float] = None
        self.QualityThreshold: float = 90.0
        self.ErrorMessage: Optional[str] = None
        self.RetryCount: int = 0
        self.MaxRetries: int = 3
    
    def IsCompleted(self) -> bool:
        """Check if VMAF analysis is completed."""
        return self.Status == "Completed"
    
    def IsFailed(self) -> bool:
        """Check if VMAF analysis failed."""
        return self.Status == "Failed"
    
    def IsRunning(self) -> bool:
        """Check if VMAF analysis is currently running."""
        return self.Status == "Running"
    
    def IsPending(self) -> bool:
        """Check if VMAF analysis is pending."""
        return self.Status == "Pending"
    
    def CanRetry(self) -> bool:
        """Check if VMAF analysis can be retried."""
        return self.RetryCount < self.MaxRetries and self.IsFailed()
    
    def MarkAsRunning(self) -> None:
        """Mark VMAF analysis as running."""
        self.Status = "Running"
        self.DateStarted = datetime.now()
    
    def MarkAsCompleted(self, VMAFScore: float) -> None:
        """Mark VMAF analysis as completed with score."""
        self.Status = "Completed"
        self.VMAFScore = VMAFScore
        self.DateCompleted = datetime.now()
    
    def MarkAsFailed(self, ErrorMessage: str) -> None:
        """Mark VMAF analysis as failed with error message."""
        self.Status = "Failed"
        self.ErrorMessage = ErrorMessage
        self.RetryCount += 1
        self.DateCompleted = datetime.now()
    
    def PassesQualityThreshold(self) -> bool:
        """Check if VMAF score passes quality threshold."""
        if self.VMAFScore is None:
            return False
        return self.VMAFScore >= self.QualityThreshold
