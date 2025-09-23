from datetime import datetime
from typing import Optional


class VMAFProgressModel:
    """Model for VMAF quality analysis progress tracking."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.VMAFQueueId: int = 0
        self.TranscodeAttemptId: int = 0
        self.Status: str = "Running"  # Running, Completed, Failed
        self.ProgressPercentage: int = 0
        self.CurrentStep: Optional[str] = None
        self.StartTime: Optional[datetime] = None
        self.EndTime: Optional[datetime] = None
        self.ETA: Optional[str] = None
        self.ErrorMessage: Optional[str] = None
        self.CreatedAt: Optional[datetime] = None
        self.UpdatedAt: Optional[datetime] = None
    
    def IsRunning(self) -> bool:
        """Check if VMAF analysis is currently running."""
        return self.Status == "Running"
    
    def IsCompleted(self) -> bool:
        """Check if VMAF analysis is completed."""
        return self.Status == "Completed"
    
    def IsFailed(self) -> bool:
        """Check if VMAF analysis failed."""
        return self.Status == "Failed"
    
    def MarkAsRunning(self, CurrentStep: str = "Initializing") -> None:
        """Mark VMAF analysis as running with current step."""
        self.Status = "Running"
        self.ProgressPercentage = 0
        self.CurrentStep = CurrentStep
        self.StartTime = datetime.now()
        self.EndTime = None
        self.ErrorMessage = None
    
    def UpdateProgress(self, ProgressPercentage: int, CurrentStep: str, ETA: str = None) -> None:
        """Update VMAF analysis progress."""
        if self.IsRunning():
            self.ProgressPercentage = max(0, min(100, ProgressPercentage))
            self.CurrentStep = CurrentStep
            if ETA:
                self.ETA = ETA
            self.UpdatedAt = datetime.now()
    
    def MarkAsCompleted(self) -> None:
        """Mark VMAF analysis as completed."""
        self.Status = "Completed"
        self.ProgressPercentage = 100
        self.CurrentStep = "Completed"
        self.EndTime = datetime.now()
        self.UpdatedAt = datetime.now()
        self.ErrorMessage = None
    
    def MarkAsFailed(self, ErrorMessage: str) -> None:
        """Mark VMAF analysis as failed with error message."""
        self.Status = "Failed"
        self.CurrentStep = "Failed"
        self.EndTime = datetime.now()
        self.UpdatedAt = datetime.now()
        self.ErrorMessage = ErrorMessage
    
    def GetDuration(self) -> Optional[float]:
        """Get duration in seconds if completed or failed."""
        if self.EndTime and self.StartTime:
            return (self.EndTime - self.StartTime).total_seconds()
        return None
    
    def GetFormattedDuration(self) -> str:
        """Get formatted duration string."""
        duration = self.GetDuration()
        if duration is None:
            return "N/A"
        
        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            return f"{hours}h {minutes}m"
