from typing import List, Optional, Dict, Any
from datetime import datetime
import os
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.TranscodeProfileModel import TranscodeProfileModel
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.FileManagerService import FileManagerService


class QueueManagementBusinessService:
    """Handles transcoding queue operations and population logic."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerService()
    
    def PopulateQueueFromMediaFiles(self, MaxItems: int = 10, RootFolderPath: str = None) -> Dict[str, Any]:
        """Populate transcoding queue from MediaFiles that have assigned profiles, ordered by largest disk space."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueFromMediaFiles", "QueueManagementBusinessService", MaxItems, RootFolderPath)
            
            # Get media files with assigned profiles, ordered by size (largest first)
            mediaFilesWithProfiles = self.GetMediaFilesWithProfilesOrderedBySize(RootFolderPath)
            LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            if not mediaFilesWithProfiles:
                if RootFolderPath:
                    friendlyMessage = f"No media files found with assigned profiles in folder '{RootFolderPath}'. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                else:
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
            itemsSkippedDueToResolution = 0
            
            for mediaFile in mediaFilesWithProfiles:
                # Skip if already in queue or already successfully transcoded
                if mediaFile.FilePath in existingFilePaths or mediaFile.FilePath in successfullyTranscodedPaths:
                    itemsSkipped += 1
                    continue
                
                # Check if should skip due to resolution
                shouldSkip, skipReason = self.ShouldSkipDueToResolution(mediaFile, mediaFile.AssignedProfile)
                if shouldSkip:
                    itemsSkippedDueToResolution += 1
                    LoggingService.LogInfo(f"Skipped {mediaFile.FileName} due to resolution: {skipReason}", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
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
                    friendlyMessage = f"No new items were added to the queue. {itemsSkipped} files were skipped (already in queue or transcoded), {itemsSkippedDueToResolution} files were skipped (resolution check)."
            else:
                friendlyMessage = f"Successfully added {itemsAdded} items to the transcoding queue. {itemsSkipped} files were skipped (already in queue or transcoded), {itemsSkippedDueToResolution} files were skipped (resolution check)."
            
            result = {
                "Success": True,
                "ItemsEvaluated": len(mediaFilesWithProfiles),
                "ItemsAdded": itemsAdded,
                "ItemsSkipped": itemsSkipped,
                "ItemsSkippedDueToResolution": itemsSkippedDueToResolution,
                "MaxItems": MaxItems,
                "Message": friendlyMessage
            }
            
            LoggingService.LogInfo(f"Queue population completed: {itemsAdded} added, {itemsSkipped} skipped (duplicate/transcoded), {itemsSkippedDueToResolution} skipped (resolution check) from {len(mediaFilesWithProfiles)} files with profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            return result
            
        except Exception as e:
            errorMsg = f"Exception populating queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}
    
    def GetMediaFilesWithProfilesOrderedBySize(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get media files that have assigned profiles, ordered by size (largest first)."""
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesWithProfilesOrderedBySize", "QueueManagementBusinessService", RootFolderPath)
            
            # Get all media files
            allMediaFiles = self.DatabaseManager.GetAllMediaFiles()
            
            # Filter to only files with assigned profiles
            filesWithProfiles = [mf for mf in allMediaFiles if mf.AssignedProfile and mf.AssignedProfile.strip()]
            
            # If RootFolderPath is specified, filter to only files in that folder
            if RootFolderPath:
                # Normalize the root folder path for comparison
                normalizedRootPath = RootFolderPath.replace('\\', '/').rstrip('/')
                filesWithProfiles = [mf for mf in filesWithProfiles 
                                   if mf.FilePath.replace('\\', '/').startswith(normalizedRootPath)]
                LoggingService.LogInfo(f"Filtered to {len(filesWithProfiles)} files in folder: {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            
            # Sort by size (largest first)
            filesWithProfiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            
            LoggingService.LogInfo(f"Found {len(filesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return filesWithProfiles
            
        except Exception as e:
            LoggingService.LogException("Exception getting media files with profiles", e, "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return []
    
    def CreateQueueItemFromMediaFileSimple(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item directly from a media file without threshold matching."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileSimple", "QueueManagementBusinessService", MediaFile.FileName)
            
            # Create queue item with basic information
            queueItem = TranscodeQueueModel(
                FilePath=MediaFile.FilePath,
                FileName=MediaFile.FileName,
                Directory=os.path.dirname(MediaFile.FilePath) if MediaFile.FilePath else '',
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0,
                Priority=self.CalculatePriority(MediaFile),
                Status='Pending',
                DateAdded=datetime.now()
            )
            
            LoggingService.LogInfo(f"Created simple queue item for {MediaFile.FileName}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return queueItem
            
        except Exception as e:
            LoggingService.LogException("Exception creating simple queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return None
    
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
    
    def FindMatchingProfileThreshold(self, MediaFile: MediaFileModel, ProfileThresholds: List[ProfileThresholdModel], AllowAssignedProfile: bool = False) -> Optional[ProfileThresholdModel]:
        """Find the best matching profile threshold for a media file."""
        try:
            LoggingService.LogFunctionEntry("FindMatchingProfileThreshold", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.Resolution)
            
            # Use ResolutionService to find matching threshold
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingThreshold = resolutionService.FindMatchingThreshold(MediaFile.Resolution or "", ProfileThresholds)
            
            # If no exact match and this is a manually assigned profile, use the first available threshold
            if not matchingThreshold and AllowAssignedProfile:
                LoggingService.LogInfo(f"No exact resolution match found for {MediaFile.Resolution}, using first available threshold for manually assigned profile", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                matchingThreshold = ProfileThresholds[0] if ProfileThresholds else None
            
            if not matchingThreshold:
                LoggingService.LogDebug(f"No thresholds found for resolution {MediaFile.Resolution}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                return None
            
            # Check if the matching threshold meets the criteria
            durationMinutes = MediaFile.DurationMinutes or 0
            if self.EvaluateThresholdCriteria(MediaFile, matchingThreshold, durationMinutes, AllowAssignedProfile):
                LoggingService.LogInfo(f"Found matching threshold for {MediaFile.FileName}: {matchingThreshold.ProfileId} (Resolution: {matchingThreshold.Resolution}, TranscodeDownTo: {matchingThreshold.TranscodeDownTo})", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                return matchingThreshold
            
            LoggingService.LogDebug(f"No matching threshold found for {MediaFile.FileName}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception finding matching profile threshold", e, "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None
    
    
    def EvaluateThresholdCriteria(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel, DurationMinutes: float, AllowAssignedProfile: bool = False) -> bool:
        """Evaluate if a media file meets the threshold criteria for transcoding."""
        try:
            LoggingService.LogFunctionEntry("EvaluateThresholdCriteria", "QueueManagementBusinessService", MediaFile.FileName, DurationMinutes, Threshold.ProfileId)
            
            # Check 1: Skip if already transcoded by MediaVortex
            if MediaFile.TranscodedByMediaVortex:
                LoggingService.LogDebug(f"Skipped {MediaFile.FileName}: already transcoded by MediaVortex", 
                                       "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                return False
            
            # Check 2: Skip if source resolution <= target resolution
            try:
                # Get profile name from ProfileId
                profile = self.DatabaseManager.GetProfileById(Threshold.ProfileId)
                if profile and profile.ProfileName:
                    shouldSkip, reason = self.ShouldSkipDueToResolution(MediaFile, profile.ProfileName)
                    if shouldSkip:
                        LoggingService.LogDebug(f"Skipped {MediaFile.FileName}: {reason}", 
                                               "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                        return False
                else:
                    LoggingService.LogWarning(f"Could not get profile name for ProfileId {Threshold.ProfileId}, skipping resolution check", 
                                            "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            except Exception as e:
                LoggingService.LogException("Exception checking resolution skip", e, "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                # Continue with other checks if resolution check fails
            
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
            
            # Allow files with assigned profiles if explicitly requested (for manual profile selection)
            profileCheck = not hasAssignedProfile if not AllowAssignedProfile else True
            
            result = meetsSizeThreshold and hasCompressionPotential and profileCheck
            
            LoggingService.LogDebug(f"Threshold evaluation for {MediaFile.FileName}: size={fileSizeMB}MB vs {thresholdSize}MB, compression={compressionPotential}, assigned={hasAssignedProfile}, allowAssigned={AllowAssignedProfile} -> {result}", "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            
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
        """Calculate priority for a queue item based on file size (largest first)."""
        try:
            LoggingService.LogFunctionEntry("CalculatePriority", "QueueManagementBusinessService", MediaFile.FileName)
            
            # Use file size directly as priority (larger files = higher priority)
            sizeMB = MediaFile.SizeMB or 0
            priority = int(sizeMB)  # Convert to integer for priority
            
            LoggingService.LogDebug(f"Calculated priority {priority} for {MediaFile.FileName} (size: {sizeMB}MB)", "QueueManagementBusinessService", "CalculatePriority")
            return priority
            
        except Exception as e:
            LoggingService.LogException("Exception calculating priority", e, "QueueManagementBusinessService", "CalculatePriority")
            return 0  # Default priority for files with no size
    
    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None, StartTime: str = None) -> Dict[str, Any]:
        """Add a specific media file to the transcoding queue. Simple logic: if it has a profile or user selects one, add it."""
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
            
            # Handle profile assignment if ProfileId is provided (user selected a profile)
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
            
            # Check if file has a profile (either existing or just assigned)
            if not mediaFile.AssignedProfile or mediaFile.AssignedProfile.strip() == '':
                errorMsg = f"File {mediaFile.FileName} has no profile assigned. Please select a profile first."
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Check if should skip due to resolution
            shouldSkip, skipReason = self.ShouldSkipDueToResolution(mediaFile, mediaFile.AssignedProfile)
            if shouldSkip:
                errorMsg = f"Cannot add {mediaFile.FileName} to queue: {skipReason}"
                LoggingService.LogInfo(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Create queue item directly from media file (no threshold matching needed)
            queueItem = self.CreateQueueItemFromMediaFileSimple(mediaFile)
            if not queueItem:
                errorMsg = f"Failed to create queue item for {mediaFile.FileName}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Override priority if specified, or add bonus for manual addition
            if Priority is not None:
                queueItem.Priority = Priority
            else:
                # Add 15 points to priority for manual addition via + button
                queueItem.Priority = min(100, queueItem.Priority + 15)
                LoggingService.LogInfo(f"Added manual addition bonus (+15) to priority for {mediaFile.FileName}. New priority: {queueItem.Priority}", "QueueManagementBusinessService", "AddJobToQueue")
            
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
            
            # Reduced logging verbosity for routine queue statistics
            return statistics
            
        except Exception as e:
            LoggingService.LogException("Exception getting queue statistics", e, "QueueManagementBusinessService", "GetQueueStatistics")
            return {}
    
    def ShouldSkipDueToResolution(self, MediaFile: MediaFileModel, ProfileName: str) -> tuple[bool, str]:
        """
        Check if a media file should be skipped due to resolution being equal to or less than target.
        
        Args:
            MediaFile: The media file to check
            ProfileName: The assigned profile name
            
        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        try:
            LoggingService.LogFunctionEntry("ShouldSkipDueToResolution", "QueueManagementBusinessService", MediaFile.FileName, ProfileName)
            
            # Get profile thresholds for this file's resolution
            profileThresholds = self.DatabaseManager.GetProfileThresholdsByProfileName(ProfileName)
            if not profileThresholds:
                LoggingService.LogWarning(f"No profile thresholds found for profile {ProfileName}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return False, ""  # Allow to queue (fail-safe)
            
            # Find matching threshold for the file's resolution
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingThreshold = resolutionService.FindMatchingThreshold(MediaFile.Resolution or "", profileThresholds)
            
            if not matchingThreshold:
                LoggingService.LogWarning(f"No matching threshold found for resolution {MediaFile.Resolution} in profile {ProfileName}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return False, ""  # Allow to queue (fail-safe)
            
            # Get the target resolution (TranscodeDownTo)
            targetResolution = matchingThreshold.TranscodeDownTo or ""
            
            # Handle "No downscaling" case
            if not targetResolution or targetResolution.strip() == "" or targetResolution.lower() == "no downscaling":
                reason = f"Profile {ProfileName} has 'No downscaling' setting - no benefit to transcode"
                LoggingService.LogInfo(f"Skipped {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason
            
            # Compare source vs target resolution
            sourceResolution = MediaFile.Resolution or ""
            comparison = resolutionService.CompareResolutions(sourceResolution, targetResolution)
            
            if comparison <= 0:  # Source <= target
                reason = f"Source resolution {sourceResolution} is <= target resolution {targetResolution}"
                LoggingService.LogInfo(f"Skipped {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason
            
            # Source > target, should transcode
            LoggingService.LogDebug(f"File {MediaFile.FileName} will be added to queue: source {sourceResolution} > target {targetResolution}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
            return False, ""
            
        except Exception as e:
            LoggingService.LogException("Exception checking resolution skip", e, "QueueManagementBusinessService", "ShouldSkipDueToResolution")
            return False, ""  # Allow to queue (fail-safe)

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
