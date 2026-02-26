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
    
    def PopulateQueueFromMediaFiles(self, RootFolderPath: str = None, ProfileId: int = None, CompatibilityOnly: bool = False) -> Dict[str, Any]:
        """Populate transcoding queue from MediaFiles that have assigned profiles, ordered by largest disk space."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueFromMediaFiles", "QueueManagementBusinessService", RootFolderPath, ProfileId, CompatibilityOnly)

            # Remux path: only MKV files, no profile/resolution requirements
            if CompatibilityOnly:
                return self.PopulateQueueForRemux(RootFolderPath)

            # If RootFolderPath is provided, always use resolution filtering
            if RootFolderPath:
                if ProfileId is not None:
                    # Use selected profile for filtering
                    mediaFilesWithProfiles = self.GetMediaFilesByFolderAndResolutionFilter(RootFolderPath, ProfileId)
                    LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files matching resolution filter with selected profile", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                else:
                    # Use each file's assigned profile for filtering
                    mediaFilesWithProfiles = self.GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles(RootFolderPath)
                    LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files matching resolution filter using assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            else:
                # No folder specified, use existing behavior: get media files with assigned profiles, ordered by size (largest first)
                mediaFilesWithProfiles = self.GetMediaFilesWithProfilesOrderedBySize(RootFolderPath)
                LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            if not mediaFilesWithProfiles:
                if ProfileId is not None and RootFolderPath:
                    friendlyMessage = f"No media files found in folder '{RootFolderPath}' with resolution greater than the target resolution for the selected profile."
                elif RootFolderPath:
                    friendlyMessage = f"No media files found with assigned profiles in folder '{RootFolderPath}'. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                else:
                    friendlyMessage = "No media files found with assigned profiles. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                LoggingService.LogWarning("No media files found matching criteria", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                return {"Success": False, "ErrorMessage": friendlyMessage, "ItemsAdded": 0}
            
            # Get existing queue items to avoid duplicates
            existingQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            existingFilePaths = {item.FilePath for item in existingQueueItems}
            LoggingService.LogInfo(f"Found {len(existingFilePaths)} existing queue items", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            # Get files already successfully transcoded
            transcodeFiles = self.DatabaseManager.GetAllTranscodeFiles()
            successfullyTranscodedPaths = {tf.FilePath for tf in transcodeFiles if tf.SuccessfullyTranscoded}
            LoggingService.LogInfo(f"Found {len(successfullyTranscodedPaths)} already successfully transcoded files", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            
            # Import adaptive quality service for VMAF-based retranscode checks
            from Services.AdaptiveQualityService import AdaptiveQualityService
            adaptiveService = AdaptiveQualityService(self.DatabaseManager)
            
            itemsAdded = 0
            itemsSkipped = 0
            itemsSkippedDueToResolution = 0
            itemsSkippedDueToQuality = 0  # Track files skipped because VMAF >= 80
            
            for mediaFile in mediaFilesWithProfiles:
                # Skip if already in queue
                if mediaFile.FilePath in existingFilePaths:
                    itemsSkipped += 1
                    continue
                
                # Check if file was previously transcoded - if so, check VMAF for retranscode decision
                if mediaFile.FilePath in successfullyTranscodedPaths:
                    # Check if file should be retranscoded based on VMAF
                    shouldRetranscode, previousAttempt = adaptiveService.ShouldRetranscode(mediaFile.FilePath)
                    
                    if not shouldRetranscode:
                        # VMAF >= 80, quality already acceptable - skip retranscode
                        itemsSkipped += 1
                        itemsSkippedDueToQuality += 1
                        LoggingService.LogInfo(f"Skipping {mediaFile.FileName}: Quality already acceptable (VMAF >= 80)", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        continue
                    
                    # VMAF < 80, check if CRF adjustment would fail
                    if previousAttempt:
                        previousCRF = previousAttempt.get('Quality')
                        vmafScore = previousAttempt.get('VMAF')
                        
                        if previousCRF and vmafScore is not None and vmafScore < 80:
                            # Calculate what the adjusted CRF would be
                            adjustedCRF = adaptiveService.CalculateAdjustedCRF(previousCRF, vmafScore)
                            
                            # Validate adjustment
                            minCRF = 15
                            if adjustedCRF < minCRF:
                                # Cannot adjust further - log critical error and skip
                                errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"
                                
                                # Extract directory for ProblemFiles
                                directory = os.path.dirname(mediaFile.FilePath)
                                
                                # Log to ProblemFiles
                                problemFileId = self.DatabaseManager.AddProblemFile(
                                    mediaFile.FilePath,
                                    "CRF_Adjustment_Failed",
                                    f"CRF adjustment failed: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF} is below minimum threshold (15). Quality threshold unreachable."
                                )
                                
                                if problemFileId:
                                    LoggingService.LogError(f"Logged CRF adjustment failure to ProblemFiles (ID: {problemFileId}): {errorMsg}", 
                                                          "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                                
                                itemsSkipped += 1
                                continue
                    
                    # VMAF < 80 and CRF adjustment is valid - allow retranscode by continuing to add to queue
                    LoggingService.LogInfo(f"File {mediaFile.FileName} will be retranscoded: Previous VMAF < 80", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                # else: File not in successfullyTranscodedPaths, proceed with normal queue addition
                
                # Resolution filtering is already done when RootFolderPath is provided, so skip the check here
                # Only check resolution if no folder was specified (using old behavior)
                if not RootFolderPath:
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
                            
                    except Exception as e:
                        LoggingService.LogException(f"Error saving queue item for {mediaFile.FileName}", e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        continue
            
            # Add friendly message based on results
            skipDetails = []
            if itemsSkipped > 0:
                skipDetails.append(f"{itemsSkipped} files were skipped")
            if itemsSkippedDueToQuality > 0:
                skipDetails.append(f"{itemsSkippedDueToQuality} skipped (quality already acceptable - VMAF >= 80)")
            if itemsSkippedDueToResolution > 0:
                skipDetails.append(f"{itemsSkippedDueToResolution} skipped (resolution check)")
            
            skipMessage = ", ".join(skipDetails) if skipDetails else "no files were skipped"
            
            if itemsAdded == 0:
                if itemsSkipped == len(mediaFilesWithProfiles):
                    if itemsSkippedDueToQuality > 0:
                        friendlyMessage = f"All {len(mediaFilesWithProfiles)} media files with assigned profiles have acceptable quality (VMAF >= 80) or are already in the queue. No new items were added."
                    else:
                        friendlyMessage = f"All {len(mediaFilesWithProfiles)} media files with assigned profiles are already in the queue or have been successfully transcoded. No new items were added."
                else:
                    friendlyMessage = f"No new items were added to the queue. {skipMessage}."
            else:
                friendlyMessage = f"Successfully added {itemsAdded} items to the transcoding queue. {skipMessage}."
            
            result = {
                "Success": True,
                "ItemsEvaluated": len(mediaFilesWithProfiles),
                "ItemsAdded": itemsAdded,
                "ItemsSkipped": itemsSkipped,
                "ItemsSkippedDueToResolution": itemsSkippedDueToResolution,
                "ItemsSkippedDueToQuality": itemsSkippedDueToQuality,
                "Message": friendlyMessage
            }
            
            LoggingService.LogInfo(f"Queue population completed: {itemsAdded} added, {itemsSkipped} skipped (duplicate/transcoded), {itemsSkippedDueToQuality} skipped (quality acceptable), {itemsSkippedDueToResolution} skipped (resolution check) from {len(mediaFilesWithProfiles)} files with profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
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
    
    def GetMediaFilesByFolderAndResolutionFilter(self, RootFolderPath: str, ProfileId: int) -> List[MediaFileModel]:
        """
        Get media files in a folder that have resolution > target resolution for the specified profile.
        Updates all files in the folder to the selected profile, then returns files where resolution > target.
        
        Args:
            RootFolderPath: The root folder path to query
            ProfileId: The profile ID to use for resolution filtering
            
        Returns:
            List of MediaFileModel objects where resolution > target resolution
        """
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesByFolderAndResolutionFilter", "QueueManagementBusinessService", RootFolderPath, ProfileId)
            
            # Get the profile
            profile = self.DatabaseManager.GetProfileById(ProfileId)
            if not profile:
                LoggingService.LogError(f"Profile with ID {ProfileId} not found", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []
            
            # Get profile thresholds
            profileThresholds = self.DatabaseManager.GetThresholdsByProfileId(ProfileId)
            if not profileThresholds:
                LoggingService.LogWarning(f"No profile thresholds found for profile {profile.ProfileName}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []
            
            # Step 1: Get target resolution once from profile thresholds
            # Find a threshold with a valid TranscodeDownTo value (use first one found)
            targetResolution = None
            for threshold in profileThresholds:
                transcodeDownTo = threshold.TranscodeDownTo or ""
                if transcodeDownTo and transcodeDownTo.strip() != "" and transcodeDownTo.lower() != "no downscaling":
                    targetResolution = transcodeDownTo.strip()
                    break
            
            if not targetResolution:
                LoggingService.LogWarning(f"No valid TranscodeDownTo found in profile {profile.ProfileName} thresholds", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []
            
            LoggingService.LogInfo(f"Target resolution for profile {profile.ProfileName}: {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            
            # Normalize the root folder path to match database format (handle Z: vs Z:\)
            # Database paths use backslashes: Z:\Videos\Couple\...
            normalizedRootPath = RootFolderPath.replace('/', '\\').strip()
            # Handle drive letter without backslash (Z:Videos -> Z:\Videos)
            if len(normalizedRootPath) >= 2 and normalizedRootPath[1] == ':' and len(normalizedRootPath) > 2 and normalizedRootPath[2] != '\\':
                normalizedRootPath = normalizedRootPath[0:2] + '\\' + normalizedRootPath[2:]
            # Ensure path doesn't end with backslash for LIKE matching (we'll add % in the query)
            
            LoggingService.LogInfo(f"Normalized root folder path: '{RootFolderPath}' -> '{normalizedRootPath}'", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            
            # Step 2: Update all files in folder to selected profile (bulk update)
            filesUpdated = self.DatabaseManager.UpdateMediaFilesProfileByRootFolder(normalizedRootPath, ProfileId)
            LoggingService.LogInfo(f"Updated {filesUpdated} files in folder {normalizedRootPath} to profile {profile.ProfileName}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            
            # Step 3: Get all media files in the folder (they now all have the profile)
            allMediaFiles = self.DatabaseManager.GetMediaFilesByRootFolder(normalizedRootPath)
            LoggingService.LogInfo(f"Found {len(allMediaFiles)} media files in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            
            # Step 4: Simple loop - compare each file's resolution to target resolution
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingFiles = []
            
            for mediaFile in allMediaFiles:
                sourceResolution = mediaFile.Resolution or ""
                if not sourceResolution:
                    LoggingService.LogDebug(f"Skipping {mediaFile.FileName}: no resolution", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                    continue
                
                # Compare file resolution to target resolution
                comparison = resolutionService.CompareResolutions(sourceResolution, targetResolution)
                
                # If comparison cannot be determined, skip
                if comparison is None:
                    LoggingService.LogWarning(f"Cannot compare resolutions for {mediaFile.FileName}: source={sourceResolution}, target={targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                    continue
                
                # Only include files where resolution > target (comparison > 0)
                if comparison > 0:
                    matchingFiles.append(mediaFile)
                    LoggingService.LogDebug(f"Including {mediaFile.FileName}: {sourceResolution} > {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                else:
                    LoggingService.LogDebug(f"Skipping {mediaFile.FileName}: {sourceResolution} <= {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            
            # Sort by size (largest first)
            matchingFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            
            LoggingService.LogInfo(f"Found {len(matchingFiles)} media files with resolution > {targetResolution} for profile {profile.ProfileName} in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            return matchingFiles
            
        except Exception as e:
            LoggingService.LogException("Exception getting media files by folder and resolution filter", e, "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            return []
    
    def GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles(self, RootFolderPath: str) -> List[MediaFileModel]:
        """
        Get media files in a folder that have resolution > target resolution using each file's assigned profile.
        Only includes files that have an assigned profile and pass the resolution check.
        
        Args:
            RootFolderPath: The root folder path to query
            
        Returns:
            List of MediaFileModel objects that match the criteria
        """
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles", "QueueManagementBusinessService", RootFolderPath)
            
            # Get all media files in the folder
            allMediaFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderPath)
            LoggingService.LogInfo(f"Found {len(allMediaFiles)} media files in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
            
            matchingFiles = []
            
            for mediaFile in allMediaFiles:
                # Skip files without assigned profiles
                if not mediaFile.AssignedProfile or mediaFile.AssignedProfile.strip() == "":
                    LoggingService.LogInfo(f"Skipping {mediaFile.FileName}: no assigned profile", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
                    continue
                
                # Check resolution using the file's assigned profile
                shouldSkip, skipReason = self.ShouldSkipDueToResolution(mediaFile, mediaFile.AssignedProfile)
                if shouldSkip:
                    LoggingService.LogDebug(f"Skipping {mediaFile.FileName}: {skipReason}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
                    continue
                
                # File passed resolution check, include it
                matchingFiles.append(mediaFile)
            
            # Sort by size (largest first)
            matchingFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            
            LoggingService.LogInfo(f"Found {len(matchingFiles)} media files with resolution > target in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
            return matchingFiles
            
        except Exception as e:
            LoggingService.LogException("Exception getting media files by folder with resolution filter using assigned profiles", e, "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
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
    
    def PopulateQueueForRemux(self, RootFolderPath: str = None) -> Dict[str, Any]:
        """Populate queue with MKV files for remuxing (container change to MP4 only)."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueForRemux", "QueueManagementBusinessService", RootFolderPath)

            mkvFiles = self.GetMkvFilesForRemux(RootFolderPath)
            if not mkvFiles:
                friendlyMessage = f"No MKV files found{' in folder ' + RootFolderPath if RootFolderPath else ''} for remuxing."
                return {"Success": False, "ErrorMessage": friendlyMessage, "ItemsAdded": 0}

            # Get existing queue items - build lookup by FilePath
            existingQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            existingQueueByPath = {item.FilePath: item for item in existingQueueItems}

            itemsAdded = 0
            itemsUpdated = 0

            for mediaFile in mkvFiles:
                existingItem = existingQueueByPath.get(mediaFile.FilePath)

                if existingItem:
                    # File already in queue - switch to Remux if it's currently Transcode and still Pending
                    if existingItem.ProcessingMode != "Remux" and existingItem.Status == "Pending":
                        existingItem.ProcessingMode = "Remux"
                        self.DatabaseManager.SaveTranscodeQueueItem(existingItem)
                        itemsUpdated += 1
                        LoggingService.LogInfo(f"Switched queue item {existingItem.Id} ({mediaFile.FileName}) from Transcode to Remux", "QueueManagementBusinessService", "PopulateQueueForRemux")
                    continue

                queueItem = self.CreateRemuxQueueItem(mediaFile)
                if queueItem:
                    try:
                        itemId = self.DatabaseManager.SaveTranscodeQueueItem(queueItem)
                        LoggingService.LogInfo(f"Added remux queue item {itemId} for {mediaFile.FileName}", "QueueManagementBusinessService", "PopulateQueueForRemux")
                        itemsAdded += 1
                        existingQueueByPath[mediaFile.FilePath] = queueItem
                    except Exception as e:
                        LoggingService.LogException(f"Error saving remux queue item for {mediaFile.FileName}", e, "QueueManagementBusinessService", "PopulateQueueForRemux")

            details = []
            if itemsAdded > 0:
                details.append(f"{itemsAdded} added")
            if itemsUpdated > 0:
                details.append(f"{itemsUpdated} switched from Transcode to Remux")
            friendlyMessage = f"Remux queue: {', '.join(details)}." if details else "No changes needed - all MKV files already queued for remux."

            return {
                "Success": True,
                "ItemsAdded": itemsAdded,
                "ItemsUpdated": itemsUpdated,
                "Message": friendlyMessage
            }

        except Exception as e:
            errorMsg = f"Exception populating remux queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueForRemux")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}

    def GetMkvFilesForRemux(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get MKV media files eligible for remuxing, ordered by size (largest first)."""
        try:
            allMediaFiles = self.DatabaseManager.GetAllMediaFiles()

            # Filter to MKV files only
            mkvFiles = [mf for mf in allMediaFiles
                        if mf.FileName and mf.FileName.lower().endswith('.mkv')]

            # Filter by root folder if specified
            if RootFolderPath:
                normalizedRootPath = RootFolderPath.replace('\\', '/').rstrip('/')
                mkvFiles = [mf for mf in mkvFiles
                            if mf.FilePath.replace('\\', '/').startswith(normalizedRootPath)]

            # Sort by size (largest first)
            mkvFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)

            LoggingService.LogInfo(f"Found {len(mkvFiles)} MKV files for remux", "QueueManagementBusinessService", "GetMkvFilesForRemux")
            return mkvFiles

        except Exception as e:
            LoggingService.LogException("Exception getting MKV files for remux", e, "QueueManagementBusinessService", "GetMkvFilesForRemux")
            return []

    def CreateRemuxQueueItem(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item for remuxing (container change only)."""
        try:
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
                Priority=self.CalculatePriority(MediaFile),
                Status="Pending",
                ProcessingMode="Remux",
                DateAdded=datetime.now()
            )

            LoggingService.LogInfo(f"Created remux queue item for {fileName}", "QueueManagementBusinessService", "CreateRemuxQueueItem")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating remux queue item", e, "QueueManagementBusinessService", "CreateRemuxQueueItem")
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
    
    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None, StartTime: str = None, ForceAdd: bool = False) -> Dict[str, Any]:
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
            
            # Check if should skip due to resolution (allow "No downscaling" for manual assignment)
            # Only skip "No downscaling" if not manually assigned (ProfileId is None means batch processing)
            if not ForceAdd:
                skipNoDownscaling = ProfileId is None  # Only skip "No downscaling" if not manually assigned
                shouldSkip, skipReason = self.ShouldSkipDueToResolution(mediaFile, mediaFile.AssignedProfile, SkipNoDownscaling=skipNoDownscaling)
                if shouldSkip:
                    errorMsg = f"Cannot add {mediaFile.FileName} to queue: {skipReason}"
                    LoggingService.LogInfo(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                    return {"Success": False, "ErrorMessage": errorMsg, "CanOverride": True}
            else:
                LoggingService.LogWarning(f"Force adding {mediaFile.FileName} to queue (resolution check overridden)", "QueueManagementBusinessService", "AddJobToQueue")
            
            # Check for previous attempts and validate CRF adjustment
            from Services.AdaptiveQualityService import AdaptiveQualityService
            adaptiveService = AdaptiveQualityService(self.DatabaseManager)
            shouldRetranscode, previousAttempt = adaptiveService.ShouldRetranscode(mediaFile.FilePath)
            
            if not shouldRetranscode:
                # VMAF >= 80, quality already acceptable - skip retranscode
                skipMsg = f"Quality already acceptable (VMAF >= 80), skipping retranscode for {mediaFile.FileName}"
                LoggingService.LogInfo(skipMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {
                    "Success": True,
                    "Skipped": True,
                    "Message": "Quality already acceptable, skipping retranscode",
                    "FileName": mediaFile.FileName
                }
            
            # Check if CRF adjustment would fail
            if previousAttempt:
                previousCRF = previousAttempt.get('Quality')
                vmafScore = previousAttempt.get('VMAF')
                
                if previousCRF and vmafScore is not None and vmafScore < 80:
                    # Calculate what the adjusted CRF would be
                    adjustedCRF = adaptiveService.CalculateAdjustedCRF(previousCRF, vmafScore)
                    
                    # Validate adjustment
                    minCRF = 15
                    if adjustedCRF < minCRF:
                        # Cannot adjust further - log critical error
                        errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"
                        
                        # Extract directory for ProblemFiles
                        import os
                        directory = os.path.dirname(mediaFile.FilePath)
                        
                        # Log to ProblemFiles
                        problemFileId = self.DatabaseManager.AddProblemFile(
                            mediaFile.FilePath,
                            "CRF_Adjustment_Failed",
                            f"CRF adjustment failed: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF} is below minimum threshold (15). Quality threshold unreachable."
                        )
                        
                        if problemFileId:
                            LoggingService.LogError(f"Logged CRF adjustment failure to ProblemFiles (ID: {problemFileId}): {errorMsg}", 
                                                  "QueueManagementBusinessService", "AddJobToQueue")
                        
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
        """Remove a job from the transcoding queue. If the job is running, kill FFmpeg and clean up first."""
        try:
            LoggingService.LogFunctionEntry("RemoveJobFromQueue", "QueueManagementBusinessService", ItemId)

            # Get queue item to verify it exists
            queueItem = self.DatabaseManager.GetTranscodeQueueItemById(ItemId)
            if not queueItem:
                errorMsg = f"Queue item with ID {ItemId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # If job is running, kill FFmpeg and clean up associated records first
            if queueItem.Status == "Running":
                LoggingService.LogInfo(f"Cancelling running job {ItemId} ({queueItem.FileName}) before removal",
                                     "QueueManagementBusinessService", "RemoveJobFromQueue")
                self._CancelRunningJob(ItemId, queueItem)

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

    def _CancelRunningJob(self, JobId: int, QueueItem) -> None:
        """Kill the FFmpeg process and clean up database records for a running job."""
        try:
            # 1. Kill FFmpeg process via ActiveJobs PID
            activeJobs = self.DatabaseManager.GetActiveJobsByService("TranscodeService")
            for activeJob in activeJobs:
                if activeJob.get('QueueId') == JobId:
                    processId = activeJob.get('ProcessId')
                    if processId:
                        try:
                            from Services.ProcessManagementService import ProcessManagementService
                            ProcessManagementService().KillProcess(processId, Graceful=True)
                            LoggingService.LogInfo(f"Killed FFmpeg process {processId} for job {JobId}",
                                                 "QueueManagementBusinessService", "_CancelRunningJob")
                        except Exception as e:
                            LoggingService.LogException(f"Error killing FFmpeg process {processId}", e,
                                                      "QueueManagementBusinessService", "_CancelRunningJob")

                    # Mark ActiveJob as failed/cancelled
                    self.DatabaseManager.CompleteActiveJob(activeJob['Id'], False, "Cancelled by user - job removed from queue")
                    break

            # 2. Mark TranscodeAttempts as cancelled
            try:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    "UPDATE TranscodeAttempts SET Success = FALSE, ErrorMessage = 'Cancelled by user' WHERE LOWER(FilePath) = LOWER(%s) AND Success IS NULL",
                    (QueueItem.FilePath,)
                )
            except Exception as e:
                LoggingService.LogException(f"Error updating TranscodeAttempts for job {JobId}", e,
                                          "QueueManagementBusinessService", "_CancelRunningJob")

            # 3. Clean up TranscodeProgress records
            try:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    """DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN (
                        SELECT Id FROM TranscodeAttempts WHERE LOWER(FilePath) = LOWER(%s) AND Success = FALSE
                    )""",
                    (QueueItem.FilePath,)
                )
            except Exception as e:
                LoggingService.LogException(f"Error cleaning TranscodeProgress for job {JobId}", e,
                                          "QueueManagementBusinessService", "_CancelRunningJob")

            LoggingService.LogInfo(f"Cleaned up running job {JobId} ({QueueItem.FileName})",
                                 "QueueManagementBusinessService", "_CancelRunningJob")

        except Exception as e:
            LoggingService.LogException(f"Error cancelling running job {JobId}", e,
                                      "QueueManagementBusinessService", "_CancelRunningJob")
    
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
    
    def ShouldSkipDueToResolution(self, MediaFile: MediaFileModel, ProfileName: str, SkipNoDownscaling: bool = True) -> tuple[bool, str]:
        """
        Check if a media file should be skipped due to resolution being equal to or less than target.
        
        Args:
            MediaFile: The media file to check
            ProfileName: The assigned profile name
            SkipNoDownscaling: If True, skip files when profile has "No downscaling" setting. 
                              If False, allow transcoding even with "No downscaling" (for manual assignments).
                              Default: True (backward compatible behavior)
            
        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        try:
            LoggingService.LogFunctionEntry("ShouldSkipDueToResolution", "QueueManagementBusinessService", MediaFile.FileName, ProfileName)
            
            # Get profile by name first, then get thresholds by ProfileId
            allProfiles = self.DatabaseManager.GetAllProfiles()
            matchingProfile = next((p for p in allProfiles if p.ProfileName == ProfileName), None)
            
            if not matchingProfile:
                reason = f"Profile {ProfileName} not found in database"
                LoggingService.LogError(f"Cannot determine resolution skip for {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason  # Skip on error - fail safe by not processing
            
            # Get profile thresholds for this file's resolution
            profileThresholds = self.DatabaseManager.GetThresholdsByProfileId(matchingProfile.Id)
            if not profileThresholds:
                reason = f"No profile thresholds found for profile {ProfileName}"
                LoggingService.LogError(f"Cannot determine resolution skip for {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason  # Skip on error - fail safe by not processing
            
            # Find matching threshold for the file's resolution
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingThreshold = resolutionService.FindMatchingThreshold(MediaFile.Resolution or "", profileThresholds)
            
            if not matchingThreshold:
                reason = f"No matching threshold found for resolution {MediaFile.Resolution} in profile {ProfileName}"
                LoggingService.LogError(f"Cannot determine resolution skip for {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason  # Skip on error - fail safe by not processing
            
            # Get the target resolution (TranscodeDownTo)
            targetResolution = matchingThreshold.TranscodeDownTo or ""
            
            # Handle "No downscaling" case - only skip if SkipNoDownscaling is True (batch processing)
            # When SkipNoDownscaling is False (manual assignment), allow transcoding even with "No downscaling"
            if SkipNoDownscaling and (not targetResolution or targetResolution.strip() == "" or targetResolution.lower() == "no downscaling"):
                reason = f"Profile {ProfileName} has 'No downscaling' setting - no benefit to transcode"
                LoggingService.LogInfo(f"Skipped {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason
            
            # Compare source vs target resolution
            sourceResolution = MediaFile.Resolution or ""
            comparison = resolutionService.CompareResolutions(sourceResolution, targetResolution)
            
            # If comparison cannot be determined, skip to be safe
            if comparison is None:
                reason = f"Cannot compare resolutions: source={sourceResolution}, target={targetResolution}"
                LoggingService.LogError(f"Cannot determine resolution skip for {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason  # Skip on error - fail safe by not processing
            
            if comparison <= 0:  # Source <= target
                reason = f"Source resolution {sourceResolution} is <= target resolution {targetResolution}"
                LoggingService.LogInfo(f"Skipped {MediaFile.FileName}: {reason}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
                return True, reason
            
            # Source > target, should transcode
            LoggingService.LogDebug(f"File {MediaFile.FileName} will be added to queue: source {sourceResolution} > target {targetResolution}", "QueueManagementBusinessService", "ShouldSkipDueToResolution")
            return False, ""
            
        except Exception as e:
            reason = f"Exception checking resolution skip: {str(e)}"
            LoggingService.LogException(f"Cannot determine resolution skip for {MediaFile.FileName}", e, "QueueManagementBusinessService", "ShouldSkipDueToResolution")
            return True, reason  # Skip on error - fail safe by not processing

    def GetMkvFileCount(self) -> int:
        """Get count of MKV files in the database."""
        try:
            mkvFiles = self.GetMkvFilesForRemux()
            return len(mkvFiles)
        except Exception as e:
            LoggingService.LogException("Exception getting MKV file count", e, "QueueManagementBusinessService", "GetMkvFileCount")
            return 0

    def PopulateQueueForSubtitleFix(self, FileIds: list = None) -> Dict[str, Any]:
        """Queue specific files (by MediaFile ID) or all eligible files for subtitle fix processing.
        Eligible = has ASS/SSA subtitle formats and is not already in queue."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueForSubtitleFix", "QueueManagementBusinessService", FileIds)

            if FileIds:
                # Queue specific files by ID
                mediaFiles = []
                for fileId in FileIds:
                    mf = self.DatabaseManager.GetMediaFileById(fileId)
                    if mf:
                        mediaFiles.append(mf)
            else:
                # Find all eligible files: SubtitleFormats contains ass or ssa
                mediaFiles = self._GetSubtitleFixEligibleFiles()

            if not mediaFiles:
                return {"Success": False, "ErrorMessage": "No eligible files found for subtitle fix.", "ItemsAdded": 0}

            # Get existing queue items to avoid duplicates
            existingQueueItems = self.DatabaseManager.GetAllTranscodeQueueItems()
            existingFilePaths = {item.FilePath for item in existingQueueItems}

            itemsAdded = 0
            itemsSkipped = 0

            for mediaFile in mediaFiles:
                if mediaFile.FilePath in existingFilePaths:
                    itemsSkipped += 1
                    continue

                queueItem = TranscodeQueueModel(
                    FilePath=mediaFile.FilePath,
                    FileName=mediaFile.FileName,
                    Directory=os.path.dirname(mediaFile.FilePath) if mediaFile.FilePath else '',
                    SizeBytes=int((mediaFile.SizeMB or 0) * 1024 * 1024),
                    SizeMB=mediaFile.SizeMB or 0.0,
                    Priority=self.CalculatePriority(mediaFile),
                    Status="Pending",
                    ProcessingMode="SubtitleFix",
                    DateAdded=datetime.now()
                )

                try:
                    itemId = self.DatabaseManager.SaveTranscodeQueueItem(queueItem)
                    LoggingService.LogInfo(f"Added subtitle fix queue item {itemId} for {mediaFile.FileName}", "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")
                    itemsAdded += 1
                    existingFilePaths.add(mediaFile.FilePath)
                except Exception as e:
                    LoggingService.LogException(f"Error saving subtitle fix queue item for {mediaFile.FileName}", e, "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")

            if itemsAdded > 0:
                friendlyMessage = f"Added {itemsAdded} files to queue for subtitle fix."
            else:
                friendlyMessage = "No new files added — all eligible files are already in the queue."
            if itemsSkipped > 0:
                friendlyMessage += f" {itemsSkipped} skipped (already queued)."

            return {"Success": True, "ItemsAdded": itemsAdded, "ItemsSkipped": itemsSkipped, "Message": friendlyMessage}

        except Exception as e:
            errorMsg = f"Exception populating subtitle fix queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}

    def _GetSubtitleFixEligibleFiles(self) -> List[MediaFileModel]:
        """Find MediaFiles where SubtitleFormats contains ASS or SSA (burn-in candidates)."""
        try:
            allMediaFiles = self.DatabaseManager.GetAllMediaFiles()
            burnInCodecs = {'ass', 'ssa'}
            eligible = []
            for mf in allMediaFiles:
                subFormats = (mf.SubtitleFormats or "").lower()
                if any(codec in subFormats for codec in burnInCodecs):
                    eligible.append(mf)
            eligible.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            LoggingService.LogInfo(f"Found {len(eligible)} files eligible for subtitle fix", "QueueManagementBusinessService", "_GetSubtitleFixEligibleFiles")
            return eligible
        except Exception as e:
            LoggingService.LogException("Exception getting subtitle fix eligible files", e, "QueueManagementBusinessService", "_GetSubtitleFixEligibleFiles")
            return []

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
