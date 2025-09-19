from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.TranscodeProfileModel import TranscodeProfileModel
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class QueueManagementBusinessService:
    """Handles transcoding queue operations and population logic."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def PopulateQueueFromMediaFiles(self, MaxItems: int = 10) -> Dict[str, Any]:
        """Populate transcoding queue from MediaFiles that have assigned profiles, ordered by largest disk space."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueFromMediaFiles", "QueueManagementBusinessService", MaxItems)
            
            # Get media files with assigned profiles, ordered by size (largest first)
            mediaFilesWithProfiles = self.GetMediaFilesWithProfilesOrderedBySize()
            LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            if not mediaFilesWithProfiles:
                friendlyMessage = "No media files found with assigned profiles. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                LoggingService.LogWarning("No media files with assigned profiles found", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                return {"Success": False, "ErrorMessage": friendlyMessage, "ItemsAdded": 0}
            
            # Get existing queue items to avoid duplicates
            existingQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            existingFilePaths = {item.FilePath for item in existingQueueItems}
            LoggingService.LogInfo(f"Found {len(existingFilePaths)} existing queue items", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            # Get files already successfully transcoded
            transcodeFiles = self.DatabaseManager.GetAllTranscodeFiles()
            successfullyTranscodedPaths = {tf.FilePath for tf in transcodeFiles if tf.SuccessfullyTranscoded}
            LoggingService.LogInfo(f"Found {len(successfullyTranscodedPaths)} already successfully transcoded files", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            itemsAdded = 0
            itemsSkipped = 0
            
            for mediaFile in mediaFilesWithProfiles:
                # Skip if already in queue or already successfully transcoded
                if mediaFile.FilePath in existingFilePaths or mediaFile.FilePath in successfullyTranscodedPaths:
                    itemsSkipped += 1
                    continue
                
                # Create queue item (no need to find threshold since profile is already assigned)
                queueItem = self.CreateQueueItemFromMediaFileWithProfile(mediaFile)
                if queueItem:
                    try:
                        itemId = self.DatabaseManager.SaveTranscodeQueueItem(queueItem)
                        LoggingService.LogInfo(f"Added queue item {itemId} for {mediaFile.FileName} (Size: {mediaFile.SizeMB:.1f}MB)", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        itemsAdded += 1
                        existingFilePaths.add(mediaFile.FilePath)  # Prevent duplicates in this run
                        
                        if itemsAdded >= MaxItems:
                            LoggingService.LogInfo(f"Reached maximum items limit ({MaxItems})", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                            break
                            
                    except Exception as e:
                        LoggingService.LogException(f"Error saving queue item for {mediaFile.FileName}", e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        continue
            
            # Add friendly message based on results
            if itemsAdded == 0:
                if itemsSkipped == len(mediaFilesWithProfiles):
                    friendlyMessage = f"All {len(mediaFilesWithProfiles)} media files with assigned profiles are already in the queue or have been successfully transcoded. No new items were added."
                else:
                    friendlyMessage = f"No new items were added to the queue. {itemsSkipped} files were skipped (already in queue or transcoded)."
            else:
                friendlyMessage = f"Successfully added {itemsAdded} items to the transcoding queue. {itemsSkipped} files were skipped (already in queue or transcoded)."
            
            result = {
                "Success": True,
                "ItemsEvaluated": len(mediaFilesWithProfiles),
                "ItemsAdded": itemsAdded,
                "ItemsSkipped": itemsSkipped,
                "MaxItems": MaxItems,
                "Message": friendlyMessage
            }
            
            LoggingService.LogInfo(f"Queue population completed: {itemsAdded} added, {itemsSkipped} skipped from {len(mediaFilesWithProfiles)} files with profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            return result
            
        except Exception as e:
            errorMsg = f"Exception populating queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}
    
    def GetMediaFilesWithProfilesOrderedBySize(self) -> List[MediaFileModel]:
        """Get media files that have assigned profiles, ordered by size (largest first)."""
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesWithProfilesOrderedBySize", "QueueManagementBusinessService")
            
            # Get all media files
            allMediaFiles = self.DatabaseManager.GetAllMediaFiles()
            
            # Filter to only files with assigned profiles
            filesWithProfiles = [mf for mf in allMediaFiles if mf.AssignedProfile and mf.AssignedProfile.strip()]
            
            # Sort by size (largest first)
            filesWithProfiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            
            LoggingService.LogInfo(f"Found {len(filesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return filesWithProfiles
            
        except Exception as e:
            LoggingService.LogException("Exception getting media files with profiles", e, "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return []
    
    def CreateQueueItemFromMediaFileWithProfile(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file that already has an assigned profile."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileWithProfile", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.AssignedProfile)
            
            # Calculate priority based on compression potential and file size
            priority = self.CalculatePriority(MediaFile)
            
            # Extract directory from file path
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""
            
            if filePath:
                pathParts = filePath.replace("\\", "/").split("/")
                if len(pathParts) > 1:
                    directory = "/".join(pathParts[:-1])
                fileName = pathParts[-1] if pathParts else ""
            
            queueItem = TranscodeQueueModel(
                FilePath=filePath,
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=priority,
                Status="Pending",
                DateAdded=datetime.now()
            )
            
            LoggingService.LogInfo(f"Created queue item for {fileName} with profile {MediaFile.AssignedProfile} and priority {priority}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile")
            return queueItem
            
        except Exception as e:
            LoggingService.LogException("Exception creating queue item from media file with profile", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile")
            return None
    
    def FindMatchingProfileThreshold(self, MediaFile: MediaFileModel, ProfileThresholds: List[ProfileThresholdModel]) -> Optional[ProfileThresholdModel]:
        """Find the best matching profile threshold for a media file."""
        try:
            LoggingService.LogFunctionEntry("FindMatchingProfileThreshold", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.Resolution)
            
            # Filter thresholds by resolution
            matchingThresholds = [pt for pt in ProfileThresholds if pt.Resolution == MediaFile.Resolution]
            
            if not matchingThresholds:
                LoggingService.LogDebug(f"No thresholds found for resolution {MediaFile.Resolution}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                return None
            
            # Find threshold based on duration
            durationMinutes = MediaFile.DurationMinutes or 0
            
            for threshold in matchingThresholds:
                # Check if file meets the threshold criteria
                if self.EvaluateThresholdCriteria(MediaFile, threshold, durationMinutes):
                    LoggingService.LogInfo(f"Found matching threshold for {MediaFile.FileName}: {threshold.ProfileId}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                    return threshold
            
            LoggingService.LogDebug(f"No matching threshold found for {MediaFile.FileName}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception finding matching profile threshold", e, "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None
    
    def EvaluateThresholdCriteria(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel, DurationMinutes: float) -> bool:
        """Evaluate if a media file meets the threshold criteria for transcoding."""
        try:
            LoggingService.LogFunctionEntry("EvaluateThresholdCriteria", "QueueManagementBusinessService", MediaFile.FileName, DurationMinutes, Threshold.ProfileId)
            
            # Check file size against threshold based on duration
            fileSizeMB = MediaFile.SizeMB or 0
            
            if DurationMinutes <= 30:
                thresholdSize = Threshold.Under30MinMB or 0
            elif DurationMinutes <= 65:
                thresholdSize = Threshold.Under65MinMB or 0
            else:
                thresholdSize = Threshold.Over65MinMB or 0
            
            # File should be larger than threshold to warrant transcoding
            meetsSizeThreshold = fileSizeMB > thresholdSize
            
            # Check compression potential
            compressionPotential = MediaFile.CompressionPotential or ""
            hasCompressionPotential = compressionPotential.lower() in ['high', 'medium', 'low']
            
            # Check if already has assigned profile (might indicate it was processed before)
            hasAssignedProfile = MediaFile.AssignedProfile and MediaFile.AssignedProfile.strip()
            
            result = meetsSizeThreshold and hasCompressionPotential and not hasAssignedProfile
            
            LoggingService.LogDebug(f"Threshold evaluation for {MediaFile.FileName}: size={fileSizeMB}MB vs {thresholdSize}MB, compression={compressionPotential}, assigned={hasAssignedProfile} -> {result}", "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Exception evaluating threshold criteria", e, "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            return False
    
    def CreateQueueItemFromMediaFile(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file and threshold."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFile", "QueueManagementBusinessService", MediaFile.FileName, Threshold.ProfileId)
            
            # Calculate priority based on compression potential and file size
            priority = self.CalculatePriority(MediaFile)
            
            # Extract directory from file path
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""
            
            if filePath:
                pathParts = filePath.replace("\\", "/").split("/")
                if len(pathParts) > 1:
                    directory = "/".join(pathParts[:-1])
                fileName = pathParts[-1] if pathParts else ""
            
            queueItem = TranscodeQueueModel(
                FilePath=filePath,
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=priority,
                Status="Pending",
                DateAdded=datetime.now()
            )
            
            LoggingService.LogInfo(f"Created queue item for {fileName} with priority {priority}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return queueItem
            
        except Exception as e:
            LoggingService.LogException("Exception creating queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return None
    
    def CalculatePriority(self, MediaFile: MediaFileModel) -> int:
        """Calculate priority for a queue item based on media file properties."""
        try:
            LoggingService.LogFunctionEntry("CalculatePriority", "QueueManagementBusinessService", MediaFile.FileName)
            
            priority = 50  # Base priority
            
            # Adjust based on compression potential
            compressionPotential = (MediaFile.CompressionPotential or "").lower()
            if compressionPotential == "high":
                priority += 30
            elif compressionPotential == "medium":
                priority += 15
            elif compressionPotential == "low":
                priority += 5
            
            # Adjust based on file size (larger files get higher priority)
            sizeMB = MediaFile.SizeMB or 0
            if sizeMB > 1000:  # > 1GB
                priority += 20
            elif sizeMB > 500:  # > 500MB
                priority += 10
            elif sizeMB > 100:  # > 100MB
                priority += 5
            
            # Adjust based on duration (longer files get higher priority)
            durationMinutes = MediaFile.DurationMinutes or 0
            if durationMinutes > 120:  # > 2 hours
                priority += 15
            elif durationMinutes > 60:  # > 1 hour
                priority += 10
            elif durationMinutes > 30:  # > 30 minutes
                priority += 5
            
            # Ensure priority is within reasonable bounds
            priority = max(1, min(100, priority))
            
            LoggingService.LogDebug(f"Calculated priority {priority} for {MediaFile.FileName} (compression: {compressionPotential}, size: {sizeMB}MB, duration: {durationMinutes}min)", "QueueManagementBusinessService", "CalculatePriority")
            return priority
            
        except Exception as e:
            LoggingService.LogException("Exception calculating priority", e, "QueueManagementBusinessService", "CalculatePriority")
            return 50  # Default priority
    
    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None) -> Dict[str, Any]:
        """Add a specific media file to the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("AddJobToQueue", "QueueManagementBusinessService", MediaFileId, Priority)
            
            # Get media file
            mediaFile = self.DatabaseManager.GetMediaFileById(MediaFileId)
            if not mediaFile:
                errorMsg = f"Media file with ID {MediaFileId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Check if already in queue
            existingQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            if any(item.FilePath == mediaFile.FilePath for item in existingQueueItems):
                errorMsg = f"File {mediaFile.FileName} is already in the transcoding queue"
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Check if already successfully transcoded
            transcodeFile = self.DatabaseManager.GetTranscodeFileByFilePath(mediaFile.FilePath)
            if transcodeFile and transcodeFile.SuccessfullyTranscoded:
                errorMsg = f"File {mediaFile.FileName} has already been successfully transcoded"
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Handle profile assignment if ProfileId is provided
            if ProfileId is not None:
                # Get the profile and update the media file's assigned profile
                profile = self.DatabaseManager.GetProfileById(ProfileId)
                if not profile:
                    errorMsg = f"Profile with ID {ProfileId} not found"
                    LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                    return {"Success": False, "ErrorMessage": errorMsg}
                
                # Update media file's assigned profile
                mediaFile.AssignedProfile = profile.ProfileName
                self.DatabaseManager.SaveMediaFile(mediaFile)
                LoggingService.LogInfo(f"Updated media file {mediaFile.FileName} to use profile {profile.ProfileName}", "QueueManagementBusinessService", "AddJobToQueue")
            
            # Get profile thresholds to find matching one
            profileThresholds = self.DatabaseManager.GetAllProfileThresholds()
            matchingThreshold = self.FindMatchingProfileThreshold(mediaFile, profileThresholds)
            
            if not matchingThreshold:
                errorMsg = f"No matching profile threshold found for {mediaFile.FileName}"
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Create queue item
            queueItem = self.CreateQueueItemFromMediaFile(mediaFile, matchingThreshold)
            if not queueItem:
                errorMsg = f"Failed to create queue item for {mediaFile.FileName}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Override priority if specified
            if Priority is not None:
                queueItem.Priority = Priority
            
            # Save to database
            itemId = self.DatabaseManager.SaveTranscodeQueueItem(queueItem)
            
            result = {
                "Success": True,
                "ItemId": itemId,
                "FileName": mediaFile.FileName,
                "Priority": queueItem.Priority
            }
            
            LoggingService.LogInfo(f"Added job {itemId} to queue for {mediaFile.FileName} with priority {queueItem.Priority}", "QueueManagementBusinessService", "AddJobToQueue")
            return result
            
        except Exception as e:
            errorMsg = f"Exception adding job to queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "AddJobToQueue")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def RemoveJobFromQueue(self, ItemId: int) -> Dict[str, Any]:
        """Remove a job from the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("RemoveJobFromQueue", "QueueManagementBusinessService", ItemId)
            
            # Get queue item to verify it exists
            queueItem = self.DatabaseManager.GetTranscodeQueueItemById(ItemId)
            if not queueItem:
                errorMsg = f"Queue item with ID {ItemId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Check if job is running
            if queueItem.Status == "Running":
                errorMsg = f"Cannot remove running job {ItemId}"
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Delete from database
            success = self.DatabaseManager.DeleteTranscodeQueueItem(ItemId)
            
            if success:
                result = {
                    "Success": True,
                    "ItemId": ItemId,
                    "FileName": queueItem.FileName
                }
                LoggingService.LogInfo(f"Removed job {ItemId} ({queueItem.FileName}) from queue", "QueueManagementBusinessService", "RemoveJobFromQueue")
                return result
            else:
                errorMsg = f"Failed to delete queue item {ItemId}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
                
        except Exception as e:
            errorMsg = f"Exception removing job from queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "RemoveJobFromQueue")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def PrioritizeJob(self, ItemId: int, NewPriority: int) -> Dict[str, Any]:
        """Update the priority of a queue item."""
        try:
            LoggingService.LogFunctionEntry("PrioritizeJob", "QueueManagementBusinessService", ItemId, NewPriority)
            
            # Validate priority range
            if NewPriority < 1 or NewPriority > 100:
                errorMsg = f"Priority must be between 1 and 100, got {NewPriority}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "PrioritizeJob")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Get queue item
            queueItem = self.DatabaseManager.GetTranscodeQueueItemById(ItemId)
            if not queueItem:
                errorMsg = f"Queue item with ID {ItemId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "PrioritizeJob")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Update priority
            oldPriority = queueItem.Priority
            queueItem.Priority = NewPriority
            
            self.DatabaseManager.SaveTranscodeQueueItem(queueItem)
            
            result = {
                "Success": True,
                "ItemId": ItemId,
                "OldPriority": oldPriority,
                "NewPriority": NewPriority,
                "FileName": queueItem.FileName
            }
            
            LoggingService.LogInfo(f"Updated priority for job {ItemId} ({queueItem.FileName}) from {oldPriority} to {NewPriority}", "QueueManagementBusinessService", "PrioritizeJob")
            return result
            
        except Exception as e:
            errorMsg = f"Exception prioritizing job: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PrioritizeJob")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQueueStatistics", "QueueManagementBusinessService")
            
            statistics = self.DatabaseManager.GetQueueStatistics()
            
            # Add additional business logic statistics
            allQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            
            # Calculate average priority
            if allQueueItems:
                totalPriority = sum(item.Priority for item in allQueueItems)
                statistics["AveragePriority"] = totalPriority / len(allQueueItems)
            else:
                statistics["AveragePriority"] = 0.0
            
            # Calculate total queue size in MB
            totalSizeMB = sum(item.SizeMB for item in allQueueItems)
            statistics["TotalQueueSizeMB"] = totalSizeMB
            statistics["TotalQueueSizeGB"] = totalSizeMB / 1024.0
            
            LoggingService.LogInfo(f"Queue statistics: {statistics.get('TotalJobs', 0)} total jobs, {statistics.get('QueueSize', 0)} active", "QueueManagementBusinessService", "GetQueueStatistics")
            return statistics
            
        except Exception as e:
            LoggingService.LogException("Exception getting queue statistics", e, "QueueManagementBusinessService", "GetQueueStatistics")
            return {}
    
    def GetNextJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next job to process from the queue."""
        try:
            LoggingService.LogFunctionEntry("GetNextJob", "QueueManagementBusinessService")
            
            # Get pending jobs ordered by priority and date
            pendingJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Pending")
            
            if not pendingJobs:
                LoggingService.LogInfo("No pending jobs in queue", "QueueManagementBusinessService", "GetNextJob")
                return None
            
            # Sort by priority (descending) then by date (ascending)
            pendingJobs.sort(key=lambda x: (-x.Priority, x.DateAdded))
            
            nextJob = pendingJobs[0]
            LoggingService.LogInfo(f"Next job: {nextJob.FileName} (ID: {nextJob.Id}, Priority: {nextJob.Priority})", "QueueManagementBusinessService", "GetNextJob")
            return nextJob
            
        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "QueueManagementBusinessService", "GetNextJob")
            return None
