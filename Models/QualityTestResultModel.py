"""
QualityTestResultModel
Data model for individual quality test results.
"""

from typing import Optional, Dict, Any
from datetime import datetime


class QualityTestResultModel:
    """Data model for individual quality test results."""
    
    def __init__(self):
        """Initialize QualityTestResultModel with default values."""
        self.Id: Optional[int] = None
        self.QualityTestId: Optional[int] = None
        self.TranscodeAttemptId: Optional[int] = None
        self.VMAFScore: Optional[float] = None
        self.ProfileId: Optional[int] = None
        self.ProfileName: Optional[str] = None
        self.FileSize: Optional[int] = None
        self.TestDuration: Optional[float] = None
        self.PassesThreshold: Optional[bool] = None
        self.Rank: Optional[int] = None
        self.ErrorMessage: Optional[str] = None
        self.DateTested: Optional[datetime] = None
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        return {
            "Id": self.Id,
            "QualityTestId": self.QualityTestId,
            "TranscodeAttemptId": self.TranscodeAttemptId,
            "VMAFScore": self.VMAFScore,
            "ProfileId": self.ProfileId,
            "ProfileName": self.ProfileName,
            "FileSize": self.FileSize,
            "TestDuration": self.TestDuration,
            "PassesThreshold": self.PassesThreshold,
            "Rank": self.Rank,
            "ErrorMessage": self.ErrorMessage,
            "DateTested": self.DateTested.isoformat() if self.DateTested else None
        }
    
    def FromDict(self, Data: Dict[str, Any]) -> None:
        """Populate model from dictionary."""
        self.Id = Data.get("Id")
        self.QualityTestId = Data.get("QualityTestId")
        self.TranscodeAttemptId = Data.get("TranscodeAttemptId")
        self.VMAFScore = Data.get("VMAFScore")
        self.ProfileId = Data.get("ProfileId")
        self.ProfileName = Data.get("ProfileName")
        self.FileSize = Data.get("FileSize")
        self.TestDuration = Data.get("TestDuration")
        self.PassesThreshold = Data.get("PassesThreshold")
        self.Rank = Data.get("Rank")
        self.ErrorMessage = Data.get("ErrorMessage")
        
        # Handle datetime fields
        if Data.get("DateTested"):
            if isinstance(Data["DateTested"], str):
                self.DateTested = datetime.fromisoformat(Data["DateTested"])
            else:
                self.DateTested = Data["DateTested"]
    
    def __str__(self) -> str:
        """String representation of the model."""
        return f"QualityTestResultModel(Id={self.Id}, QualityTestId={self.QualityTestId}, VMAFScore={self.VMAFScore}, PassesThreshold={self.PassesThreshold})"
    
    def __repr__(self) -> str:
        """Detailed string representation of the model."""
        return f"QualityTestResultModel(Id={self.Id}, QualityTestId={self.QualityTestId}, TranscodeAttemptId={self.TranscodeAttemptId}, VMAFScore={self.VMAFScore}, ProfileId={self.ProfileId}, PassesThreshold={self.PassesThreshold})"
