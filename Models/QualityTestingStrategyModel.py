"""
QualityTestingStrategyModel
Data model for quality testing strategy configuration.
"""

from typing import Optional, Dict, Any
from datetime import datetime


class QualityTestingStrategyModel:
    """Data model for quality testing strategy configuration."""
    
    def __init__(self):
        """Initialize QualityTestingStrategyModel with default values."""
        self.Id: Optional[int] = None
        self.ProfileId: Optional[int] = None
        self.StrategyType: Optional[str] = None  # Skip, Single, Multi, Custom
        self.VMAFThreshold: Optional[float] = None
        self.MaxAttempts: Optional[int] = None
        self.AlternativeProfileIds: Optional[str] = None  # JSON string of profile IDs
        self.CustomSettings: Optional[str] = None  # JSON string of custom settings
        self.IsEnabled: Optional[bool] = None
        self.CreatedDate: Optional[datetime] = None
        self.UpdatedDate: Optional[datetime] = None
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        return {
            "Id": self.Id,
            "ProfileId": self.ProfileId,
            "StrategyType": self.StrategyType,
            "VMAFThreshold": self.VMAFThreshold,
            "MaxAttempts": self.MaxAttempts,
            "AlternativeProfileIds": self.AlternativeProfileIds,
            "CustomSettings": self.CustomSettings,
            "IsEnabled": self.IsEnabled,
            "CreatedDate": self.CreatedDate.isoformat() if self.CreatedDate else None,
            "UpdatedDate": self.UpdatedDate.isoformat() if self.UpdatedDate else None
        }
    
    def FromDict(self, Data: Dict[str, Any]) -> None:
        """Populate model from dictionary."""
        self.Id = Data.get("Id")
        self.ProfileId = Data.get("ProfileId")
        self.StrategyType = Data.get("StrategyType")
        self.VMAFThreshold = Data.get("VMAFThreshold")
        self.MaxAttempts = Data.get("MaxAttempts")
        self.AlternativeProfileIds = Data.get("AlternativeProfileIds")
        self.CustomSettings = Data.get("CustomSettings")
        self.IsEnabled = Data.get("IsEnabled")
        
        # Handle datetime fields
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
        return f"QualityTestingStrategyModel(Id={self.Id}, ProfileId={self.ProfileId}, StrategyType={self.StrategyType}, VMAFThreshold={self.VMAFThreshold})"
    
    def __repr__(self) -> str:
        """Detailed string representation of the model."""
        return f"QualityTestingStrategyModel(Id={self.Id}, ProfileId={self.ProfileId}, StrategyType={self.StrategyType}, VMAFThreshold={self.VMAFThreshold}, MaxAttempts={self.MaxAttempts}, IsEnabled={self.IsEnabled})"
