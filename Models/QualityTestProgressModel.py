"""
QualityTestProgressModel
Data model for quality testing progress tracking.
"""

from typing import Optional, Dict, Any
from datetime import datetime


class QualityTestProgressModel:
    """Data model for quality testing progress tracking."""
    
    def __init__(self):
        """Initialize QualityTestProgressModel with default values."""
        self.Id: Optional[int] = None
        self.QualityTestId: Optional[int] = None
        self.Status: Optional[str] = None  # Pending, Running, Completed, Failed
        self.ProgressPercent: Optional[float] = None
        self.CurrentPhase: Optional[str] = None
        self.StartTime: Optional[datetime] = None
        self.EndTime: Optional[datetime] = None
        self.ElapsedTime: Optional[float] = None
        self.ErrorMessage: Optional[str] = None
        self.CreatedDate: Optional[datetime] = None
        self.UpdatedDate: Optional[datetime] = None
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        return {
            "Id": self.Id,
            "QualityTestId": self.QualityTestId,
            "Status": self.Status,
            "ProgressPercent": self.ProgressPercent,
            "CurrentPhase": self.CurrentPhase,
            "StartTime": self.StartTime.isoformat() if self.StartTime else None,
            "EndTime": self.EndTime.isoformat() if self.EndTime else None,
            "ElapsedTime": self.ElapsedTime,
            "ErrorMessage": self.ErrorMessage,
            "CreatedDate": self.CreatedDate.isoformat() if self.CreatedDate else None,
            "UpdatedDate": self.UpdatedDate.isoformat() if self.UpdatedDate else None
        }
    
    def FromDict(self, Data: Dict[str, Any]) -> None:
        """Populate model from dictionary."""
        self.Id = Data.get("Id")
        self.QualityTestId = Data.get("QualityTestId")
        self.Status = Data.get("Status")
        self.ProgressPercent = Data.get("ProgressPercent")
        self.CurrentPhase = Data.get("CurrentPhase")
        self.ErrorMessage = Data.get("ErrorMessage")
        
        # Handle datetime fields
        if Data.get("StartTime"):
            if isinstance(Data["StartTime"], str):
                self.StartTime = datetime.fromisoformat(Data["StartTime"])
            else:
                self.StartTime = Data["StartTime"]
        
        if Data.get("EndTime"):
            if isinstance(Data["EndTime"], str):
                self.EndTime = datetime.fromisoformat(Data["EndTime"])
            else:
                self.EndTime = Data["EndTime"]
        
        if Data.get("CreatedDate"):
            if isinstance(Data["CreatedDate"], str):
                self.CreatedDate = datetime.fromisoformat(Data["CreatedDate"])
            else:
                self.CreatedDate = Data["CreatedDate"]
        
        if Data.get("UpdatedDate"):
            if isinstance(Data["UpdatedDate"], str):
                self.UpdatedDate = datetime.fromisoformat(Data["UpdatedDate"])
            else:
                self.UpdatedDate = Data["UpdatedDate"]
    
    def __str__(self) -> str:
        """String representation of the model."""
        return f"QualityTestProgressModel(Id={self.Id}, QualityTestId={self.QualityTestId}, Status={self.Status}, ProgressPercent={self.ProgressPercent})"
    
    def __repr__(self) -> str:
        """Detailed string representation of the model."""
        return f"QualityTestProgressModel(Id={self.Id}, QualityTestId={self.QualityTestId}, Status={self.Status}, ProgressPercent={self.ProgressPercent}, CurrentPhase={self.CurrentPhase})"
