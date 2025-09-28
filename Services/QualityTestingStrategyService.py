"""
QualityTestingStrategyService
Manages quality testing strategies and configuration.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Models.QualityTestingStrategyModel import QualityTestingStrategyModel


class QualityTestingStrategyService:
    """Manages quality testing strategies and their configuration."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        """Initialize the QualityTestingStrategyService."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        
        LoggingService.LogInfo("QualityTestingStrategyService initialized", "QualityTestingStrategyService", "__init__")
    
    def GetStrategyForProfile(self, ProfileId: int) -> Optional[QualityTestingStrategyModel]:
        """Get quality testing strategy for a specific profile."""
        try:
            LoggingService.LogFunctionEntry("GetStrategyForProfile", "QualityTestingStrategyService", ProfileId)
            
            Strategy = self.DatabaseManager.GetQualityTestingStrategyForProfile(ProfileId)
            
            if Strategy:
                LoggingService.LogInfo(f"Retrieved quality testing strategy for profile {ProfileId}", "QualityTestingStrategyService", "GetStrategyForProfile")
            else:
                LoggingService.LogInfo(f"No quality testing strategy found for profile {ProfileId}", "QualityTestingStrategyService", "GetStrategyForProfile")
            
            return Strategy
            
        except Exception as e:
            LoggingService.LogException(f"Failed to get strategy for profile {ProfileId}", e, "QualityTestingStrategyService", "GetStrategyForProfile")
            return None
    
    def SaveStrategy(self, Strategy: QualityTestingStrategyModel) -> int:
        """Save a quality testing strategy."""
        try:
            LoggingService.LogFunctionEntry("SaveStrategy", "QualityTestingStrategyService", Strategy.ProfileId, Strategy.StrategyType)
            
            StrategyId = self.DatabaseManager.SaveQualityTestingStrategy(Strategy)
            
            if StrategyId > 0:
                LoggingService.LogInfo(f"Saved quality testing strategy {StrategyId}", "QualityTestingStrategyService", "SaveStrategy")
            else:
                LoggingService.LogError(f"Failed to save quality testing strategy", "QualityTestingStrategyService", "SaveStrategy")
            
            return StrategyId
            
        except Exception as e:
            LoggingService.LogException("Failed to save quality testing strategy", e, "QualityTestingStrategyService", "SaveStrategy")
            return 0
    
    def CreateDefaultStrategy(self, ProfileId: int, StrategyType: str = "Single", VMAFThreshold: float = 90.0) -> QualityTestingStrategyModel:
        """Create a default quality testing strategy for a profile."""
        try:
            LoggingService.LogFunctionEntry("CreateDefaultStrategy", "QualityTestingStrategyService", ProfileId, StrategyType, VMAFThreshold)
            
            Strategy = QualityTestingStrategyModel()
            Strategy.ProfileId = ProfileId
            Strategy.StrategyType = StrategyType
            Strategy.VMAFThreshold = VMAFThreshold
            Strategy.MaxAttempts = 3
            Strategy.AlternativeProfileIds = None
            Strategy.CustomSettings = None
            Strategy.IsEnabled = True
            Strategy.UpdatedDate = datetime.now()
            
            LoggingService.LogInfo(f"Created default quality testing strategy for profile {ProfileId}", "QualityTestingStrategyService", "CreateDefaultStrategy")
            
            return Strategy
            
        except Exception as e:
            LoggingService.LogException("Failed to create default quality testing strategy", e, "QualityTestingStrategyService", "CreateDefaultStrategy")
            return None
    
    def ValidateStrategy(self, Strategy: QualityTestingStrategyModel) -> Dict[str, Any]:
        """Validate a quality testing strategy."""
        try:
            LoggingService.LogFunctionEntry("ValidateStrategy", "QualityTestingStrategyService")
            
            Errors = []
            
            # Validate required fields
            if not Strategy.ProfileId or Strategy.ProfileId <= 0:
                Errors.append("ProfileId is required and must be positive")
            
            if not Strategy.StrategyType or Strategy.StrategyType not in ["Skip", "Single", "Multi", "Custom"]:
                Errors.append("StrategyType must be one of: Skip, Single, Multi, Custom")
            
            if Strategy.VMAFThreshold is not None and (Strategy.VMAFThreshold < 0 or Strategy.VMAFThreshold > 100):
                Errors.append("VMAFThreshold must be between 0 and 100")
            
            if Strategy.MaxAttempts is not None and (Strategy.MaxAttempts < 1 or Strategy.MaxAttempts > 10):
                Errors.append("MaxAttempts must be between 1 and 10")
            
            if Errors:
                return {
                    "Success": False,
                    "IsValid": False,
                    "Errors": Errors
                }
            else:
                return {
                    "Success": True,
                    "IsValid": True,
                    "Errors": []
                }
            
        except Exception as e:
            LoggingService.LogException("Failed to validate quality testing strategy", e, "QualityTestingStrategyService", "ValidateStrategy")
            return {
                "Success": False,
                "IsValid": False,
                "Errors": [f"Validation error: {str(e)}"]
            }
    
    def GetStrategyTypes(self) -> List[str]:
        """Get list of available strategy types."""
        return ["Skip", "Single", "Multi", "Custom"]
    
    def GetStrategyDescription(self, StrategyType: str) -> str:
        """Get description for a strategy type."""
        Descriptions = {
            "Skip": "No quality testing performed - transcoded file is accepted as-is",
            "Single": "Single VMAF quality test against the original file",
            "Multi": "Multiple quality tests with different settings to find the best result",
            "Custom": "Custom quality testing configuration with user-defined parameters"
        }
        
        return Descriptions.get(StrategyType, "Unknown strategy type")
