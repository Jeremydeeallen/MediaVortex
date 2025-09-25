from typing import Dict, Any, List, Optional
from datetime import datetime
from Services.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Services.VideoTranscodingService import VideoTranscodingService
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class TranscodingViewModel:
    """ViewModel for transcoding operations that maintains the existing controller contract."""
    
    def __init__(self, ProcessTranscodeQueueInstance: ProcessTranscodeQueueService = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 DatabaseManagerInstance: DatabaseManager = None):
        self.ProcessTranscodeQueue = ProcessTranscodeQueueInstance or ProcessTranscodeQueueService()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def StartTranscoding(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start transcoding with specified number of concurrent jobs."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "TranscodingViewModel", MaxConcurrentJobs)
            
            return self.ProcessTranscodeQueue.Run(MaxConcurrentJobs)
            
        except Exception as e:
            errorMsg = f"Exception starting transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "StartTranscoding")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def StopTranscoding(self) -> Dict[str, Any]:
        """Stop transcoding operations."""
        try:
            LoggingService.LogFunctionEntry("StopTranscoding", "TranscodingViewModel")
            
            return self.ProcessTranscodeQueue.Stop()
            
        except Exception as e:
            errorMsg = f"Exception stopping transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "StopTranscoding")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetTranscodingStatus(self) -> Dict[str, Any]:
        """Get current transcoding status and progress."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "TranscodingViewModel")
            
            return self.ProcessTranscodeQueue.GetStatus()
            
        except Exception as e:
            errorMsg = f"Exception getting transcoding status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "GetTranscodingStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetTranscodingHistory(self, Limit: int = 50) -> Dict[str, Any]:
        """Get transcoding history from database."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingHistory", "TranscodingViewModel", Limit)
            
            # Get recent transcoding attempts
            query = """
                SELECT ta.Id, ta.JobId, ta.StartTime, ta.EndTime, ta.Duration, 
                       ta.Success, ta.OutputFilePath, ta.ErrorMessage,
                       tq.FilePath, tq.AssignedProfile
                FROM TranscodeAttempts ta
                JOIN TranscodeQueue tq ON ta.JobId = tq.Id
                ORDER BY ta.StartTime DESC
                LIMIT ?
            """
            
            rows = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (Limit,))
            
            history = []
            for row in rows:
                historyItem = {
                    'Id': row['Id'],
                    'JobId': row['JobId'],
                    'StartTime': row['StartTime'],
                    'EndTime': row['EndTime'],
                    'Duration': row['Duration'],
                    'Success': bool(row['Success']),
                    'OutputFilePath': row['OutputFilePath'],
                    'ErrorMessage': row['ErrorMessage'],
                    'FilePath': row['FilePath'],
                    'AssignedProfile': row['AssignedProfile']
                }
                history.append(historyItem)
            
            return {
                "Success": True,
                "History": history,
                "Count": len(history)
            }
            
        except Exception as e:
            errorMsg = f"Exception getting transcoding history: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "GetTranscodingHistory")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetRecentAttempts(self, Limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent transcoding attempts."""
        try:
            LoggingService.LogFunctionEntry("GetRecentAttempts", "TranscodingViewModel", Limit)
            
            # Get recent attempts from DatabaseManager
            attempts = self.DatabaseManager.GetRecentTranscodeAttempts(Limit)
            
            return attempts
            
        except Exception as e:
            LoggingService.LogException("Exception getting recent attempts", e, "TranscodingViewModel", "GetRecentAttempts")
            return []
    
    def GetProgressSummary(self) -> Dict[str, Any]:
        """Get transcoding progress summary."""
        try:
            LoggingService.LogFunctionEntry("GetProgressSummary", "TranscodingViewModel")
            
            # Get current progress from database
            currentProgress = self.DatabaseManager.GetCurrentTranscodeProgress()
            
            # Get queue statistics
            queueStats = self.GetQueueStatistics()
            
            return {
                'CurrentProgress': currentProgress,
                'QueueStatistics': queueStats,
                'IsTranscoding': self.ProcessTranscodeQueue.IsProcessing,
                'ActiveJobs': len(self.ProcessTranscodeQueue.ActiveJobs)
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting progress summary", e, "TranscodingViewModel", "GetProgressSummary")
            return {}
    
    def GetCurrentTranscodeProgress(self) -> Dict[str, Any]:
        """Get current transcoding progress from database."""
        try:
            return self.DatabaseManager.GetCurrentTranscodeProgress()
        except Exception as e:
            LoggingService.LogException("Exception getting current progress", e, "TranscodingViewModel", "GetCurrentTranscodeProgress")
            return {}
    
    def RefreshStatus(self) -> Dict[str, Any]:
        """Refresh transcoding status and progress."""
        try:
            LoggingService.LogFunctionEntry("RefreshStatus", "TranscodingViewModel")
            
            # Get current status
            status = self.GetTranscodingStatus()
            
            return {
                "Success": True,
                "Status": status,
                "Timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            errorMsg = f"Exception refreshing status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "RefreshStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get queue statistics for progress summary."""
        try:
            # Get queue counts by status
            query = """
                SELECT Status, COUNT(*) as Count
                FROM TranscodeQueue
                GROUP BY Status
            """
            
            rows = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            
            stats = {
                'Pending': 0,
                'Processing': 0,
                'Completed': 0,
                'Failed': 0,
                'Total': 0
            }
            
            for row in rows:
                status = row['Status']
                count = row['Count']
                stats[status] = count
                stats['Total'] += count
            
            return stats
            
        except Exception as e:
            LoggingService.LogException("Exception getting queue statistics", e, "TranscodingViewModel", "GetQueueStatistics")
            return {}