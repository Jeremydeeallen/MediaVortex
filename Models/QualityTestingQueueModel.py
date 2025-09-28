"""
Quality Testing Queue Model
Represents quality testing queue management and status tracking.
"""

from typing import Optional, List
from datetime import datetime
from Models.QualityTestResultModel import QualityTestResultModel


class QualityTestingQueueModel:
    """Model for quality testing queue management."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.TranscodeAttemptId: int = 0
        self.OriginalFilePath: Optional[str] = None
        self.TranscodedFilePath: Optional[str] = None
        self.FileName: Optional[str] = None
        self.Status: str = "Pending"  # "Pending", "Testing", "Completed", "Skipped", "Failed"
        self.Priority: int = 50
        self.DateAdded: Optional[datetime] = None
        self.DateStarted: Optional[datetime] = None
        self.DateCompleted: Optional[datetime] = None
        self.QualityThreshold: float = 90.0
        self.StrategyType: str = "Single"  # "Single", "Multi", "Custom", "Skip"
        self.VMAFScore: Optional[float] = None
        self.Results: Optional[str] = None  # JSON string of results
        self.RetryCount: int = 0
        self.MaxRetries: int = 3
        self.ErrorMessage: Optional[str] = None
        # Legacy attributes for compatibility
        self.StrategyId: int = 0
        self.SelectedResultId: Optional[int] = None
        self.DateCreated: Optional[datetime] = None
    
    def ToDict(self) -> dict:
        """Convert model to dictionary for database storage."""
        return {
            'Id': self.Id,
            'TranscodeAttemptId': self.TranscodeAttemptId,
            'OriginalFilePath': self.OriginalFilePath,
            'TranscodedFilePath': self.TranscodedFilePath,
            'FileName': self.FileName,
            'Status': self.Status,
            'Priority': self.Priority,
            'DateAdded': self.DateAdded,
            'DateStarted': self.DateStarted,
            'DateCompleted': self.DateCompleted,
            'QualityThreshold': self.QualityThreshold,
            'StrategyType': self.StrategyType,
            'VMAFScore': self.VMAFScore,
            'Results': self.Results,
            'RetryCount': self.RetryCount,
            'MaxRetries': self.MaxRetries,
            'ErrorMessage': self.ErrorMessage,
            # Legacy attributes
            'StrategyId': self.StrategyId,
            'SelectedResultId': self.SelectedResultId,
            'DateCreated': self.DateCreated
        }
    
    def FromDict(self, data: dict) -> 'QualityTestingQueueModel':
        """Create model from dictionary data."""
        self.Id = data.get('Id')
        self.TranscodeAttemptId = data.get('TranscodeAttemptId', 0)
        self.OriginalFilePath = data.get('OriginalFilePath')
        self.TranscodedFilePath = data.get('TranscodedFilePath')
        self.FileName = data.get('FileName')
        self.Status = data.get('Status', 'Pending')
        self.Priority = data.get('Priority', 50)
        self.DateAdded = data.get('DateAdded')
        self.DateStarted = data.get('DateStarted')
        self.DateCompleted = data.get('DateCompleted')
        self.QualityThreshold = data.get('QualityThreshold', 90.0)
        self.StrategyType = data.get('StrategyType', 'Single')
        self.VMAFScore = data.get('VMAFScore')
        self.Results = data.get('Results')
        self.RetryCount = data.get('RetryCount', 0)
        self.MaxRetries = data.get('MaxRetries', 3)
        self.ErrorMessage = data.get('ErrorMessage')
        # Legacy attributes
        self.StrategyId = data.get('StrategyId', 0)
        self.SelectedResultId = data.get('SelectedResultId')
        self.DateCreated = data.get('DateCreated')
        
        return self
    
    def IsPending(self) -> bool:
        """Check if the quality test is pending."""
        return self.Status == "Pending"
    
    def IsTesting(self) -> bool:
        """Check if the quality test is currently running."""
        return self.Status == "Testing"
    
    def IsCompleted(self) -> bool:
        """Check if the quality test is completed."""
        return self.Status == "Completed"
    
    def IsSkipped(self) -> bool:
        """Check if the quality test was skipped."""
        return self.Status == "Skipped"
    
    def IsFailed(self) -> bool:
        """Check if the quality test failed."""
        return self.Status == "Failed"
    
    def MarkAsTesting(self) -> None:
        """Mark the quality test as currently testing."""
        self.Status = "Testing"
    
    def MarkAsCompleted(self, selectedResultId: Optional[int] = None) -> None:
        """Mark the quality test as completed."""
        self.Status = "Completed"
        self.SelectedResultId = selectedResultId
        self.DateCompleted = datetime.now()
    
    def MarkAsSkipped(self) -> None:
        """Mark the quality test as skipped."""
        self.Status = "Skipped"
        self.DateCompleted = datetime.now()
    
    def MarkAsFailed(self, errorMessage: str) -> None:
        """Mark the quality test as failed."""
        self.Status = "Failed"
        self.ErrorMessage = errorMessage
        self.DateCompleted = datetime.now()
    
    def GetResultCount(self) -> int:
        """Get the number of test results."""
        return len(self.Results)
    
    def GetPassingResults(self) -> List[QualityTestResultModel]:
        """Get all results that pass the threshold."""
        return [result for result in self.Results if result.PassesThreshold]
    
    def GetBestResult(self) -> Optional[QualityTestResultModel]:
        """Get the best result (highest VMAF score)."""
        if not self.Results:
            return None
        return max(self.Results, key=lambda x: x.VMAFScore)
    
    def GetSelectedResult(self) -> Optional[QualityTestResultModel]:
        """Get the selected result."""
        if not self.SelectedResultId:
            return None
        return next((result for result in self.Results if result.Id == self.SelectedResultId), None)
    
    def GetProcessingDuration(self) -> Optional[float]:
        """Get the processing duration in seconds."""
        if not self.DateCreated or not self.DateCompleted:
            return None
        
        duration = self.DateCompleted - self.DateCreated
        return duration.total_seconds()
    
    def Validate(self) -> List[str]:
        """Validate the quality testing queue data."""
        errors = []
        
        if not self.TranscodeAttemptId or self.TranscodeAttemptId <= 0:
            errors.append("TranscodeAttemptId is required and must be greater than 0")
        
        if not self.StrategyId or self.StrategyId <= 0:
            errors.append("StrategyId is required and must be greater than 0")
        
        if self.Status not in ["Pending", "Testing", "Completed", "Skipped", "Failed"]:
            errors.append("Status must be one of: Pending, Testing, Completed, Skipped, Failed")
        
        if self.IsCompleted() and not self.Results:
            errors.append("Completed tests must have at least one result")
        
        if self.IsFailed() and not self.ErrorMessage:
            errors.append("Failed tests must have an error message")
        
        return errors
