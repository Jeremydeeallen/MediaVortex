from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Services.TranscodingBusinessService import TranscodingBusinessService
from Services.VMAFQueueBusinessService import VMAFQueueBusinessService
from Services.LoggingService import LoggingService


class ActivityViewModel:
    """Manages real-time activity progress UI state including transcoding and VMAF quality analysis."""
    
    def __init__(self, TranscodingService: TranscodingBusinessService = None, VMAFService: VMAFQueueBusinessService = None):
        self.TranscodingService = TranscodingService or TranscodingBusinessService()
        self.VMAFService = VMAFService or VMAFQueueBusinessService()
        self.CurrentJob = None
        self.CurrentVMAFJob = None
        self.Progress = {}
        self.VMAFProgress = {}
        self.IsTranscoding = False
        self.IsVMAFProcessing = False
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
            
            # Filter out in-progress attempts (Success is None) - only show completed attempts
            completedAttempts = [attempt for attempt in attempts if attempt.Success is not None]
            
            # Sort by date and limit
            completedAttempts.sort(key=lambda x: x.AttemptDate or datetime.min, reverse=True)
            recentAttempts = completedAttempts[:Limit]
            
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
            
            # Reduced logging verbosity for routine data retrieval
            return result
            
        except Exception as e:
            LoggingService.LogException("Exception getting recent attempts", e, "TranscodeProgressViewModel", "GetRecentAttempts")
            return []
    
    def GetCurrentTranscodeProgress(self) -> Dict[str, Any]:
        """Get current transcoding progress from database using optimized single-record approach."""
        try:
            LoggingService.LogFunctionEntry("GetCurrentTranscodeProgress", "TranscodeProgressViewModel")
            
            # Get current running job
            status = self.TranscodingService.GetTranscodingStatus()
            currentJob = status.get("CurrentJob")
            
            if not currentJob or currentJob.get("Status") != "Running":
                return {"Success": False, "Message": "No active transcoding job"}
            
            # Get the latest attempt for this job by file path
            attempts = self.TranscodingService.DatabaseManager.GetTranscodeAttemptsByFilePath(currentJob.get("FilePath"))
            if not attempts:
                return {"Success": False, "Message": "No transcoding attempt found"}
            
            # Find the current running attempt (Success is None) or the most recent attempt
            runningAttempt = None
            for attempt in attempts:
                if attempt.Success is None:  # This is the current running attempt
                    runningAttempt = attempt
                    break
            
            if not runningAttempt:
                return {"Success": False, "Message": "No running transcoding attempt found"}
            
            latestAttempt = runningAttempt
            
            # Get progress from database
            progress = self.TranscodingService.DatabaseManager.GetLatestTranscodeProgress(latestAttempt.Id)
            
            if not progress:
                return {"Success": False, "Message": "No progress data found"}
            
            # Format progress data for frontend
            progressData = {
                "Success": True,
                "AttemptId": latestAttempt.Id,
                "FileName": self.ExtractFileName(latestAttempt.FilePath),
                "StartTime": currentJob.get("DateStarted"),
                "CurrentPhase": progress.get("CurrentPhase", "Transcoding"),
                "ProgressPercent": progress.get("ProgressPercent", 0.0),
                "CurrentFrame": progress.get("CurrentFrame", 0),
                "CurrentFPS": progress.get("CurrentFPS", 0.0),
                "ETA": progress.get("ETA", "Unknown"),
                "CurrentSpeed": progress.get("CurrentSpeed", "0x"),
                "LastUpdate": progress.get("LastProgressUpdate")
            }
            
            LoggingService.LogInfo(f"Retrieved progress for attempt {latestAttempt.Id}: {progressData['CurrentPhase']} ({progressData['ProgressPercent']}%)", "TranscodeProgressViewModel", "GetCurrentTranscodeProgress")
            return progressData
            
        except Exception as e:
            LoggingService.LogException("Exception getting current transcode progress", e, "TranscodeProgressViewModel", "GetCurrentTranscodeProgress")
            return {"Success": False, "Message": f"Error retrieving progress: {str(e)}"}

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
    
    def GetVMAFStatus(self) -> Dict[str, Any]:
        """Get current VMAF processing status and progress."""
        try:
            LoggingService.LogFunctionEntry("GetVMAFStatus", "ActivityViewModel")
            
            self.ErrorMessage = ""
            
            # Get status from VMAF service
            Status = self.VMAFService.GetVMAFQueueStatus()
            
            self.IsVMAFProcessing = Status.get("IsRunning", False)
            self.CurrentVMAFJob = Status.get("CurrentVMAFJob")
            
            # Get progress information
            if self.CurrentVMAFJob:
                self.VMAFProgress = {
                    "VMAFQueueId": self.CurrentVMAFJob.get("Id"),
                    "FileName": self.CurrentVMAFJob.get("FileName"),
                    "Status": self.CurrentVMAFJob.get("Status"),
                    "DateStarted": self.CurrentVMAFJob.get("DateStarted"),
                    "IsRunning": self.CurrentVMAFJob.get("Status") == "Running",
                    "TranscodeAttemptId": self.CurrentVMAFJob.get("TranscodeAttemptId")
                }
            else:
                self.VMAFProgress = {}
            
            Result = {
                "Success": True,
                "IsVMAFProcessing": self.IsVMAFProcessing,
                "CurrentVMAFJob": self.CurrentVMAFJob,
                "VMAFProgress": self.VMAFProgress,
                "VMAFQueueStatistics": Status.get("QueueStatistics", {})
            }
            
            return Result
            
        except Exception as e:
            self.ErrorMessage = f"Error getting VMAF status: {str(e)}"
            LoggingService.LogException("Exception getting VMAF status", e, "ActivityViewModel", "GetVMAFStatus")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def StartVMAFProcessing(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start the VMAF processing."""
        try:
            LoggingService.LogFunctionEntry("StartVMAFProcessing", "ActivityViewModel", MaxConcurrentJobs)
            
            self.ErrorMessage = ""
            self.SuccessMessage = ""
            
            # Start VMAF processing using service
            Result = self.VMAFService.StartVMAFProcessing(MaxConcurrentJobs)
            
            if Result.get("Success", False):
                self.SuccessMessage = "VMAF processing started successfully"
                self.IsVMAFProcessing = True
                LoggingService.LogInfo("VMAF processing started", "ActivityViewModel", "StartVMAFProcessing")
            else:
                self.ErrorMessage = Result.get("ErrorMessage", "Failed to start VMAF processing")
                LoggingService.LogError(self.ErrorMessage, "ActivityViewModel", "StartVMAFProcessing")
            
            return Result
            
        except Exception as e:
            self.ErrorMessage = f"Error starting VMAF processing: {str(e)}"
            LoggingService.LogException("Exception starting VMAF processing", e, "ActivityViewModel", "StartVMAFProcessing")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def StopVMAFProcessing(self) -> Dict[str, Any]:
        """Stop the VMAF processing."""
        try:
            LoggingService.LogFunctionEntry("StopVMAFProcessing", "ActivityViewModel")
            
            self.ErrorMessage = ""
            self.SuccessMessage = ""
            
            # Stop VMAF processing using service
            Result = self.VMAFService.StopVMAFProcessing()
            
            if Result.get("Success", False):
                self.SuccessMessage = "VMAF processing stopped successfully"
                self.IsVMAFProcessing = False
                self.CurrentVMAFJob = None
                self.VMAFProgress = {}
                LoggingService.LogInfo("VMAF processing stopped", "ActivityViewModel", "StopVMAFProcessing")
            else:
                self.ErrorMessage = Result.get("ErrorMessage", "Failed to stop VMAF processing")
                LoggingService.LogError(self.ErrorMessage, "ActivityViewModel", "StopVMAFProcessing")
            
            return Result
            
        except Exception as e:
            self.ErrorMessage = f"Error stopping VMAF processing: {str(e)}"
            LoggingService.LogException("Exception stopping VMAF processing", e, "ActivityViewModel", "StopVMAFProcessing")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}
    
    def GetVMAFQueue(self) -> Dict[str, Any]:
        """Get current VMAF queue items."""
        try:
            LoggingService.LogFunctionEntry("GetVMAFQueue", "ActivityViewModel")
            
            # Get VMAF queue items
            QueueItems = self.VMAFService.DatabaseManager.GetAllVMAFQueueItems()
            
            # Format queue items for response
            FormattedItems = []
            for Item in QueueItems:
                FormattedItems.append({
                    'Id': Item.Id,
                    'TranscodeAttemptId': Item.TranscodeAttemptId,
                    'FileName': Item.FileName,
                    'Status': Item.Status,
                    'Priority': Item.Priority,
                    'DateAdded': Item.DateAdded.isoformat() if Item.DateAdded else None,
                    'DateStarted': Item.DateStarted.isoformat() if Item.DateStarted else None,
                    'DateCompleted': Item.DateCompleted.isoformat() if Item.DateCompleted else None,
                    'VMAFScore': Item.VMAFScore,
                    'QualityThreshold': Item.QualityThreshold,
                    'ErrorMessage': Item.ErrorMessage,
                    'RetryCount': Item.RetryCount,
                    'MaxRetries': Item.MaxRetries
                })
            
            Result = {
                "Success": True,
                "Message": "VMAF queue retrieved successfully",
                "QueueItems": FormattedItems,
                "TotalItems": len(FormattedItems)
            }
            
            LoggingService.LogInfo(f"Retrieved {len(FormattedItems)} VMAF queue items", "ActivityViewModel", "GetVMAFQueue")
            return Result
            
        except Exception as e:
            ErrorMsg = f"Exception getting VMAF queue: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "ActivityViewModel", "GetVMAFQueue")
            return {"Success": False, "ErrorMessage": ErrorMsg}
    
    def GetCombinedStatus(self) -> Dict[str, Any]:
        """Get combined status for both transcoding and VMAF processing."""
        try:
            LoggingService.LogFunctionEntry("GetCombinedStatus", "ActivityViewModel")
            
            # Get transcoding status
            TranscodingStatus = self.GetTranscodingStatus()
            
            # Get VMAF status
            VMAFStatus = self.GetVMAFStatus()
            
            # Get progress summary
            Summary = self.GetProgressSummary()
            
            Result = {
                "Success": True,
                "Transcoding": TranscodingStatus,
                "VMAF": VMAFStatus,
                "Summary": Summary
            }
            
            return Result
            
        except Exception as e:
            ErrorMsg = f"Exception getting combined status: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "ActivityViewModel", "GetCombinedStatus")
            return {"Success": False, "ErrorMessage": ErrorMsg}
