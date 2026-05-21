from typing import List, Optional, Dict, Any
from datetime import datetime
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
from ViewModels.TranscodingViewModel import TranscodingViewModel
from Core.Logging.LoggingService import LoggingService


from Core.DateTimeHelpers import ToUtcIsoZ
class TranscodeQueueViewModel:
    """Manages transcoding queue UI state and operations."""

    def __init__(self, QueueManagementService: QueueManagementBusinessService = None,
                 TranscodingService: TranscodingViewModel = None):
        self.QueueManagementService = QueueManagementService or QueueManagementBusinessService()
        self.TranscodingService = TranscodingService or TranscodingViewModel()
        self.QueueItems = []
        self.QueueStatistics = {}
        self.IsLoading = False
        self.ErrorMessage = ""
        self.SuccessMessage = ""

    def LoadQueueItems(self, Page: int = 1, PageSize: int = 25, SortBy: str = "Priority", SortOrder: str = "DESC", Mode: str = None) -> Dict[str, Any]:
        """Load transcoding queue items with database-level pagination, sorting, optional ProcessingMode filter."""
        try:
            LoggingService.LogFunctionEntry("LoadQueueItems", "TranscodeQueueViewModel", Page, PageSize, SortBy, SortOrder, Mode)

            self.IsLoading = True
            self.ErrorMessage = ""

            # Use database-level pagination
            from Repositories.DatabaseManager import DatabaseManager
            from Core.Database.DatabaseService import DatabaseService
            db = DatabaseManager()
            pageItems, totalItems = db.GetTranscodeQueueItemsPaginated(Page, PageSize, SortBy, SortOrder, Mode)
            self.QueueItems = pageItems

            # Per-mode counts -- one cheap GROUP BY, drives the tab badges
            ModeCounts = {'Transcode': 0, 'Quick': 0, 'Remux': 0, 'AudioFix': 0}
            try:
                Rows = DatabaseService().ExecuteQuery(
                    "SELECT COALESCE(ProcessingMode, 'Transcode') AS Mode, COUNT(*) AS N FROM TranscodeQueue GROUP BY 1"
                )
                for Row in Rows:
                    Key = Row.get('Mode') or 'Transcode'
                    if Key in ModeCounts:
                        ModeCounts[Key] = Row.get('N', 0)
            except Exception:
                pass

            totalPages = (totalItems + PageSize - 1) // PageSize

            self.IsLoading = False

            result = {
                "Success": True,
                "QueueItems": [self.QueueItemToDict(item) for item in pageItems],
                "Count": len(pageItems),
                "TotalItems": totalItems,
                "TotalPages": totalPages,
                "CurrentPage": Page,
                "PageSize": PageSize,
                "SortBy": SortBy,
                "SortOrder": SortOrder,
                "Mode": Mode,
                "ModeCounts": ModeCounts
            }

            return result

        except Exception as e:
            self.IsLoading = False
            self.ErrorMessage = f"Error loading queue items: {str(e)}"
            LoggingService.LogException("Exception loading queue items", e, "TranscodeQueueViewModel", "LoadQueueItems")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def PopulateQueue(self, RootFolderPath: str = None, ProfileId: int = None, CompatibilityOnly: bool = False) -> Dict[str, Any]:
        """Populate the transcoding queue from MediaFiles."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueue", "TranscodeQueueViewModel", RootFolderPath, ProfileId, CompatibilityOnly)

            self.IsLoading = True
            self.ErrorMessage = ""
            self.SuccessMessage = ""

            # Populate queue using business service
            result = self.QueueManagementService.PopulateQueueFromMediaFiles(RootFolderPath, ProfileId, CompatibilityOnly)

            if result.get("Success", False):
                itemsAdded = result.get("ItemsAdded", 0)
                friendlyMessage = result.get("Message", f"Successfully added {itemsAdded} items to the queue")
                self.SuccessMessage = friendlyMessage

                # Reload queue items
                self.LoadQueueItems()

                LoggingService.LogInfo(f"Queue populated with {itemsAdded} items", "TranscodeQueueViewModel", "PopulateQueue")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to populate queue")
                LoggingService.LogError(self.ErrorMessage, "TranscodeQueueViewModel", "PopulateQueue")

            self.IsLoading = False
            return result

        except Exception as e:
            self.IsLoading = False
            self.ErrorMessage = f"Error populating queue: {str(e)}"
            LoggingService.LogException("Exception populating queue", e, "TranscodeQueueViewModel", "PopulateQueue")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None, StartTime: str = None, ForceAdd: bool = False) -> Dict[str, Any]:
        """Add a specific media file to the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("AddJobToQueue", "TranscodeQueueViewModel", MediaFileId, Priority)

            self.ErrorMessage = ""
            self.SuccessMessage = ""

            # Add job using business service
            result = self.QueueManagementService.AddJobToQueue(MediaFileId, Priority, ProfileId, StartTime, ForceAdd)

            if result.get("Success", False):
                fileName = result.get("FileName", "Unknown")
                self.SuccessMessage = f"Successfully added {fileName} to the queue"

                # Reload queue items
                self.LoadQueueItems()

                LoggingService.LogInfo(f"Added job for {fileName} to queue", "TranscodeQueueViewModel", "AddJobToQueue")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to add job to queue")
                LoggingService.LogError(self.ErrorMessage, "TranscodeQueueViewModel", "AddJobToQueue")

            return result

        except Exception as e:
            self.ErrorMessage = f"Error adding job to queue: {str(e)}"
            LoggingService.LogException("Exception adding job to queue", e, "TranscodeQueueViewModel", "AddJobToQueue")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def RemoveJobFromQueue(self, ItemId: int) -> Dict[str, Any]:
        """Remove a job from the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("RemoveJobFromQueue", "TranscodeQueueViewModel", ItemId)

            self.ErrorMessage = ""
            self.SuccessMessage = ""

            # Remove job using business service
            result = self.QueueManagementService.RemoveJobFromQueue(ItemId)

            if result.get("Success", False):
                fileName = result.get("FileName", "Unknown")
                self.SuccessMessage = f"Successfully removed {fileName} from the queue"

                # Reload queue items
                self.LoadQueueItems()

                LoggingService.LogInfo(f"Removed job {ItemId} ({fileName}) from queue", "TranscodeQueueViewModel", "RemoveJobFromQueue")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to remove job from queue")
                LoggingService.LogError(self.ErrorMessage, "TranscodeQueueViewModel", "RemoveJobFromQueue")

            return result

        except Exception as e:
            self.ErrorMessage = f"Error removing job from queue: {str(e)}"
            LoggingService.LogException("Exception removing job from queue", e, "TranscodeQueueViewModel", "RemoveJobFromQueue")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def PrioritizeJob(self, ItemId: int, NewPriority: int) -> Dict[str, Any]:
        """Update the priority of a queue item."""
        try:
            LoggingService.LogFunctionEntry("PrioritizeJob", "TranscodeQueueViewModel", ItemId, NewPriority)

            self.ErrorMessage = ""
            self.SuccessMessage = ""

            # Update priority using business service
            result = self.QueueManagementService.PrioritizeJob(ItemId, NewPriority)

            if result.get("Success", False):
                fileName = result.get("FileName", "Unknown")
                oldPriority = result.get("OldPriority", 0)
                newPriority = result.get("NewPriority", 0)
                self.SuccessMessage = f"Updated priority for {fileName} from {oldPriority} to {newPriority}"

                # Reload queue items
                self.LoadQueueItems()

                LoggingService.LogInfo(f"Updated priority for job {ItemId} ({fileName})", "TranscodeQueueViewModel", "PrioritizeJob")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to update job priority")
                LoggingService.LogError(self.ErrorMessage, "TranscodeQueueViewModel", "PrioritizeJob")

            return result

        except Exception as e:
            self.ErrorMessage = f"Error updating job priority: {str(e)}"
            LoggingService.LogException("Exception updating job priority", e, "TranscodeQueueViewModel", "PrioritizeJob")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def RemoveBySize(self, MaxSizeMB: float) -> Dict[str, Any]:
        """Remove all pending queue items smaller than the given size in MB."""
        try:
            LoggingService.LogFunctionEntry("RemoveBySize", "TranscodeQueueViewModel", MaxSizeMB)

            query = "DELETE FROM TranscodeQueue WHERE SizeMB < %s AND Status = 'Pending'"
            itemsRemoved = self.QueueManagementService.Repository.DatabaseService.ExecuteNonQuery(
                query, (MaxSizeMB,)
            )

            message = f"Removed {itemsRemoved} pending items smaller than {MaxSizeMB} MB"
            LoggingService.LogInfo(message, "TranscodeQueueViewModel", "RemoveBySize")

            return {
                "Success": True,
                "ItemsRemoved": itemsRemoved,
                "Message": message
            }

        except Exception as e:
            errorMsg = f"Error removing items by size: {str(e)}"
            LoggingService.LogException("Exception removing by size", e, "TranscodeQueueViewModel", "RemoveBySize")
            return {"Success": False, "ErrorMessage": errorMsg}

    def ClearQueue(self) -> Dict[str, Any]:
        """Clear all items from the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("ClearQueue", "TranscodeQueueViewModel")

            # Get current queue count for logging
            stats = self.QueueManagementService.GetQueueStatistics()
            currentCount = stats.get("QueueSize", 0)

            # Clear all queue items
            itemsCleared = self.QueueManagementService.Repository.ClearAllTranscodeQueueItems()

            if itemsCleared > 0:
                message = f"Successfully cleared {itemsCleared} items from the transcoding queue"
                self.SuccessMessage = message
                LoggingService.LogInfo(message, "TranscodeQueueViewModel", "ClearQueue")

                result = {
                    "Success": True,
                    "ItemsCleared": itemsCleared,
                    "Message": message
                }
            else:
                message = "No items were found in the queue to clear"
                self.SuccessMessage = message
                LoggingService.LogInfo(message, "TranscodeQueueViewModel", "ClearQueue")

                result = {
                    "Success": True,
                    "ItemsCleared": 0,
                    "Message": message
                }

            return result

        except Exception as e:
            self.ErrorMessage = f"Error clearing queue: {str(e)}"
            LoggingService.LogException("Exception clearing queue", e, "TranscodeQueueViewModel", "ClearQueue")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQueueStatistics", "TranscodeQueueViewModel")

            self.QueueStatistics = self.QueueManagementService.GetQueueStatistics()

            result = {
                "Success": True,
                "Statistics": self.QueueStatistics
            }

            return result

        except Exception as e:
            self.ErrorMessage = f"Error getting queue statistics: {str(e)}"
            LoggingService.LogException("Exception getting queue statistics", e, "TranscodeQueueViewModel", "GetQueueStatistics")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def GetMkvFileCount(self) -> Dict[str, Any]:
        """Get count of MKV files available for remuxing."""
        try:
            count = self.QueueManagementService.GetMkvFileCount()
            return {"Success": True, "MkvFileCount": count}
        except Exception as e:
            LoggingService.LogException("Exception getting MKV file count", e, "TranscodeQueueViewModel", "GetMkvFileCount")
            return {"Success": False, "MkvFileCount": 0, "ErrorMessage": str(e)}

    def QueueItemToDict(self, QueueItem: TranscodeQueueModel) -> Dict[str, Any]:
        """Convert a queue item to dictionary for JSON serialization."""
        try:
            # Helper function to safely format datetime
            def format_datetime(dt):
                if dt is None:
                    return None
                if isinstance(dt, str):
                    return dt  # Already a string, return as-is
                if hasattr(dt, 'isoformat'):
                    return ToUtcIsoZ(dt)
                return str(dt)

            return {
                "Id": QueueItem.Id,
                "FilePath": QueueItem.FilePath,
                "FileName": QueueItem.FileName,
                "Directory": QueueItem.Directory,
                "SizeBytes": QueueItem.SizeBytes,
                "SizeMB": QueueItem.SizeMB,
                "SizeGB": QueueItem.SizeGB,
                "Priority": QueueItem.Priority,
                "Status": QueueItem.Status,
                "DateAdded": format_datetime(QueueItem.DateAdded),
                "DateStarted": format_datetime(QueueItem.DateStarted),
                "DurationMinutes": QueueItem.DurationMinutes,
                "IsCompleted": QueueItem.IsCompleted,
                "IsFailed": QueueItem.IsFailed,
                "IsRunning": QueueItem.IsRunning,
                "IsPending": QueueItem.IsPending,
                "IsCancelled": QueueItem.IsCancelled,
                "ProcessingMode": QueueItem.ProcessingMode,
                "ClaimedBy": QueueItem.ClaimedBy
            }
        except Exception as e:
            LoggingService.LogException("Exception converting queue item to dict", e, "TranscodeQueueViewModel", "QueueItemToDict")
            return {}

    def ClearMessages(self):
        """Clear success and error messages."""
        self.SuccessMessage = ""
        self.ErrorMessage = ""

    def GetStatusCounts(self) -> Dict[str, int]:
        """Get count of items by status."""
        try:
            statusCounts = {}
            for item in self.QueueItems:
                status = item.Status
                statusCounts[status] = statusCounts.get(status, 0) + 1

            return statusCounts

        except Exception as e:
            LoggingService.LogException("Exception getting status counts", e, "TranscodeQueueViewModel", "GetStatusCounts")
            return {}
