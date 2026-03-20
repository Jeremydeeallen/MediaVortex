from typing import Dict, Any, List, Optional
from datetime import datetime
from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Features.TranscodeJob.VideoTranscodingService import VideoTranscodingService
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService


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
        """Get current transcoding status and progress from ServiceStatus table."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "TranscodingViewModel")

            # Get status from ServiceStatus table instead of ProcessTranscodeQueueService
            query = """
                SELECT Status, HealthStatus, IsProcessing, ActiveJobsCount, LastHealthCheck
                FROM ServiceStatus
                WHERE ServiceName = 'TranscodeService'
            """

            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)

            if result and len(result) > 0:
                row = result[0]
                return {
                    "Success": True,
                    "IsTranscoding": bool(row['IsProcessing']),
                    "Status": row['Status'],
                    "HealthStatus": row['HealthStatus'],
                    "ActiveJobsCount": row['ActiveJobsCount'],
                    "LastHealthCheck": row['LastHealthCheck']
                }
            else:
                # TranscodeService not found in ServiceStatus table
                return {
                    "Success": True,
                    "IsTranscoding": False,
                    "Status": "Stopped",
                    "HealthStatus": "Unknown",
                    "ActiveJobsCount": 0,
                    "LastHealthCheck": None
                }

        except Exception as e:
            errorMsg = f"Exception getting transcoding status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingViewModel", "GetTranscodingStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }

    def GetTranscodingHistory(self, Limit: int = 50) -> Dict[str, Any]:
        """Get successful transcoding history from database."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingHistory", "TranscodingViewModel", Limit)

            # Get recent successful transcoding attempts only
            query = """
                SELECT ta.Id, ta.FilePath, ta.AttemptDate, ta.CompletedDate, ta.TranscodeDurationSeconds,
                       ta.Success, ta.ErrorMessage, ta.Quality, ta.ProfileName,
                       ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionPercent, ta.VMAF
                FROM TranscodeAttempts ta
                WHERE ta.Success = TRUE
                ORDER BY COALESCE(ta.CompletedDate, ta.AttemptDate) DESC
                LIMIT %s
            """

            rows = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (Limit,))

            history = []
            for row in rows:
                historyItem = {
                    'Id': row['Id'],
                    'FilePath': row['FilePath'],
                    'AttemptDate': row['AttemptDate'],
                    'CompletedDate': row['CompletedDate'],
                    'Duration': row['TranscodeDurationSeconds'],
                    'Success': bool(row['Success']),
                    'ErrorMessage': row['ErrorMessage'],
                    'Quality': row['Quality'],
                    'ProfileName': row['ProfileName'],
                    'OldSizeBytes': row['OldSizeBytes'],
                    'NewSizeBytes': row['NewSizeBytes'],
                    'SizeReductionPercent': row['SizeReductionPercent'],
                    'VMAF': row['VMAF']
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

    def GetProgressSummary(self) -> Dict[str, Any]:
        """Get transcoding progress summary."""
        try:
            LoggingService.LogFunctionEntry("GetProgressSummary", "TranscodingViewModel")

            # Get current progress from database
            currentProgress = self.DatabaseManager.GetCurrentTranscodeProgress()

            # Get queue statistics
            queueStats = self.GetQueueStatistics()

            # Get status from ServiceStatus table
            status = self.GetTranscodingStatus()

            return {
                'CurrentProgress': currentProgress,
                'QueueStatistics': queueStats,
                'IsTranscoding': status.get('IsTranscoding', False),
                'ActiveJobs': status.get('ActiveJobsCount', 0)
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

            # Get current status from ServiceStatus table
            status = self.GetTranscodingStatus()

            # Get current progress from database
            currentProgress = self.DatabaseManager.GetCurrentTranscodeProgress()

            return {
                "Success": True,
                "Status": status,
                "CurrentProgress": currentProgress,
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
