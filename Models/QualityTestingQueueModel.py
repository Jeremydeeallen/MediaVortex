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
        self.StrategyId: int = 0
        self.Status: str = "Pending"  # "Pending", "Testing", "Completed", "Skipped", "Failed"
        self.Results: List[QualityTestResultModel] = []
        self.SelectedResultId: Optional[int] = None
        self.DateCreated: Optional[datetime] = None
        self.DateCompleted: Optional[datetime] = None
        self.ErrorMessage: Optional[str] = None
    
    def ToDict(self) -> dict:
        """Convert model to dictionary for database storage."""
        return {
            'Id': self.Id,
            'TranscodeAttemptId': self.TranscodeAttemptId,
            'StrategyId': self.StrategyId,
            'Status': self.Status,
            'Results': [result.ToDict() for result in self.Results],
            'SelectedResultId': self.SelectedResultId,
            'DateCreated': self.DateCreated,
            'DateCompleted': self.DateCompleted,
            'ErrorMessage': self.ErrorMessage
        }
    
    def FromDict(self, data: dict) -> 'QualityTestingQueueModel':
        """Create model from dictionary data."""
        self.Id = data.get('Id')
        self.TranscodeAttemptId = data.get('TranscodeAttemptId', 0)
        self.StrategyId = data.get('StrategyId', 0)
        self.Status = data.get('Status', 'Pending')
        self.SelectedResultId = data.get('SelectedResultId')
        self.DateCreated = data.get('DateCreated')
        self.DateCompleted = data.get('DateCompleted')
        self.ErrorMessage = data.get('ErrorMessage')
        
        # Convert results from dict list to model list
        results_data = data.get('Results', [])
        self.Results = []
        for result_data in results_data:
            result = QualityTestResultModel()
            result.FromDict(result_data)
            self.Results.append(result)
        
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
