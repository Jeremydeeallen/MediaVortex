from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.QualityTestingQueueModel import QualityTestingQueueModel
from Services.QualityTestingOrchestratorService import QualityTestingOrchestratorService
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class QualityTestingViewModel:
    """Manages quality testing UI state and operations."""
    
    def __init__(self, QualityTestingService: QualityTestingOrchestratorService = None):
        self.QualityTestingService = QualityTestingService or QualityTestingOrchestratorService()
        self.DatabaseManager = DatabaseManager()
        self.QueueItems = []
        self.QueueStatistics = {}
        self.IsLoading = False
        self.ErrorMessage = ""
        self.SuccessMessage = ""
    
    def GetQualityTestingQueue(self, Page: int = 1, PageSize: int = 25, SortBy: str = "DateAdded", SortOrder: str = "DESC") -> Dict[str, Any]:
        """Get quality testing queue items with pagination and sorting."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingQueue", "QualityTestingViewModel", Page, PageSize, SortBy, SortOrder)
            
            self.IsLoading = True
            self.ErrorMessage = ""
            
            # Get all queue items from database
            AllQueueItems = self.DatabaseManager.GetAllQualityTestingQueueItems()
            
            # Sort items based on SortBy parameter
            if SortBy == "DateAdded":
                AllQueueItems.sort(key=lambda x: x.DateAdded or datetime.min, reverse=(SortOrder == "DESC"))
            elif SortBy == "Priority":
                AllQueueItems.sort(key=lambda x: x.Priority or 0, reverse=(SortOrder == "DESC"))
            elif SortBy == "Status":
                AllQueueItems.sort(key=lambda x: x.Status or "", reverse=(SortOrder == "DESC"))
            elif SortBy == "FileName":
                AllQueueItems.sort(key=lambda x: x.FileName or "", reverse=(SortOrder == "DESC"))
            elif SortBy == "VMAFScore":
                AllQueueItems.sort(key=lambda x: x.VMAFScore or 0, reverse=(SortOrder == "DESC"))
            
            # Calculate pagination
            TotalItems = len(AllQueueItems)
            TotalPages = (TotalItems + PageSize - 1) // PageSize
            StartIndex = (Page - 1) * PageSize
            EndIndex = min(StartIndex + PageSize, TotalItems)
            
            # Get page items
            PageItems = AllQueueItems[StartIndex:EndIndex]
            
            # Convert to dictionaries for JSON response
            QueueItemsDict = []
            for item in PageItems:
                QueueItemsDict.append({
                    "Id": item.Id,
                    "TranscodeAttemptId": item.TranscodeAttemptId,
                    "OriginalFilePath": item.OriginalFilePath,
                    "TranscodedFilePath": item.TranscodedFilePath,
                    "FileName": item.FileName,
                    "Status": item.Status,
                    "Priority": item.Priority,
                    "DateAdded": item.DateAdded.isoformat() if item.DateAdded and hasattr(item.DateAdded, 'isoformat') else str(item.DateAdded) if item.DateAdded else None,
                    "DateStarted": item.DateStarted.isoformat() if item.DateStarted and hasattr(item.DateStarted, 'isoformat') else str(item.DateStarted) if item.DateStarted else None,
                    "DateCompleted": item.DateCompleted.isoformat() if item.DateCompleted and hasattr(item.DateCompleted, 'isoformat') else str(item.DateCompleted) if item.DateCompleted else None,
                    "VMAFScore": item.VMAFScore,
                    "QualityThreshold": item.QualityThreshold,
                    "ErrorMessage": item.ErrorMessage,
                    "RetryCount": item.RetryCount,
                    "MaxRetries": item.MaxRetries,
                    "StrategyType": item.StrategyType,
                    "StrategyId": item.StrategyId,
                    "AlternativeProfileIds": item.AlternativeProfileIds,
                    "CustomSettings": item.CustomSettings,
                    "Results": item.Results,
                    "SelectedResultId": item.SelectedResultId
                })
            
            # Calculate statistics
            StatusCounts = {}
            for item in AllQueueItems:
                Status = item.Status or "Unknown"
                StatusCounts[Status] = StatusCounts.get(Status, 0) + 1
            
            self.QueueStatistics = {
                "TotalItems": TotalItems,
                "TotalPages": TotalPages,
                "CurrentPage": Page,
                "PageSize": PageSize,
                "StatusCounts": StatusCounts
            }
            
            self.IsLoading = False
            
            return {
                "Success": True,
                "QueueItems": QueueItemsDict,
                "Statistics": self.QueueStatistics,
                "Count": len(QueueItemsDict)
            }
            
        except Exception as e:
            self.IsLoading = False
            self.ErrorMessage = f"Failed to get quality testing queue: {str(e)}"
            LoggingService.LogException(self.ErrorMessage, e, "QualityTestingViewModel", "GetQualityTestingQueue")
            return {
                "Success": False,
                "ErrorMessage": self.ErrorMessage,
                "QueueItems": [],
                "Statistics": {},
                "Count": 0
            }
    
    def GetQualityTestingStatus(self) -> Dict[str, Any]:
        """Get current quality testing service status."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingStatus", "QualityTestingViewModel")
            
            # Get running jobs count
            RunningJobs = self.DatabaseManager.GetRunningQualityTestingJobsCount()
            
            # Get queue statistics
            QueueStats = self.DatabaseManager.GetQualityTestingQueueStatistics()
            
            # Check if service is running (this would be implemented based on your service monitoring)
            IsQualityTesting = RunningJobs > 0
            
            return {
                "Success": True,
                "IsQualityTesting": IsQualityTesting,
                "RunningJobs": RunningJobs,
                "QueueStatistics": QueueStats,
                "Timestamp": self.DatabaseManager.DatabaseService.GetCurrentTimestamp()
            }
            
        except Exception as e:
            ErrorMsg = f"Failed to get quality testing status: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "GetQualityTestingStatus")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg,
                "IsQualityTesting": False,
                "RunningJobs": 0,
                "QueueStatistics": {},
                "Timestamp": None
            }
    
    def GetQualityTestingHistory(self, Limit: int = 50) -> Dict[str, Any]:
        """Get quality testing history."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingHistory", "QualityTestingViewModel", Limit)
            
            # Get recent completed jobs
            HistoryItems = self.DatabaseManager.GetQualityTestingHistory(Limit)
            
            # Convert to dictionaries for JSON response
            HistoryItemsDict = []
            for item in HistoryItems:
                HistoryItemsDict.append({
                    "Id": item.Id,
                    "TranscodeAttemptId": item.TranscodeAttemptId,
                    "FileName": item.FileName,
                    "Status": item.Status,
                    "VMAFScore": item.VMAFScore,
                    "QualityThreshold": item.QualityThreshold,
                    "DateCompleted": item.DateCompleted.isoformat() if item.DateCompleted else None,
                    "ErrorMessage": item.ErrorMessage
                })
            
            return {
                "Success": True,
                "HistoryItems": HistoryItemsDict,
                "Count": len(HistoryItemsDict)
            }
            
        except Exception as e:
            ErrorMsg = f"Failed to get quality testing history: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "GetQualityTestingHistory")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg,
                "HistoryItems": [],
                "Count": 0
            }
    
    def GetQualityTestingProgress(self) -> Dict[str, Any]:
        """Get current quality testing progress."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingProgress", "QualityTestingViewModel")
            
            # Get running jobs
            RunningJobs = self.DatabaseManager.GetRunningQualityTestingJobs()
            
            # Convert to dictionaries for JSON response
            RunningJobsDict = []
            for job in RunningJobs:
                RunningJobsDict.append({
                    "Id": job.Id,
                    "TranscodeAttemptId": job.TranscodeAttemptId,
                    "FileName": job.FileName,
                    "Status": job.Status,
                    "DateStarted": job.DateStarted.isoformat() if job.DateStarted and hasattr(job.DateStarted, 'isoformat') else str(job.DateStarted) if job.DateStarted else None,
                    "Progress": self.PrivateCalculateJobProgress(job)
                })
            
            # Check if there are any running jobs
            IsRunning = len(RunningJobsDict) > 0
            CurrentJob = RunningJobsDict[0] if RunningJobsDict else None
            
            # Get progress details for the current job if running
            Progress = None
            if CurrentJob:
                Progress = CurrentJob.get("Progress", {})
            
            return {
                "Success": True,
                "IsRunning": IsRunning,
                "CurrentJob": CurrentJob,
                "Progress": Progress,
                "RunningJobs": RunningJobsDict,
                "Count": len(RunningJobsDict)
            }
            
        except Exception as e:
            ErrorMsg = f"Failed to get quality testing progress: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "GetQualityTestingProgress")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg,
                "RunningJobs": [],
                "Count": 0
            }
    
    def GetQualityTestingHistory(self, Limit: int = 5) -> Dict[str, Any]:
        """Get quality testing history/results."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingHistory", "QualityTestingViewModel", Limit)
            
            # Get recent quality test results
            Results = self.DatabaseManager.GetQualityTestResults(Limit=Limit)
            
            return {
                "Success": True,
                "QualityTestingResults": Results,
                "Count": len(Results)
            }
            
        except Exception as e:
            ErrorMsg = f"Failed to get quality testing history: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "GetQualityTestingHistory")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg,
                "QualityTestingResults": [],
                "Count": 0
            }
    
    def RetryQualityTestingJob(self, QueueId: int) -> Dict[str, Any]:
        """Retry a failed quality testing job."""
        try:
            LoggingService.LogFunctionEntry("RetryQualityTestingJob", "QualityTestingViewModel", QueueId)
            
            # Reset job status and retry count
            Success = self.DatabaseManager.ResetQualityTestingJobForRetry(QueueId)
            
            if Success:
                return {
                    "Success": True,
                    "Message": f"Quality testing job {QueueId} reset for retry"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Failed to reset quality testing job {QueueId} for retry"
                }
            
        except Exception as e:
            ErrorMsg = f"Failed to retry quality testing job {QueueId}: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "RetryQualityTestingJob")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg
            }
    
    def GetQualityTestingDetails(self, QueueId: int) -> Dict[str, Any]:
        """Get detailed information about a quality testing job."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingDetails", "QualityTestingViewModel", QueueId)
            
            # Get job details
            JobDetails = self.DatabaseManager.GetQualityTestingJobDetails(QueueId)
            
            if JobDetails:
                return {
                    "Success": True,
                    "JobDetails": {
                        "Id": JobDetails.Id,
                        "TranscodeAttemptId": JobDetails.TranscodeAttemptId,
                        "OriginalFilePath": JobDetails.OriginalFilePath,
                        "TranscodedFilePath": JobDetails.TranscodedFilePath,
                        "FileName": JobDetails.FileName,
                        "Status": JobDetails.Status,
                        "Priority": JobDetails.Priority,
                        "DateAdded": JobDetails.DateAdded.isoformat() if JobDetails.DateAdded else None,
                        "DateStarted": JobDetails.DateStarted.isoformat() if JobDetails.DateStarted else None,
                        "DateCompleted": JobDetails.DateCompleted.isoformat() if JobDetails.DateCompleted else None,
                        "VMAFScore": JobDetails.VMAFScore,
                        "QualityThreshold": JobDetails.QualityThreshold,
                        "ErrorMessage": JobDetails.ErrorMessage,
                        "RetryCount": JobDetails.RetryCount,
                        "MaxRetries": JobDetails.MaxRetries,
                        "StrategyType": JobDetails.StrategyType,
                        "StrategyId": JobDetails.StrategyId,
                        "AlternativeProfileIds": JobDetails.AlternativeProfileIds,
                        "CustomSettings": JobDetails.CustomSettings,
                        "Results": JobDetails.Results,
                        "SelectedResultId": JobDetails.SelectedResultId
                    }
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Quality testing job {QueueId} not found"
                }
            
        except Exception as e:
            ErrorMsg = f"Failed to get quality testing details for job {QueueId}: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "QualityTestingViewModel", "GetQualityTestingDetails")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg
            }
    
    def PrivateCalculateJobProgress(self, Job: QualityTestingQueueModel) -> Dict[str, Any]:
        """Calculate progress for a quality testing job using real progress data."""
        try:
            if not Job.DateStarted:
                return {"ProgressPercentage": 0, "Percentage": 0, "Status": "Pending", "ETA": "Unknown"}
            
            if Job.Status == "Completed":
                return {"ProgressPercentage": 100, "Percentage": 100, "Status": "Completed", "ETA": "Complete"}
            elif Job.Status == "Failed":
                return {"ProgressPercentage": 0, "Percentage": 0, "Status": "Failed", "ETA": "Failed"}
            elif Job.Status == "Running":
                # Get real progress data from QualityTestProgress table
                ProgressData = self.DatabaseManager.GetQualityTestProgress(Job.Id, Job.TranscodeAttemptId)
                
                if ProgressData:
                    # Format percentage to remove decimal points
                    RawPercentage = ProgressData.get("ProgressPercentage", 0)
                    FormattedPercentage = int(round(RawPercentage))
                    
                    return {
                        "ProgressPercentage": FormattedPercentage,
                        "Percentage": FormattedPercentage,  # Keep both for compatibility
                        "Status": ProgressData.get("Status", "Running"),
                        "CurrentStep": ProgressData.get("CurrentStep", "Processing..."),
                        "StartTime": ProgressData.get("StartTime"),
                        "EndTime": ProgressData.get("EndTime"),
                        "ErrorMessage": ProgressData.get("ErrorMessage"),
                        "StrategyType": ProgressData.get("StrategyType"),
                        "ETA": ProgressData.get("ETA"),
                        "CurrentTime": ProgressData.get("CurrentTime"),
                        "CurrentFrame": ProgressData.get("CurrentFrame"),
                        "TotalFrames": ProgressData.get("TotalFrames"),
                        "ProcessingSpeed": ProgressData.get("ProcessingSpeed"),
                        "UpdatedAt": ProgressData.get("UpdatedAt")
                    }
                else:
                    # Fallback to time-based estimate if no progress data
                    ElapsedTime = datetime.now() - Job.DateStarted
                    EstimatedProgress = min(90, int((ElapsedTime.total_seconds() / 3600) * 20))  # Rough estimate
                    return {"ProgressPercentage": EstimatedProgress, "Percentage": EstimatedProgress, "Status": "Running", "CurrentStep": "Processing...", "ETA": "Unknown"}
            else:
                return {"ProgressPercentage": 0, "Percentage": 0, "Status": Job.Status or "Unknown", "ETA": "Unknown"}
                
        except Exception as e:
            LoggingService.LogException(f"Error calculating job progress: {str(e)}", e, "QualityTestingViewModel", "PrivateCalculateJobProgress")
            return {"ProgressPercentage": 0, "Percentage": 0, "Status": "Unknown", "ETA": "Unknown"}
