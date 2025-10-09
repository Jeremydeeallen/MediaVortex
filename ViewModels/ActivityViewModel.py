from typing import Dict, Any, List, Optional
from datetime import datetime
from ViewModels.TranscodingViewModel import TranscodingViewModel
from Services.LoggingService import LoggingService


class ActivityViewModel:
    """ViewModel for real-time transcoding activity and progress tracking."""
    
    def __init__(self, TranscodingService: TranscodingViewModel = None):
        self.TranscodingService = TranscodingService or TranscodingViewModel()
        
        # Activity state
        self.IsTranscoding = False
        self.CurrentProgress = {}
        self.ActiveJobs = []
        self.LastUpdate = None
    
    def StartTranscoding(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start transcoding with specified number of concurrent jobs."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "ActivityViewModel", MaxConcurrentJobs)
            
            result = self.TranscodingService.StartTranscoding(MaxConcurrentJobs)
            
            if result.get("Success", False):
                self.IsTranscoding = True
                self.LastUpdate = datetime.now()
                LoggingService.LogInfo(f"Started transcoding with {MaxConcurrentJobs} concurrent jobs", 
                                     "ActivityViewModel", "StartTranscoding")
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception starting transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ActivityViewModel", "StartTranscoding")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def StopTranscoding(self) -> Dict[str, Any]:
        """Stop transcoding operations."""
        try:
            LoggingService.LogFunctionEntry("StopTranscoding", "ActivityViewModel")
            
            result = self.TranscodingService.StopTranscoding()
            
            if result.get("Success", False):
                self.IsTranscoding = False
                self.ActiveJobs.clear()
                self.LastUpdate = datetime.now()
                LoggingService.LogInfo("Stopped transcoding", "ActivityViewModel", "StopTranscoding")
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception stopping transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ActivityViewModel", "StopTranscoding")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetTranscodingStatus(self) -> Dict[str, Any]:
        """Get current transcoding status and progress."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "ActivityViewModel")
            
            # Get status from transcoding service
            status = self.TranscodingService.GetTranscodingStatus()
            
            if status.get("Success", False):
                # Update local state
                self.IsTranscoding = status.get("IsTranscoding", False)
                self.CurrentProgress = status.get("CurrentProgress", {})
                self.LastUpdate = datetime.now()
                
                # Add activity-specific information
                status.update({
                    "ActivityLastUpdate": self.LastUpdate.isoformat(),
                    "LocalIsTranscoding": self.IsTranscoding
                })
            
            return status
            
        except Exception as e:
            errorMsg = f"Exception getting transcoding status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ActivityViewModel", "GetTranscodingStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetTranscodingHistory(self, Limit: int = 50) -> Dict[str, Any]:
        """Get transcoding history."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingHistory", "ActivityViewModel", Limit)
            
            return self.TranscodingService.GetTranscodingHistory(Limit)
            
        except Exception as e:
            errorMsg = f"Exception getting transcoding history: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ActivityViewModel", "GetTranscodingHistory")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetProgressSummary(self) -> Dict[str, Any]:
        """Get transcoding progress summary."""
        try:
            LoggingService.LogFunctionEntry("GetProgressSummary", "ActivityViewModel")
            
            summary = self.TranscodingService.GetProgressSummary()
            
            # Add activity-specific information
            summary.update({
                "ActivityIsTranscoding": self.IsTranscoding,
                "ActivityLastUpdate": self.LastUpdate.isoformat() if self.LastUpdate else None,
                "ActivityCurrentProgress": self.CurrentProgress
            })
            
            return summary
            
        except Exception as e:
            LoggingService.LogException("Exception getting progress summary", e, "ActivityViewModel", "GetProgressSummary")
            return {}
    
    def GetCurrentTranscodeProgress(self) -> Dict[str, Any]:
        """Get current transcoding progress from database."""
        try:
            # Get progress from transcoding service
            progress = self.TranscodingService.GetCurrentTranscodeProgress()
            
            # Update local state
            self.CurrentProgress = progress
            self.LastUpdate = datetime.now()
            
            return progress
            
        except Exception as e:
            LoggingService.LogException("Exception getting current progress", e, "ActivityViewModel", "GetCurrentTranscodeProgress")
            return {}
    
    def RefreshStatus(self) -> Dict[str, Any]:
        """Refresh transcoding status and progress."""
        try:
            LoggingService.LogFunctionEntry("RefreshStatus", "ActivityViewModel")
            
            # Refresh status from transcoding service
            result = self.TranscodingService.RefreshStatus()
            
            if result.get("Success", False):
                # Update local state
                status = result.get("Status", {})
                self.IsTranscoding = status.get("IsTranscoding", False)
                self.CurrentProgress = status.get("CurrentProgress", {})
                self.LastUpdate = datetime.now()
                
                # Add activity-specific information
                result.update({
                    "ActivityLastUpdate": self.LastUpdate.isoformat(),
                    "LocalIsTranscoding": self.IsTranscoding
                })
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception refreshing status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ActivityViewModel", "RefreshStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetActivityState(self) -> Dict[str, Any]:
        """Get current activity state for UI updates."""
        try:
            return {
                "IsTranscoding": self.IsTranscoding,
                "CurrentProgress": self.CurrentProgress,
                "ActiveJobs": self.ActiveJobs,
                "LastUpdate": self.LastUpdate.isoformat() if self.LastUpdate else None,
                "Timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting activity state", e, "ActivityViewModel", "GetActivityState")
            return {}
    
    def UpdateActivityState(self, NewState: Dict[str, Any]):
        """Update local activity state from external source."""
        try:
            self.IsTranscoding = NewState.get("IsTranscoding", False)
            self.CurrentProgress = NewState.get("CurrentProgress", {})
            self.ActiveJobs = NewState.get("ActiveJobs", [])
            self.LastUpdate = datetime.now()
            
        except Exception as e:
            LoggingService.LogException("Exception updating activity state", e, "ActivityViewModel", "UpdateActivityState")