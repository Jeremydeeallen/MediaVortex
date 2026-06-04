import os
from typing import List, Dict, Any
from Services.FileManagerService import FileManagerService
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Core.Logging.LoggingService import LoggingService
from Core.PathStorage import LastSegment, LocalGetSize


class DuplicateDetectionService:
    """Service for detecting and managing duplicate media files."""

    def __init__(self, RepositoryInstance: FileScanningRepository = None, FileManagerInstance: FileManagerService = None):
        self.Repository = RepositoryInstance or FileScanningRepository()
        self.FileManager = FileManagerInstance or FileManagerService()

    def FindDuplicateMediaFiles(self, RootFolderId: int) -> List[Dict[str, Any]]:
        """Find duplicate media files on disk based on file size and content."""
        try:
            LoggingService.LogInfo("Starting duplicate media file detection for root folder: {}", RootFolderId)

            # Get root folder path
            RootFolder = self.Repository.GetRootFolderById(RootFolderId)
            if not RootFolder:
                LoggingService.LogWarning("Root folder not found: {}", RootFolderId)
                return []

            # Get all files on disk
            FoundFiles = self.FileManager.ScanDirectory(RootFolder.RootFolder, True)
            LoggingService.LogInfo("Scanning {} files for duplicates", len(FoundFiles))

            # Group files by size (first pass - files with same size are potential duplicates)
            SizeGroups = {}
            for FilePath in FoundFiles:
                try:
                    FileSize = LocalGetSize(FilePath)
                    if FileSize not in SizeGroups:
                        SizeGroups[FileSize] = []
                    SizeGroups[FileSize].append(FilePath)
                except Exception as e:
                    LoggingService.LogException("Error getting file size: {}", e, FilePath)
                    continue

            # Find groups with multiple files (potential duplicates)
            DuplicateGroups = []
            for FileSize, Files in SizeGroups.items():
                if len(Files) > 1:
                    # Files with same size are potential duplicates
                    DuplicateGroups.append({
                        'Size': FileSize,
                        'Files': Files,
                        'Count': len(Files)
                    })
                    LoggingService.LogInfo("Found {} files with size {} bytes", len(Files), FileSize)

            LoggingService.LogInfo("Found {} potential duplicate groups", len(DuplicateGroups))
            return DuplicateGroups

        except Exception as e:
            LoggingService.LogException("Error finding duplicate media files", e)
            return []

    def CleanupDuplicateMediaFiles(self, RootFolderId: int, KeepBestQuality: bool = True) -> Dict[str, Any]:
        """Remove duplicate media files, keeping the best quality version."""
        try:
            LoggingService.LogInfo("Starting duplicate media file cleanup for root folder: {}", RootFolderId)

            # Find duplicate groups
            DuplicateGroups = self.FindDuplicateMediaFiles(RootFolderId)

            if not DuplicateGroups:
                LoggingService.LogInfo("No duplicate files found")
                return {'Success': True, 'Message': 'No duplicates found', 'DeletedCount': 0}

            DeletedCount = 0
            ProcessedGroups = 0

            for Group in DuplicateGroups:
                Files = Group['Files']
                LoggingService.LogInfo("Processing duplicate group with {} files", len(Files))

                if KeepBestQuality:
                    # Keep the file with the best quality indicators in the filename
                    BestFile = self.SelectBestQualityFile(Files)
                    FilesToDelete = [f for f in Files if f != BestFile]
                else:
                    # Keep the first file, delete the rest
                    BestFile = Files[0]
                    FilesToDelete = Files[1:]

                LoggingService.LogInfo("Keeping file: {}", BestFile)

                # Delete duplicate files
                JellyfinDeletes: List[Dict[str, str]] = []
                for FileToDelete in FilesToDelete:
                    try:
                        if os.path.exists(FileToDelete):
                            os.remove(FileToDelete)
                            LoggingService.LogInfo("Deleted duplicate file: {}", FileToDelete)
                            DeletedCount += 1

                            # Also remove from database if it exists
                            self.Repository.DeleteMediaFileByPath(FileToDelete)
                            JellyfinDeletes.append({'Path': FileToDelete, 'UpdateType': 'Deleted'})
                        else:
                            LoggingService.LogWarning("Duplicate file no longer exists: {}", FileToDelete)
                    except Exception as DeleteError:
                        LoggingService.LogException("Failed to delete duplicate file: {}", DeleteError, FileToDelete)

                if JellyfinDeletes:
                    try:
                        from Services.JellyfinNotifyService import NotifyJellyfin
                        NotifyJellyfin(JellyfinDeletes)
                    except Exception as NotifyEx:
                        LoggingService.LogException(
                            "Jellyfin notify swallowed at DuplicateDetection boundary",
                            NotifyEx, "DuplicateDetectionService", "CleanupDuplicateMediaFiles",
                        )

                ProcessedGroups += 1

            LoggingService.LogInfo("Cleaned up {} duplicate files from {} groups", DeletedCount, ProcessedGroups)

            return {
                'Success': True,
                'Message': f'Cleaned up {DeletedCount} duplicate files from {ProcessedGroups} groups',
                'DeletedCount': DeletedCount,
                'ProcessedGroups': ProcessedGroups
            }

        except Exception as e:
            LoggingService.LogException("Error cleaning up duplicate media files", e)
            return {'Success': False, 'Message': f'Error: {str(e)}', 'DeletedCount': 0}

    def SelectBestQualityFile(self, Files: List[str]) -> str:
        """Select the best quality file from a list of duplicates based on filename indicators."""
        try:
            # Quality indicators in order of preference
            QualityIndicators = [
                '4K', '2160p', '1080p', '720p', '480p', '360p',
                'BluRay', 'Blu-ray', 'BDRip', 'BRRip', 'HDTV', 'WEBRip', 'WEB-DL', 'DVDRip', 'TVRip'
            ]

            BestFile = Files[0]
            BestScore = 0

            for FilePath in Files:
                FileName = LastSegment(FilePath).lower()
                Score = 0

                # Check for quality indicators
                for i, Indicator in enumerate(QualityIndicators):
                    if Indicator.lower() in FileName:
                        Score += len(QualityIndicators) - i  # Higher score for better quality
                        break

                # Prefer files with more metadata (longer filenames often indicate more info)
                Score += len(FileName) * 0.1

                if Score > BestScore:
                    BestScore = Score
                    BestFile = FilePath

            return BestFile

        except Exception as e:
            LoggingService.LogException("Error selecting best quality file", e)
            return Files[0] if Files else ""

    def GetDuplicateReport(self, RootFolderId: int) -> Dict[str, Any]:
        """Generate a detailed report of duplicate files without deleting them."""
        try:
            LoggingService.LogInfo("Generating duplicate file report for root folder: {}", RootFolderId)

            DuplicateGroups = self.FindDuplicateMediaFiles(RootFolderId)

            if not DuplicateGroups:
                return {
                    'Success': True,
                    'Message': 'No duplicate files found',
                    'DuplicateGroups': [],
                    'TotalDuplicateFiles': 0,
                    'TotalWastedSpace': 0
                }

            TotalDuplicateFiles = 0
            TotalWastedSpace = 0
            DetailedGroups = []

            for Group in DuplicateGroups:
                Files = Group['Files']
                FileSize = Group['Size']
                WastedSpace = FileSize * (len(Files) - 1)  # Space wasted by duplicates

                # Determine which file would be kept
                BestFile = self.SelectBestQualityFile(Files)
                FilesToDelete = [f for f in Files if f != BestFile]

                DetailedGroup = {
                    'Size': FileSize,
                    'SizeMB': round(FileSize / (1024 * 1024), 2),
                    'Count': len(Files),
                    'BestFile': BestFile,
                    'FilesToDelete': FilesToDelete,
                    'WastedSpace': WastedSpace,
                    'WastedSpaceMB': round(WastedSpace / (1024 * 1024), 2),
                    'AllFiles': Files
                }

                DetailedGroups.append(DetailedGroup)
                TotalDuplicateFiles += len(FilesToDelete)
                TotalWastedSpace += WastedSpace

            return {
                'Success': True,
                'Message': f'Found {len(DuplicateGroups)} duplicate groups with {TotalDuplicateFiles} duplicate files',
                'DuplicateGroups': DetailedGroups,
                'TotalDuplicateFiles': TotalDuplicateFiles,
                'TotalWastedSpace': TotalWastedSpace,
                'TotalWastedSpaceMB': round(TotalWastedSpace / (1024 * 1024), 2),
                'TotalWastedSpaceGB': round(TotalWastedSpace / (1024 * 1024 * 1024), 2)
            }

        except Exception as e:
            LoggingService.LogException("Error generating duplicate file report", e)
            return {
                'Success': False,
                'Message': f'Error: {str(e)}',
                'DuplicateGroups': [],
                'TotalDuplicateFiles': 0,
                'TotalWastedSpace': 0
            }
