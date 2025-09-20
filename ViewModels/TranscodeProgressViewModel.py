from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Services.TranscodingBusinessService import TranscodingBusinessService
from Services.LoggingService import LoggingService


class TranscodeProgressViewModel:
    """Manages real-time transcoding progress UI state."""
    
    def __init__(self, TranscodingService: TranscodingBusinessService = None):
        self.TranscodingService = TranscodingService or TranscodingBusinessService()
        self.CurrentJob = None
        self.Progress = {}
        self.IsTranscoding = False
        self.ErrorMessage = ""
        self.SuccessMessage = ""
        self.RecentAttempts = []
    
    def GetTranscodingStatus(self) -> Dict[str, Any]:
        """Get current transcoding status and progress."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "TranscodeProgressViewModel")
            
            self.ErrorMessage = ""
            
            # Get status from transcoding service
            status = self.TranscodingService.GetTranscodingStatus()
            
            self.IsTranscoding = status.get("IsRunning", False)
            self.CurrentJob = status.get("CurrentJob")
            
            # Get progress information
            if self.CurrentJob:
                self.Progress = {
                    "JobId": self.CurrentJob.get("Id"),
                    "FileName": self.CurrentJob.get("FileName"),
                    "Status": self.CurrentJob.get("Status"),
                    "DateStarted": self.CurrentJob.get("DateStarted"),
                    "IsRunning": self.CurrentJob.get("Status") == "Running"
                }
            else:
                self.Progress = {}
            
            result = {
                "Success": True,
                "IsTranscoding": self.IsTranscoding,
                "CurrentJob": self.CurrentJob,
                "Progress": self.Progress,
                "QueueStatistics": status.get("QueueStatistics", {}),
                "FFmpegAvailable": status.get("FFmpegAvailable", False)
            }
            
            return result
            
        except Exception as e:
            self.ErrorMessage = f"Error getting transcoding status: {str(e)}"
            LoggingService.LogException("Exception getting transcoding status", e, "TranscodeProgressViewModel", "GetTranscodingStatus")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def StartTranscoding(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start the transcoding process."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "TranscodeProgressViewModel", MaxConcurrentJobs)
            
            self.ErrorMessage = ""
            self.SuccessMessage = ""
            
            # Start transcoding using service
            result = self.TranscodingService.StartTranscoding(MaxConcurrentJobs)
            
            if result.get("Success", False):
                self.SuccessMessage = "Transcoding process started successfully"
                self.IsTranscoding = True
                LoggingService.LogInfo("Transcoding started", "TranscodeProgressViewModel", "StartTranscoding")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to start transcoding")
                LoggingService.LogError(self.ErrorMessage, "TranscodeProgressViewModel", "StartTranscoding")
            
            return result
            
        except Exception as e:
            self.ErrorMessage = f"Error starting transcoding: {str(e)}"
            LoggingService.LogException("Exception starting transcoding", e, "TranscodeProgressViewModel", "StartTranscoding")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def StopTranscoding(self) -> Dict[str, Any]:
        """Stop the transcoding process."""
        try:
            LoggingService.LogFunctionEntry("StopTranscoding", "TranscodeProgressViewModel")
            
            self.ErrorMessage = ""
            self.SuccessMessage = ""
            
            # Stop transcoding using service
            result = self.TranscodingService.StopTranscoding()
            
            if result.get("Success", False):
                self.SuccessMessage = "Transcoding process stopped successfully"
                self.IsTranscoding = False
                self.CurrentJob = None
                self.Progress = {}
                LoggingService.LogInfo("Transcoding stopped", "TranscodeProgressViewModel", "StopTranscoding")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to stop transcoding")
                LoggingService.LogError(self.ErrorMessage, "TranscodeProgressViewModel", "StopTranscoding")
            
            return result
            
        except Exception as e:
            self.ErrorMessage = f"Error stopping transcoding: {str(e)}"
            LoggingService.LogException("Exception stopping transcoding", e, "TranscodeProgressViewModel", "StopTranscoding")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def GetTranscodingHistory(self, Limit: int = 50) -> Dict[str, Any]:
        """Get recent transcoding history."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingHistory", "TranscodeProgressViewModel", Limit)
            
            self.ErrorMessage = ""
            
            # Get history from transcoding service
            history = self.TranscodingService.GetTranscodingHistory(Limit)
            
            self.RecentAttempts = history
            
            result = {
                "Success": True,
                "History": history,
                "Count": len(history)
            }
            
            LoggingService.LogInfo(f"Retrieved {len(history)} history items", "TranscodeProgressViewModel", "GetTranscodingHistory")
            return result
            
        except Exception as e:
            self.ErrorMessage = f"Error getting transcoding history: {str(e)}"
            LoggingService.LogException("Exception getting transcoding history", e, "TranscodeProgressViewModel", "GetTranscodingHistory")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def GetRecentAttempts(self, Limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent transcoding attempts for display."""
        try:
            LoggingService.LogFunctionEntry("GetRecentAttempts", "TranscodeProgressViewModel", Limit)
            
            # Get recent attempts from database
            attempts = self.TranscodingService.DatabaseManager.GetAllTranscodeAttempts()
            
            # Sort by date and limit
            attempts.sort(key=lambda x: x.AttemptDate or datetime.min, reverse=True)
            recentAttempts = attempts[:Limit]
            
            result = []
            for attempt in recentAttempts:
                # Helper function to safely format datetime
                def format_datetime(dt):
                    if dt is None:
                        return None
                    if isinstance(dt, str):
                        return dt  # Already a string, return as-is
                    if hasattr(dt, 'isoformat'):
                        return dt.isoformat()
                    return str(dt)
                
                attemptDict = {
                    "Id": attempt.Id,
                    "FilePath": attempt.FilePath,
                    "FileName": self.ExtractFileName(attempt.FilePath),
                    "AttemptDate": format_datetime(attempt.AttemptDate),
                    "Success": attempt.Success,
                    "Quality": attempt.Quality,
                    "SizeReductionPercent": attempt.SizeReductionPercent,
                    "Duration": attempt.TranscodeDurationSeconds,
                    "DurationMinutes": attempt.TranscodeDurationMinutes,
                    "ErrorMessage": attempt.ErrorMessage,
                    "ProfileName": attempt.ProfileName,
                    "OldSizeMB": attempt.OldSizeMB,
                    "NewSizeMB": attempt.NewSizeMB,
                    "CompressionRatio": attempt.CompressionRatio,
                    "IsCompressed": attempt.IsCompressed
                }
                result.append(attemptDict)
            
            LoggingService.LogInfo(f"Retrieved {len(result)} recent attempts", "TranscodeProgressViewModel", "GetRecentAttempts")
            return result
            
        except Exception as e:
            LoggingService.LogException("Exception getting recent attempts", e, "TranscodeProgressViewModel", "GetRecentAttempts")
            return []
    
    def GetProgressSummary(self) -> Dict[str, Any]:
        """Get a summary of transcoding progress."""
        try:
            LoggingService.LogFunctionEntry("GetProgressSummary", "TranscodeProgressViewModel")
            
            # Get queue statistics
            queueStats = self.TranscodingService.QueueManagementService.GetQueueStatistics()
            
            # Get recent attempts
            recentAttempts = self.GetRecentAttempts(10)
            
            # Calculate success rate from recent attempts
            if recentAttempts:
                successfulAttempts = sum(1 for attempt in recentAttempts if attempt.get("Success", False))
                successRate = (successfulAttempts / len(recentAttempts)) * 100.0
            else:
                successRate = 0.0
            
            # Calculate average compression
            if recentAttempts:
                successfulCompressions = [attempt for attempt in recentAttempts if attempt.get("Success", False) and attempt.get("IsCompressed", False)]
                if successfulCompressions:
                    avgCompression = sum(attempt.get("SizeReductionPercent", 0) for attempt in successfulCompressions) / len(successfulCompressions)
                else:
                    avgCompression = 0.0
            else:
                avgCompression = 0.0
            
            summary = {
                "IsTranscoding": self.IsTranscoding,
                "CurrentJob": self.CurrentJob,
                "QueueStatistics": queueStats,
                "RecentAttemptsCount": len(recentAttempts),
                "SuccessRate": successRate,
                "AverageCompression": avgCompression,
                "FFmpegAvailable": self.TranscodingService.FFmpegService.CheckAvailability()
            }
            
            return summary
            
        except Exception as e:
            LoggingService.LogException("Exception getting progress summary", e, "TranscodeProgressViewModel", "GetProgressSummary")
            return {}
    
    def ExtractFileName(self, FilePath: str) -> str:
        """Extract filename from file path."""
        try:
            if not FilePath:
                return "Unknown"
            
            # Handle both Windows and Unix paths
            pathParts = FilePath.replace("\\", "/").split("/")
            return pathParts[-1] if pathParts else "Unknown"
            
        except Exception as e:
            LoggingService.LogException("Exception extracting filename", e, "TranscodeProgressViewModel", "ExtractFileName")
            return "Unknown"
    
    def ClearMessages(self):
        """Clear success and error messages."""
        self.SuccessMessage = ""
        self.ErrorMessage = ""
    
    def RefreshStatus(self) -> Dict[str, Any]:
        """Refresh the current transcoding status."""
        try:
            LoggingService.LogFunctionEntry("RefreshStatus", "TranscodeProgressViewModel")
            
            # Get updated status
            statusResult = self.GetTranscodingStatus()
            
            # Get updated history
            historyResult = self.GetTranscodingHistory(20)
            
            # Get progress summary
            summary = self.GetProgressSummary()
            
            result = {
                "Success": True,
                "Status": statusResult,
                "History": historyResult,
                "Summary": summary
            }
            
            return result
            
        except Exception as e:
            self.ErrorMessage = f"Error refreshing status: {str(e)}"
            LoggingService.LogException("Exception refreshing status", e, "TranscodeProgressViewModel", "RefreshStatus")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
