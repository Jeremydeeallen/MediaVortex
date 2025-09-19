from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TranscodeFileModel:
    """Represents overall transcoding status using TranscodeFiles table."""
    
    Id: Optional[int] = None
    FilePath: str = ""
    AllQualitiesFailed: bool = False
    SuccessfullyTranscoded: bool = False
    FirstAttemptDate: Optional[datetime] = None
    LastAttemptDate: Optional[datetime] = None
    SuccessDate: Optional[datetime] = None
    FinalQuality: Optional[int] = None
    FinalSizeBytes: Optional[int] = None
    TotalAttempts: int = 0
    OriginalFilePath: Optional[str] = None
    FinalFilePath: Optional[str] = None
    
    def __post_init__(self):
        if self.OriginalFilePath is None:
            self.OriginalFilePath = self.FilePath
    
    @property
    def FinalSizeMB(self) -> float:
        """Get final transcoded file size in MB."""
        return self.FinalSizeBytes / (1024 * 1024) if self.FinalSizeBytes else 0.0
    
    @property
    def FinalSizeGB(self) -> float:
        """Get final transcoded file size in GB."""
        return self.FinalSizeBytes / (1024 * 1024 * 1024) if self.FinalSizeBytes else 0.0
    
    @property
    def IsTranscodingComplete(self) -> bool:
        """Check if transcoding is complete (success or all qualities failed)."""
        return self.SuccessfullyTranscoded or self.AllQualitiesFailed
    
    @property
    def HasSuccessfulTranscode(self) -> bool:
        """Check if there was a successful transcoding attempt."""
        return self.SuccessfullyTranscoded and self.SuccessDate is not None
    
    @property
    def ProcessingDurationDays(self) -> Optional[float]:
        """Calculate total processing duration in days."""
        if self.FirstAttemptDate and self.LastAttemptDate:
            duration = self.LastAttemptDate - self.FirstAttemptDate
            return duration.total_seconds() / (24 * 3600)
        return None
    
    @property
    def SuccessDurationDays(self) -> Optional[float]:
        """Calculate time to success in days."""
        if self.FirstAttemptDate and self.SuccessDate:
            duration = self.SuccessDate - self.FirstAttemptDate
            return duration.total_seconds() / (24 * 3600)
        return None
    
    @property
    def AverageAttemptsPerDay(self) -> Optional[float]:
        """Calculate average attempts per day."""
        if self.ProcessingDurationDays and self.ProcessingDurationDays > 0:
            return self.TotalAttempts / self.ProcessingDurationDays
        return None
    
    @property
    def IsStuck(self) -> bool:
        """Check if file appears to be stuck (many attempts, no success)."""
        return (self.TotalAttempts >= 5 and 
                not self.SuccessfullyTranscoded and 
                not self.AllQualitiesFailed)
    
    @property
    def NeedsAttention(self) -> bool:
        """Check if file needs manual attention."""
        return (self.IsStuck or 
                (self.AllQualitiesFailed and self.TotalAttempts > 0) or
                (self.ProcessingDurationDays and self.ProcessingDurationDays > 7))
