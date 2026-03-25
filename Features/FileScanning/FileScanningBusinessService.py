import os
import uuid
import re
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from Features.FileScanning.Models.RootFolderModel import RootFolderModel
from Core.Models.MediaFileModel import MediaFileModel
from Features.FileScanning.Models.SeasonModel import SeasonModel
from Features.FileScanning.Models.FileScanResultModel import FileScanResultModel
from Services.FileManagerService import FileManagerService
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Core.Logging.LoggingService import LoggingService


class FileScanningBusinessService:
    """Orchestrates the file scanning process and coordinates between services."""

    def __init__(self, RepositoryInstance=None, FileManagerInstance=None):
        self.Repository = RepositoryInstance or FileScanningRepository()
        self.FileManager = FileManagerInstance or FileManagerService()
        self.MediaProbeService = MediaProbeBusinessService()
        self.CurrentJobId = None
        self.ScanProgress = 0.0
        self.ScanResults = FileScanResultModel()
        self.ScanErrors = []
        self.IsScanning = False
        self.CurrentScanDirectory = ""

        # Check for existing running scans on startup
        self.CheckForExistingRunningScan()

    def CheckForExistingRunningScan(self):
        """Check for existing running scans and set CurrentJobId if found."""
        try:
            Query = "SELECT JobId FROM ScanJobs WHERE Status IN ('Pending', 'Running') ORDER BY StartTime DESC LIMIT 1"
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)
            if Result:
                self.CurrentJobId = Result[0]['JobId']
                LoggingService.LogInfo(f"Found existing running scan with JobId: {self.CurrentJobId}", 'FileScanningBusinessService', 'CheckForExistingRunningScan')
            else:
                LoggingService.LogInfo("No existing running scans found", 'FileScanningBusinessService', 'CheckForExistingRunningScan')
        except Exception as e:
            LoggingService.LogException("Error checking for existing running scans", e, 'FileScanningBusinessService', 'CheckForExistingRunningScan')

    def StartScanning(self, RootFolderPath: str, Recursive: bool = True, SkipDuplicateCleanup: bool = False) -> Dict[str, Any]:
        """Start scanning a root folder for media files directly in the main process."""
        try:
            LoggingService.LogFunctionEntry("StartScanning", 'FileScanningBusinessService', RootFolderPath, Recursive=Recursive)

            # Check if we can start a new scan (allow up to 2 concurrent scans)
            if not self.CanStartNewScan(MaxConcurrentScans=2):
                RunningCount = self.GetRunningScanCount()
                return {
                    'Success': False,
                    'Message': f'Maximum concurrent scans reached ({RunningCount}/2). Please wait for a scan to complete.',
                    'Error': 'MaxConcurrentScansReached'
                }

            # Validate the root folder path with detailed debugging
            LoggingService.LogInfo(f"Starting path validation for: '{RootFolderPath}'", 'FileScanningBusinessService', 'StartScanning')

            # Check if path is provided
            if not RootFolderPath:
                LoggingService.LogError("RootFolderPath is empty or None", 'FileScanningBusinessService', 'StartScanning')
                return {
                    'Success': False,
                    'Message': 'Root folder path is required',
                    'Error': 'EmptyPath'
                }

            # Normalize the path
            NormalizedPath = os.path.normpath(RootFolderPath)
            LoggingService.LogInfo(f"Normalized path: '{NormalizedPath}'", 'FileScanningBusinessService', 'StartScanning')

            # Check if path exists
            PathExists = os.path.exists(NormalizedPath)
            LoggingService.LogInfo(f"os.path.exists('{NormalizedPath}') = {PathExists}", 'FileScanningBusinessService', 'StartScanning')

            if not PathExists:
                # Additional debugging for failed path
                LoggingService.LogError(f"Path does not exist: '{NormalizedPath}'", 'FileScanningBusinessService', 'StartScanning')

                # Try alternative validation methods
                try:
                    ListDirResult = os.listdir(NormalizedPath)
                    LoggingService.LogInfo(f"os.listdir succeeded, found {len(ListDirResult)} items", 'FileScanningBusinessService', 'StartScanning')
                    PathExists = True  # Override if listdir works
                except Exception as e:
                    LoggingService.LogError(f"os.listdir also failed: {str(e)}", 'FileScanningBusinessService', 'StartScanning')

                if not PathExists:
                    return {
                        'Success': False,
                        'Message': f'Root folder does not exist: {RootFolderPath}',
                        'Error': 'InvalidPath'
                    }

            # Check if it's a directory
            IsDirectory = os.path.isdir(NormalizedPath)
            LoggingService.LogInfo(f"os.path.isdir('{NormalizedPath}') = {IsDirectory}", 'FileScanningBusinessService', 'StartScanning')

            if not IsDirectory:
                LoggingService.LogError(f"Path is not a directory: '{NormalizedPath}'", 'FileScanningBusinessService', 'StartScanning')
                return {
                    'Success': False,
                    'Message': f'Path is not a directory: {RootFolderPath}',
                    'Error': 'NotDirectory'
                }

            # Additional validation for network drives
            if len(NormalizedPath) >= 2 and NormalizedPath[1] == ':' and NormalizedPath[0].isalpha():
                LoggingService.LogInfo(f"Detected network drive: {NormalizedPath[0]}:", 'FileScanningBusinessService', 'StartScanning')
                try:
                    # Test if we can actually access the directory
                    TestFiles = os.listdir(NormalizedPath)
                    LoggingService.LogInfo(f"Network drive access test successful, found {len(TestFiles)} items", 'FileScanningBusinessService', 'StartScanning')
                except Exception as e:
                    LoggingService.LogError(f"Network drive access test failed: {str(e)}", 'FileScanningBusinessService', 'StartScanning')
                    return {
                        'Success': False,
                        'Message': f'Cannot access network drive: {RootFolderPath}',
                        'Error': 'NetworkDriveAccessFailed'
                    }

            LoggingService.LogInfo(f"Path validation successful for: '{NormalizedPath}'", 'FileScanningBusinessService', 'StartScanning')

            # Generate unique job ID
            JobId = str(uuid.uuid4())
            self.CurrentJobId = JobId

            # Create scan job record
            self.CreateScanJob(JobId, RootFolderPath, Recursive)

            # Set scanning state
            self.IsScanning = True
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = RootFolderPath

            LoggingService.LogInfo(f"Starting direct scan for {RootFolderPath}", 'FileScanningBusinessService', 'StartScanning')

            # Perform the scan directly
            result = self.PerformScan(RootFolderPath, Recursive, SkipDuplicateCleanup=SkipDuplicateCleanup)

            # Update job status based on result
            if result.get('Success', False):
                self.UpdateJobStatus(JobId, 'Completed', Progress=100.0, EndTime=datetime.now())
            else:
                self.UpdateJobStatus(JobId, 'Failed', ErrorMessage=result.get('Message', 'Unknown error'), EndTime=datetime.now())

            return result

        except Exception as e:
            LoggingService.LogException("Error starting scan", e, 'FileScanningBusinessService', 'StartScanning')
            return {
                'Success': False,
                'Message': f'Error starting scan: {str(e)}',
                'Error': 'ScanError'
            }

    def CreateScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool):
        """Create a new scan job record in the database."""
        try:
            Query = """
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated, ScanType)
            VALUES (%s, %s, %s, 'Running', %s, %s, 'File')
            """
            Now = datetime.now()
            self.Repository.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now))

        except Exception as e:
            LoggingService.LogException(f"Error creating scan job {JobId}", e, 'FileScanningBusinessService', 'CreateScanJob')
            raise

    def UpdateJobStatus(self, JobId: str, Status: str, Progress: float = None, CurrentDirectory: str = None,
                       ProcessId: str = None, StartTime: datetime = None, EndTime: datetime = None,
                       ErrorMessage: str = None, ScanResults: FileScanResultModel = None):
        """Update the status of a scan job."""
        try:
            UpdateFields = []
            UpdateValues = []

            if Status:
                UpdateFields.append("Status = %s")
                UpdateValues.append(Status)

            if Progress is not None:
                UpdateFields.append("Progress = %s")
                UpdateValues.append(Progress)

            if CurrentDirectory is not None:
                UpdateFields.append("CurrentDirectory = %s")
                UpdateValues.append(CurrentDirectory)

            if ProcessId is not None:
                UpdateFields.append("ProcessId = %s")
                UpdateValues.append(ProcessId)

            if StartTime is not None:
                UpdateFields.append("StartTime = %s")
                UpdateValues.append(StartTime)

            if EndTime is not None:
                UpdateFields.append("EndTime = %s")
                UpdateValues.append(EndTime)

            if ErrorMessage is not None:
                UpdateFields.append("ErrorMessage = %s")
                UpdateValues.append(ErrorMessage)

            if ScanResults is not None:
                UpdateFields.extend([
                    "TotalFiles = %s",
                    "ProcessedFiles = %s",
                    "SkippedFiles = %s",
                    "EncodingErrors = %s"
                ])
                UpdateValues.extend([
                    ScanResults.TotalFilesFound,
                    ScanResults.TotalFilesProcessed,
                    ScanResults.TotalFilesSkipped,
                    ScanResults.TotalFilesWithErrors
                ])

            # Always update LastUpdated
            UpdateFields.append("LastUpdated = %s")
            UpdateValues.append(datetime.now())

            # Add JobId for WHERE clause
            UpdateValues.append(JobId)

            Query = f"UPDATE ScanJobs SET {', '.join(UpdateFields)} WHERE JobId = %s"
            self.Repository.DatabaseService.ExecuteNonQuery(Query, UpdateValues)

        except Exception as e:
            LoggingService.LogException(f"Error updating job status for {JobId}", e, 'UpdateJobStatus', 'FileScanningBusinessService')


    def IsScanRunning(self) -> bool:
        """Check if there's currently a scan running."""
        try:
            # Check for any running scans in database
            Query = "SELECT COUNT(*) as Count FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)
            return Result[0]['Count'] > 0 if Result else False

        except Exception as e:
            LoggingService.LogException("Error checking scan status", e)
            return False

    def GetRunningScanCount(self) -> int:
        """Get the number of currently running scans."""
        try:
            Query = "SELECT COUNT(*) as Count FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)
            return Result[0]['Count'] if Result else 0
        except Exception as e:
            LoggingService.LogException("Error getting running scan count", e)
            return 0

    def CanStartNewScan(self, MaxConcurrentScans: int = 2) -> bool:
        """Check if we can start a new scan based on concurrent scan limit."""
        try:
            RunningCount = self.GetRunningScanCount()
            return RunningCount < MaxConcurrentScans
        except Exception as e:
            LoggingService.LogException("Error checking if can start new scan", e)
            return False

    def GetScanJobStatus(self, JobId: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific scan job."""
        try:
            Query = """
            SELECT JobId, RootFolderPath, Recursive, Status, ProcessId, StartTime, EndTime,
                   Progress, CurrentDirectory, TotalFiles, ProcessedFiles, SkippedFiles,
                   EncodingErrors, NewFiles, UpdatedFiles, DeletedFiles, ErrorMessage, LastUpdated
            FROM ScanJobs WHERE JobId = %s
            """
            Result = self.Repository.DatabaseService.ExecuteQuery(Query, (JobId,))

            if Result:
                return Result[0]
            return None

        except Exception as e:
            LoggingService.LogException(f"Error getting scan job status for {JobId}", e)
            return None

    def GetCurrentScanStatus(self) -> Dict[str, Any]:
        """Get the status of all running scan jobs."""
        try:
            # Get all running scans
            RunningScans = self.GetAllRunningScans()

            if not RunningScans:
                return {
                    'Success': True,
                    'IsScanning': False,
                    'Progress': 0.0,
                    'CurrentDirectory': '',
                    'RootFolderPath': '',
                    'Results': FileScanResultModel(),
                    'Errors': [],
                    'RunningScans': [],
                    'TotalRunningScans': 0
                }

            # For backward compatibility, use the first running scan as the "primary" status
            PrimaryScan = RunningScans[0]
            IsScanning = True

            # Create FileScanResultModel from primary scan
            Results = FileScanResultModel()
            Results.Id = PrimaryScan['JobId']
            Results.RootFolderId = None  # Will be set by the scan process
            Results.ScanStartTime = PrimaryScan['StartTime']
            Results.ScanEndTime = PrimaryScan['EndTime']
            Results.TotalFilesFound = PrimaryScan['TotalFiles'] or 0
            Results.TotalFilesProcessed = PrimaryScan['ProcessedFiles'] or 0
            Results.TotalFilesSkipped = PrimaryScan['SkippedFiles'] or 0
            Results.TotalFilesWithErrors = PrimaryScan['EncodingErrors'] or 0
            Results.ScanStatus = PrimaryScan['Status']
            Results.ErrorMessage = PrimaryScan['ErrorMessage']
            Results.ProcessId = PrimaryScan['ProcessId']

            Errors = [PrimaryScan['ErrorMessage']] if PrimaryScan['ErrorMessage'] else []

            # Sync instance state with database state (use primary scan)
            self.IsScanning = IsScanning
            self.ScanProgress = PrimaryScan['Progress'] or 0.0
            self.CurrentScanDirectory = PrimaryScan['CurrentDirectory'] or ''

            return {
                'Success': True,
                'IsScanning': IsScanning,
                'Progress': PrimaryScan['Progress'] or 0.0,
                'CurrentDirectory': PrimaryScan['CurrentDirectory'] or '',
                'RootFolderPath': PrimaryScan['RootFolderPath'] or '',
                'Results': Results,
                'Errors': Errors,
                'Status': PrimaryScan['Status'],
                'JobId': PrimaryScan['JobId'],
                'ProcessId': PrimaryScan['ProcessId'],
                'RunningScans': RunningScans,
                'TotalRunningScans': len(RunningScans)
            }

        except Exception as e:
            LoggingService.LogException("Error getting current scan status", e)
            return {
                'Success': False,
                'IsScanning': False,
                'Progress': 0.0,
                'CurrentDirectory': '',
                'RootFolderPath': '',
                'Results': {},
                'Errors': [str(e)],
                'RunningScans': [],
                'TotalRunningScans': 0
            }

    def GetAllRunningScans(self) -> List[Dict[str, Any]]:
        """Get all currently running scan jobs."""
        try:
            Query = """
            SELECT JobId, RootFolderPath, Recursive, Status, StartTime, EndTime,
                   TotalFiles, ProcessedFiles, SkippedFiles, EncodingErrors,
                   Progress, CurrentDirectory, ErrorMessage, ProcessId, LastUpdated
            FROM ScanJobs
            WHERE Status IN ('Pending', 'Running')
            ORDER BY StartTime ASC
            """
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)

            if not Result:
                return []

            RunningScans = []
            for row in Result:
                scan_info = {
                    'JobId': row['JobId'],
                    'RootFolderPath': row['RootFolderPath'],
                    'Recursive': bool(row['Recursive']),
                    'Status': row['Status'],
                    'StartTime': row['StartTime'],
                    'EndTime': row['EndTime'],
                    'TotalFiles': row['TotalFiles'] or 0,
                    'ProcessedFiles': row['ProcessedFiles'] or 0,
                    'SkippedFiles': row['SkippedFiles'] or 0,
                    'EncodingErrors': row['EncodingErrors'] or 0,
                    'Progress': row['Progress'] or 0.0,
                    'CurrentDirectory': row['CurrentDirectory'] or '',
                    'ErrorMessage': row['ErrorMessage'],
                    'ProcessId': row['ProcessId'],
                    'LastUpdated': row['LastUpdated']
                }
                RunningScans.append(scan_info)

            return RunningScans

        except Exception as e:
            LoggingService.LogException("Error getting all running scans", e)
            return []

    def StopScanning(self) -> Dict[str, Any]:
        """Stop the current scanning process."""
        try:
            if not self.CurrentJobId:
                return {
                    'Success': False,
                    'Message': 'No scan is currently in progress',
                    'Error': 'NoScanInProgress'
                }

            # Update job status to stopped
            self.UpdateJobStatus(self.CurrentJobId, 'Stopped', EndTime=datetime.now())

            # Clear current job and update scanning state
            self.CurrentJobId = None
            self.IsScanning = False
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = ""

            LoggingService.LogInfo("Scan stopped by user request")

            return {
                'Success': True,
                'Message': 'Scan stopped successfully'
            }

        except Exception as e:
            LoggingService.LogException("Error stopping scan", e)
            return {
                'Success': False,
                'Message': f'Error stopping scan: {str(e)}',
                'Error': 'StopError'
            }

    def CleanupCompletedJobs(self):
        """Clean up old completed scan jobs."""
        try:
            # Delete jobs older than 7 days
            Query = """
            DELETE FROM ScanJobs
            WHERE Status IN ('Completed', 'Failed', 'Stopped')
            AND LastUpdated < NOW() - INTERVAL '7 days'
            """
            self.Repository.DatabaseService.ExecuteNonQuery(Query)
            LoggingService.LogInfo("Cleaned up old scan jobs")
        except Exception as e:
            LoggingService.LogException("Error cleaning up scan jobs", e)

    def PerformScan(self, RootFolderPath: str, Recursive: bool, SkipDuplicateCleanup: bool = False) -> Dict[str, Any]:
        """Perform the actual scanning process."""
        try:
            LoggingService.LogInfo("Starting scan of directory: {}", RootFolderPath)

            # Step 0: Clean up any existing duplicate records before scanning
            # Skipped during continuous scans where cleanup runs once before the loop
            if not SkipDuplicateCleanup:
                CleanupResult = self.Repository.CleanupDuplicateMediaFiles()
                if CleanupResult.get('DuplicatesRemoved', 0) > 0:
                    LoggingService.LogInfo(f"Pre-scan cleanup removed {CleanupResult['DuplicatesRemoved']} duplicate records", 'PerformScan', 'FileScanningBusinessService')

            # Step 1: Calculate directory size
            self.ScanProgress = 10.0
            TotalSizeGB = self.FileManager.CalculateDirectorySize(RootFolderPath)

            # Step 2: Get or create root folder record
            self.ScanProgress = 20.0
            RootFolder = self.GetOrCreateRootFolder(RootFolderPath, TotalSizeGB)

            if not RootFolder or not RootFolder.Id:
                LoggingService.LogError(f"Failed to create or get root folder for: {RootFolderPath}", 'PerformScan', 'FileScanningBusinessService')
                return {
                    'Success': False,
                    'Message': f'Failed to create root folder record for: {RootFolderPath}',
                    'Error': 'RootFolderCreationFailed'
                }

            # Step 3: Scan for media files
            self.ScanProgress = 30.0
            MediaFiles = self.FileManager.ScanDirectory(RootFolderPath, Recursive)
            self.ScanResults.TotalFilesFound = len(MediaFiles)
            self.ScanResults.RootFolderId = RootFolder.Id

            # Step 4: Process each media file (without metadata extraction for speed)
            self.ProcessMediaFiles(MediaFiles, RootFolder.Id, RootFolderPath, ExtractMetadata=False)

            # Step 5: Update scan results
            self.ScanProgress = 90.0
            self.UpdateScanResults()

            # Step 6: Complete scan
            self.ScanProgress = 100.0
            self.IsScanning = False

            LoggingService.LogInfo(f"Scan completed: {len(MediaFiles)} files found")

            # Step 7: Automatically trigger metadata extraction for the scanned files
            try:
                if RootFolder and RootFolder.Id:
                    LoggingService.LogInfo(f"Starting automatic metadata extraction for RootFolderId: {RootFolder.Id}", 'PerformScan', 'FileScanningBusinessService')
                    metadataResult = self.MediaProbeService.ProbeFilesNeedingMetadata(RootFolder.Id)
                else:
                    LoggingService.LogWarning("No RootFolderId available - skipping automatic metadata extraction", 'PerformScan', 'FileScanningBusinessService')
                    metadataResult = {'Success': True, 'Message': 'No RootFolderId - metadata extraction skipped', 'Processed': 0}
                if metadataResult.get('Success', False):
                    processedFiles = metadataResult.get('Processed', 0)
                    LoggingService.LogInfo(f"Metadata extraction completed: {processedFiles} files processed")
                else:
                    LoggingService.LogWarning(f"Metadata extraction failed: {metadataResult.get('Message', 'Unknown error')}")
            except Exception as e:
                LoggingService.LogException("Error during automatic metadata extraction", e, 'PerformScan', 'FileScanningBusinessService')

            return {
                'Success': True,
                'Message': 'Scan completed successfully',
                'Results': self.ScanResults,
                'RootFolderId': RootFolder.Id,
                'TotalSizeGB': TotalSizeGB
            }

        except Exception as e:
            LoggingService.LogException("Error during scan", e)
            self.IsScanning = False
            self.ScanErrors.append(f"Scan error: {str(e)}")
            return {
                'Success': False,
                'Message': f'Error during scan: {str(e)}',
                'Error': 'ScanError',
                'Results': self.ScanResults
            }


    def GetOrCreateRootFolder(self, RootFolderPath: str, TotalSizeGB: float) -> RootFolderModel:
        """Get existing root folder or create a new one using filesystem validation."""
        try:
            # Get canonical path from filesystem
            CanonicalPath = self.GetCanonicalPathFromFilesystem(RootFolderPath)

            # Check if root folder already exists (case-insensitive via canonical paths)
            ExistingFolders = self.Repository.GetAllRootFolders()

            for Folder in ExistingFolders:
                # Compare using canonical paths from filesystem
                # Only check if the path exists to avoid warnings for inaccessible drives
                try:
                    if os.path.exists(Folder.RootFolder):
                        ExistingCanonical = self.GetCanonicalPathFromFilesystem(Folder.RootFolder)
                        if ExistingCanonical == CanonicalPath:
                            # Update existing folder with canonical path
                            Folder.RootFolder = CanonicalPath
                            Folder.LastScannedDate = datetime.now()
                            Folder.TotalSizeGB = TotalSizeGB
                            FolderId = self.Repository.SaveRootFolder(Folder)
                            Folder.Id = FolderId
                            LoggingService.LogInfo(f"Updated existing root folder: {CanonicalPath}")
                            return Folder
                except Exception:
                    # Skip folders that can't be accessed (e.g., T: drive not mapped in this session)
                    continue

            # Create new root folder with canonical path
            NewFolder = RootFolderModel(
                RootFolder=CanonicalPath,
                LastScannedDate=datetime.now(),
                TotalSizeGB=TotalSizeGB
            )
            FolderId = self.Repository.SaveRootFolder(NewFolder)
            NewFolder.Id = FolderId
            LoggingService.LogInfo(f"Created new root folder: {CanonicalPath}")
            return NewFolder

        except Exception as e:
            LoggingService.LogException("Error managing root folder", e)
            raise

    def GetCanonicalPathFromFilesystem(self, Path: str) -> str:
        """Get the actual case-sensitive path as it exists on the filesystem."""
        try:
            if not Path:
                return Path

            import os
            normalized_path = os.path.normpath(Path)

            # Check if path exists
            if not os.path.exists(normalized_path):
                LoggingService.LogWarning(f"Path does not exist, cannot get canonical case: {Path}",
                                         'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
                return normalized_path

            # Build the path component by component to get actual case
            # This works for both local and network drives
            # Handle Windows drive letter paths properly (e.g., "Z:\Videos")
            if len(normalized_path) >= 2 and normalized_path[1] == ':':
                # Windows drive letter path - split at the drive letter
                drive = normalized_path[0:2]  # e.g., "Z:"
                remainder = normalized_path[2:].lstrip(os.sep)  # e.g., "Videos" (without leading \)
                result_path = drive + os.sep  # e.g., "Z:\" - ensure we have the backslash
                if remainder:
                    parts = remainder.split(os.sep)
                else:
                    parts = []
            else:
                # Unix-style path or UNC path
                parts = normalized_path.split(os.sep)
                result_path = parts[0] if parts else ''
                parts = parts[1:] if parts else []

            # Resolve each component by listing parent directory
            current_path = result_path
            for part in parts:
                if not part:  # Skip empty parts
                    continue

                try:
                    # List directory contents to find actual case
                    if os.path.isdir(current_path):
                        dir_contents = os.listdir(current_path)
                        # Find matching directory (case-insensitive comparison)
                        actual_name = None
                        for item in dir_contents:
                            if item.upper() == part.upper():
                                actual_name = item
                                break

                        if actual_name:
                            current_path = os.path.join(current_path, actual_name)
                        else:
                            # If not found in listing, use original (might be a file)
                            current_path = os.path.join(current_path, part)
                    else:
                        # Not a directory, just append
                        current_path = os.path.join(current_path, part)
                except Exception as e:
                    # If we can't list directory, just use original part
                    LoggingService.LogWarning(f"Could not list directory '{current_path}' to get actual case, using: {part}",
                                             'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
                    current_path = os.path.join(current_path, part)

            # Log if case changed
            if current_path != normalized_path:
                LoggingService.LogInfo(f"Normalized path case: '{normalized_path}' -> '{current_path}'",
                                     'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')

            return current_path

        except Exception as e:
            LoggingService.LogWarning(f"Could not resolve canonical path for {Path}, using original: {str(e)}",
                                     'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
            return Path if Path else normalized_path

    def ProcessMediaFiles(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process each media file found during scanning with optional metadata extraction."""
        try:
            LoggingService.LogFunctionEntry("ProcessMediaFiles", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")

            # Use the new metadata-aware processing method
            self.ProcessMediaFilesWithMetadata(MediaFiles, RootFolderId, RootFolderPath, ExtractMetadata)

        except Exception as e:
            LoggingService.LogException("Error processing media files", e, 'ProcessMediaFiles', 'FileScanningBusinessService')
            raise

    def ExtractSeasonFromPath(self, FilePath: str, RootFolderPath: str) -> str:
        """Simplified season extraction - return empty string since season functionality is disabled."""
        return ""


    def ExtractShowInfo(self, FileName: str) -> Dict[str, str]:
        """Extract show, season, and episode information from filename."""
        try:
            # Remove file extension
            NameWithoutExt = Path(FileName).stem

            ShowInfo = {
                'ShowName': '',
                'Season': '',
                'Episode': '',
                'Quality': '',
                'Source': ''
            }

            # Extract season/episode pattern (S01E11, S1E11, 1x11, etc.)
            SeasonEpisodePattern = r'[Ss](\d+)[Ee](\d+)'
            Match = re.search(SeasonEpisodePattern, NameWithoutExt)

            if Match:
                ShowInfo['Season'] = f"S{Match.group(1).zfill(2)}"
                ShowInfo['Episode'] = f"E{Match.group(2).zfill(2)}"

                # Extract show name (everything before season/episode)
                ShowName = NameWithoutExt[:Match.start()].strip()
                ShowName = re.sub(r'[-._]', ' ', ShowName).strip()
                ShowInfo['ShowName'] = ShowName
            else:
                # Try alternative pattern (1x11, 1.11, etc.)
                AltPattern = r'(\d+)[x.](\d+)'
                AltMatch = re.search(AltPattern, NameWithoutExt)
                if AltMatch:
                    ShowInfo['Season'] = f"S{AltMatch.group(1).zfill(2)}"
                    ShowInfo['Episode'] = f"E{AltMatch.group(2).zfill(2)}"

                    # Extract show name
                    ShowName = NameWithoutExt[:AltMatch.start()].strip()
                    ShowName = re.sub(r'[-._]', ' ', ShowName).strip()
                    ShowInfo['ShowName'] = ShowName

            # Extract quality indicators
            QualityPatterns = ['1080p', '720p', '480p', '4K', 'Bluray', 'HDTV', 'WEBRip', 'WEB-DL', 'BRRip', 'DVDRip']
            for Pattern in QualityPatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    ShowInfo['Quality'] = Pattern
                    break

            # Extract source indicators
            SourcePatterns = ['Bluray', 'HDTV', 'WEBRip', 'WEB-DL', 'BRRip', 'DVDRip', 'TVRip']
            for Pattern in SourcePatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    ShowInfo['Source'] = Pattern
                    break

            return ShowInfo

        except Exception as e:
            LoggingService.LogException("Error extracting show info", e)
            return {'ShowName': '', 'Season': '', 'Episode': '', 'Quality': '', 'Source': ''}

    def IsFuzzyMatch(self, FileInfo: Dict[str, str], DbFileInfo: Dict[str, str],
                    FileSize: float, DbFileSize: float) -> bool:
        """Determine if two files are a fuzzy match."""
        try:
            # Must have same show name (case insensitive)
            if FileInfo['ShowName'].lower() != DbFileInfo['ShowName'].lower():
                return False

            # Must have same season and episode
            if FileInfo['Season'] != DbFileInfo['Season'] or FileInfo['Episode'] != DbFileInfo['Episode']:
                return False

            # Size difference tolerance (within 10% or 100MB, whichever is larger)
            SizeDifference = abs(FileSize - DbFileSize)
            SizeTolerance = max(FileSize * 0.1, 100)  # 10% or 100MB, whichever is larger

            if SizeDifference > SizeTolerance:
                return False

            # If we get here, it's a fuzzy match
            return True

        except Exception as e:
            LoggingService.LogException("Error in fuzzy match logic", e)
            return False

    def IsValidTranscodeResolutionChange(self, OriginalResolution: Optional[str], NewResolution: Optional[str]) -> bool:
        """Check if resolution change matches valid transcoding patterns."""
        try:
            if not OriginalResolution or not NewResolution:
                return False

            # Import FilenameResolutionService to access resolution mapping
            from Services.FilenameResolutionService import FilenameResolutionService
            ResolutionService = FilenameResolutionService()

            # Normalize resolution strings (case-insensitive comparison)
            OriginalRes = OriginalResolution.lower()
            NewRes = NewResolution.lower()

            # Check if the resolution change matches the transcoding mapping
            # For example: 2160p -> 720p, 1080p -> 720p
            for SourceRes, TargetRes in ResolutionService.ResolutionMapping.items():
                if OriginalRes == SourceRes.lower() and NewRes == TargetRes.lower():
                    LoggingService.LogDebug(f"Valid transcode resolution change detected: {OriginalResolution} -> {NewResolution}", 'IsValidTranscodeResolutionChange', 'FileScanningBusinessService')
                    return True

            LoggingService.LogDebug(f"Invalid transcode resolution change: {OriginalResolution} -> {NewResolution}", 'IsValidTranscodeResolutionChange', 'FileScanningBusinessService')
            return False

        except Exception as e:
            LoggingService.LogException("Error validating transcode resolution change", e, 'IsValidTranscodeResolutionChange', 'FileScanningBusinessService')
            return False

    def FindFuzzyFileMatch(self, FilePath: str, FileName: str, FileSizeMB: float, RootFolderId: int) -> Optional[MediaFileModel]:
        """Find a fuzzy match for a file in the database."""
        try:
            # Get all files for this root folder
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(RootFolderId)

            # Extract show/season/episode info from filename
            FileShowInfo = self.ExtractShowInfo(FileName)

            # Skip fuzzy matching if we don't have show info
            if not FileShowInfo['ShowName'] or not FileShowInfo['Season'] or not FileShowInfo['Episode']:
                return None

            for DbFile in DatabaseFiles:
                DbShowInfo = self.ExtractShowInfo(DbFile.FileName)

                # Check for fuzzy match criteria
                if self.IsFuzzyMatch(FileShowInfo, DbShowInfo, FileSizeMB, DbFile.SizeMB):
                    # Only update if old file doesn't exist on filesystem
                    if not os.path.exists(DbFile.FilePath):
                        return DbFile
                    else:
                        return None

            return None

        except Exception as e:
            LoggingService.LogException("Error in fuzzy file matching", e)
            return None

    def FindTranscodedFileMatch(self, FilePath: str, FileName: str, FileSizeMB: float, RootFolderId: int) -> Optional[MediaFileModel]:
        """Find a match for a transcoded file with resolution change."""
        try:
            LoggingService.LogDebug(f"Checking for transcoded file match: {FilePath}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')

            # STEP 1: Check if file is in _transcoded subdirectory
            if "_transcoded" not in FilePath:
                LoggingService.LogDebug(f"File not in _transcoded directory, skipping transcoded match: {FilePath}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                return None

            # STEP 2: Extract base filename without resolution
            from Services.FilenameResolutionService import FilenameResolutionService
            ResolutionService = FilenameResolutionService()
            BaseFileName = ResolutionService.ExtractBaseFilenameWithoutResolution(FileName)

            if not BaseFileName:
                LoggingService.LogWarning(f"Could not extract base filename from: {FileName}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                return None

            # STEP 3: Get current resolution from filename
            CurrentResolution = ResolutionService.ExtractResolutionFromFilename(FileName)

            # STEP 4: Get all files for this root folder
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(RootFolderId)

            LoggingService.LogDebug(f"Searching {len(DatabaseFiles)} database files for base name match: '{BaseFileName}'", 'FindTranscodedFileMatch', 'FileScanningBusinessService')

            # STEP 5: Check each potential match
            for DbFile in DatabaseFiles:
                # Extract base filename from database file
                DbBaseFileName = ResolutionService.ExtractBaseFilenameWithoutResolution(DbFile.FileName)

                # Check if base filenames match (case-insensitive)
                if DbBaseFileName.lower() != BaseFileName.lower():
                    continue

                # Get resolution from database file
                DbResolution = ResolutionService.ExtractResolutionFromFilename(DbFile.FileName)

                # Check if resolution change is valid (2160p->720p, 1080p->720p)
                if not self.IsValidTranscodeResolutionChange(DbResolution, CurrentResolution):
                    LoggingService.LogDebug(f"Resolution change not valid: {DbResolution} -> {CurrentResolution}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                    continue

                # Check if original file is in parent directory (not _transcoded)
                if "_transcoded" in DbFile.FilePath:
                    LoggingService.LogDebug(f"Database file already in _transcoded directory: {DbFile.FilePath}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                    continue

                # Check if original file still exists
                if not os.path.exists(DbFile.FilePath):
                    # Original file no longer exists, this is likely the transcoded version
                    LoggingService.LogInfo(f"TRANSCODED FILE MATCH FOUND: Original '{DbFile.FilePath}' -> Transcoded '{FilePath}'", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                    return DbFile
                else:
                    # Original still exists, check TranscodeFiles table
                    TranscodeRecord = self.Repository.GetTranscodeFileByFilePath(DbFile.FilePath)
                    if TranscodeRecord and TranscodeRecord.SuccessfullyTranscoded:
                        # Original was transcoded successfully, update DB record
                        LoggingService.LogInfo(f"TRANSCODED FILE MATCH FOUND (original exists but marked as transcoded): Original '{DbFile.FilePath}' -> Transcoded '{FilePath}'", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
                        return DbFile

            LoggingService.LogDebug(f"No transcoded file match found for: {FilePath}", 'FindTranscodedFileMatch', 'FileScanningBusinessService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding transcoded file match", e, 'FindTranscodedFileMatch', 'FileScanningBusinessService')
            return None



    def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process a single media file with fuzzy matching and optional metadata extraction."""
        try:
            # Normalize the path upfront so all lookups and inserts use the same canonical path
            # This prevents duplicates caused by path normalization differences between
            # GetMediaFileByPath (raw path) and SaveMediaFile (normalized path)
            FilePath = os.path.normpath(FilePath)

            # First check if the file actually exists on disk
            if not os.path.exists(FilePath):
                LoggingService.LogWarning(f"File does not exist on disk: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                # Check if there's a database entry for this file path and delete it
                ExistingFile = self.Repository.GetMediaFileByPath(FilePath)
                if ExistingFile:
                    LoggingService.LogInfo(f"Deleting database entry for missing file: {FilePath} (ID: {ExistingFile.Id})", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    self.Repository.DeleteMediaFile(ExistingFile.Id)
                    LoggingService.LogInfo(f"Successfully deleted database entry for missing file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                else:
                    LoggingService.LogDebug(f"No database entry found for missing file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                # Don't process further if file doesn't exist
                return

            # Get file information (FAST - no ffprobe yet)
            FileSizeMB = self.FileManager.GetFileSizeMB(FilePath)
            FileName = self.FileManager.GetFileNameFromPath(FilePath)
            FileModificationTime = self.GetFileModificationTime(FilePath)

            # Get file size in bytes for new FileSize column
            try:
                FileSize = os.path.getsize(FilePath)
            except:
                FileSize = int(FileSizeMB * 1024 * 1024) if FileSizeMB else 0

            # Check if this file already exists in database (exact match)
            ExistingFile = self.Repository.GetMediaFileByPath(FilePath)
            if ExistingFile:
                # OPTIMIZATION: Quick check using LastModifiedDate and FileSize
                # This is MUCH faster than re-extracting metadata
                HasChanged = self.HasFileChanged(ExistingFile, FileSizeMB, FileName, FileModificationTime)

                if HasChanged:
                    # File has changed - update it
                    LoggingService.LogInfo(f"File changed, updating: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    ExistingFile.SizeMB = FileSizeMB
                    ExistingFile.FileName = FileName
                    ExistingFile.FileModificationTime = FileModificationTime
                    ExistingFile.LastModifiedDate = FileModificationTime
                    ExistingFile.FileSize = FileSize
                    ExistingFile.SeasonId = None  # Season functionality disabled
                    ExistingFile.LastScannedDate = datetime.now()

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                        self.ExtractAndUpdateMetadata(ExistingFile, FilePath)

                    self.Repository.SaveMediaFile(ExistingFile)
                    self.ScanResults.TotalFilesProcessed += 1
                else:
                    # FILE UNCHANGED - SKIP PROCESSING (HUGE PERFORMANCE WIN!)
                    # Only update LastScannedDate to mark it was checked
                    ExistingFile.LastScannedDate = datetime.now()
                    self.UpdateLastScannedDate(ExistingFile.Id, ExistingFile.LastScannedDate)
                    self.ScanResults.TotalFilesSkipped += 1
                    LoggingService.LogDebug(f"Skipped unchanged file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

            else:
                # File doesn't exist in database - check for fuzzy match (renamed file)
                FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)

                if FuzzyMatch:
                    # Found a fuzzy match - this is likely a renamed file
                    FuzzyMatch.FilePath = FilePath  # Update to new path
                    FuzzyMatch.FileName = FileName  # Update to new filename
                    FuzzyMatch.SizeMB = FileSizeMB  # Update to new size
                    FuzzyMatch.FileModificationTime = FileModificationTime
                    FuzzyMatch.SeasonId = None  # Season functionality disabled
                    FuzzyMatch.LastScannedDate = datetime.now()
                    # Note: RootFolderId is not stored in MediaFiles table - files are associated by FilePath

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(FuzzyMatch):
                        self.ExtractAndUpdateMetadata(FuzzyMatch, FilePath)

                    self.Repository.SaveMediaFile(FuzzyMatch)
                    self.ScanResults.TotalFilesProcessed += 1
                else:
                    # No fuzzy match found - check for transcoded file match
                    TranscodedMatch = self.FindTranscodedFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)

                    if TranscodedMatch:
                        # Found a transcoded match - update existing record with new path/name
                        LoggingService.LogInfo(f"Updating database record for transcoded file: {TranscodedMatch.FilePath} -> {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                        TranscodedMatch.FilePath = FilePath  # Update to new path
                        TranscodedMatch.FileName = FileName  # Update to new filename
                        TranscodedMatch.SizeMB = FileSizeMB  # Update to new size
                        TranscodedMatch.FileModificationTime = FileModificationTime
                        TranscodedMatch.TranscodedByMediaVortex = True  # Flag as transcoded
                        TranscodedMatch.LastScannedDate = datetime.now()

                        # Extract metadata if requested (transcoded files may have different metadata)
                        if ExtractMetadata:
                            self.ExtractAndUpdateMetadata(TranscodedMatch, FilePath)

                        self.Repository.SaveMediaFile(TranscodedMatch)
                        self.ScanResults.TotalFilesProcessed += 1
                        LoggingService.LogInfo(f"Successfully updated transcoded file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    else:
                        # Create new file record
                        LoggingService.LogInfo(f"New file discovered: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                        NewFile = MediaFileModel(
                            SeasonId=None,  # Season functionality disabled
                            FilePath=FilePath,
                            FileName=FileName,
                            SizeMB=FileSizeMB,
                            FileModificationTime=FileModificationTime,
                            LastModifiedDate=FileModificationTime,
                            FileSize=FileSize,
                            LastScannedDate=datetime.now()
                        )
                        # Note: RootFolderId is not stored in MediaFiles table - files are associated by FilePath

                        # Extract metadata if requested
                        if ExtractMetadata:
                            self.ExtractAndUpdateMetadata(NewFile, FilePath)

                        self.Repository.SaveMediaFile(NewFile)
                        self.ScanResults.TotalFilesProcessed += 1

        except Exception as e:
            LoggingService.LogException("Error processing single media file", e)
            self.ScanResults.TotalFilesSkipped += 1
            raise


    # Note: Duplicate detection methods have been moved to DuplicateDetectionService
    # to keep the scanning process focused and fast. Use the dedicated service
    # for duplicate file detection and cleanup operations.

    def UpdateScanResults(self):
        """Update scan results with file manager statistics."""
        try:
            FileManagerStats = self.FileManager.GetProcessingStats()
            EncodingErrors = self.FileManager.GetEncodingErrors()

            # Update scan results with file manager statistics
            self.ScanResults.TotalFilesSkipped = FileManagerStats.get('SkippedFiles', 0)
            self.ScanResults.TotalFilesWithErrors = FileManagerStats.get('EncodingErrors', 0)

            # Add encoding errors to scan errors
            self.ScanErrors.extend(EncodingErrors)

            LoggingService.LogInfo(f"Scan results updated: TotalFiles={self.ScanResults.TotalFilesFound}, Processed={self.ScanResults.TotalFilesProcessed}, Skipped={self.ScanResults.TotalFilesSkipped}, Errors={self.ScanResults.TotalFilesWithErrors}")

        except Exception as e:
            LoggingService.LogException("Error updating scan results", e)


    def GetScanStatus(self) -> Dict[str, Any]:
        """Get current scan status and progress."""
        return self.GetCurrentScanStatus()

    def GetRootFolders(self, SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> List[RootFolderModel]:
        """Get all root folders with optional sorting."""
        try:
            return self.Repository.GetAllRootFolders(SortColumn, SortOrder)
        except Exception as e:
            LoggingService.LogException("Error getting root folders", e)
            return []

    def GetMediaFiles(self, RootFolderPath: Optional[str] = None) -> List[MediaFileModel]:
        """Get media files, optionally filtered by root folder."""
        try:
            if RootFolderPath:
                return self.Repository.GetMediaFilesByRootFolder(RootFolderPath)
            else:
                return self.Repository.GetAllMediaFiles()
        except Exception as e:
            LoggingService.LogException("Error getting media files", e)
            return []

    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            return self.Repository.DeleteRootFolder(RootFolderId)
        except Exception as e:
            LoggingService.LogException("Error deleting root folder", e)
            return False

    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete a media file."""
        try:
            return self.Repository.DeleteMediaFile(MediaFileId)
        except Exception as e:
            LoggingService.LogException("Error deleting media file", e)
            return False

    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings from SystemSettings table."""
        try:
            return self.Repository.GetScanDirectories()
        except Exception as e:
            LoggingService.LogException("Error getting scan directories", e)
            return []

    def GetStatistics(self) -> Dict[str, Any]:
        """Get library statistics for display."""
        try:
            Query = """
                SELECT
                    COUNT(*) AS TotalMediaFiles,
                    COUNT(CASE WHEN TranscodedByMediaVortex = true THEN 1 END) AS EncodedByMediaVortex,
                    COUNT(CASE WHEN FFProbeFailureCount >= 3 THEN 1 END) AS PossiblyCorrupt,
                    ROUND(SUM(SizeMB)::numeric / 1024, 1) AS TotalSizeGB
                FROM MediaFiles
            """
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)
            Row = Result[0] if Result else {}

            SpaceSavedQuery = """
                SELECT ROUND(COALESCE(SUM(OldSizeBytes - NewSizeBytes), 0)::numeric / 1024 / 1024 / 1024, 1) AS SpaceSavedGB
                FROM TranscodeAttempts
                WHERE Success = true AND FileReplaced = true
            """
            SpaceSavedResult = self.Repository.DatabaseService.ExecuteQuery(SpaceSavedQuery)
            SpaceSavedGB = float(SpaceSavedResult[0]['SpaceSavedGB']) if SpaceSavedResult and SpaceSavedResult[0]['SpaceSavedGB'] else 0.0

            return {
                'TotalMediaFiles': Row.get('TotalMediaFiles', 0),
                'EncodedByMediaVortex': Row.get('EncodedByMediaVortex', 0),
                'SpaceSavedGB': SpaceSavedGB,
                'TotalSizeGB': float(Row.get('TotalSizeGB', 0) or 0),
                'PossiblyCorrupt': Row.get('PossiblyCorrupt', 0)
            }

        except Exception as e:
            LoggingService.LogException("Error getting statistics", e, "FileScanningBusinessService", "GetStatistics")
            return {
                'TotalMediaFiles': 0,
                'EncodedByMediaVortex': 0,
                'SpaceSavedGB': 0.0,
                'TotalSizeGB': 0.0,
                'PossiblyCorrupt': 0
            }

    def ResetScanState(self):
        """Reset the scan state to allow new scans."""
        # Clear current job reference
        self.CurrentJobId = None
        # Clean up old completed jobs
        self.CleanupCompletedJobs()

    def ShouldExtractMetadata(self, MediaFile: MediaFileModel) -> bool:
        """Determine if metadata should be extracted for a media file based on change detection."""
        try:
            # Don't extract if media analysis is not available
            if not self.FileManager.IsMediaAnalysisAvailable():
                LoggingService.LogWarning("Media analysis not available - skipping metadata extraction", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return False

            LoggingService.LogDebug(f"Media analysis is available for file: {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')

            # Skip files that have exceeded the FFprobe failure limit
            if (MediaFile.FFprobeFailureCount or 0) >= MediaProbeBusinessService.MaxFFprobeFailures:
                LoggingService.LogDebug(f"Skipping file with {MediaFile.FFprobeFailureCount} probe failures (max {MediaProbeBusinessService.MaxFFprobeFailures}): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return False

            # Always extract for new files (no metadata at all)
            if (MediaFile.VideoBitrateKbps is None and
                MediaFile.AudioBitrateKbps is None and
                MediaFile.Resolution is None and
                MediaFile.Codec is None and
                MediaFile.DurationMinutes is None and
                MediaFile.FrameRate is None):
                LoggingService.LogDebug(f"File needs metadata extraction (new file): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Always extract if resolution is None (FFprobe analysis failed or never ran)
            if MediaFile.Resolution is None:
                LoggingService.LogDebug(f"File needs metadata extraction (no resolution): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Always extract if TotalFrames is missing (critical for transcode progress tracking)
            if MediaFile.TotalFrames is None:
                LoggingService.LogDebug(f"File needs metadata extraction (no TotalFrames): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Check if file has changed (size or name)
            # Get current file information to compare
            try:
                if os.path.exists(MediaFile.FilePath):
                    CurrentSizeMB = os.path.getsize(MediaFile.FilePath) / (1024 * 1024)
                    CurrentFileName = os.path.basename(MediaFile.FilePath)
                    CurrentModificationTime = self.GetFileModificationTime(MediaFile.FilePath)

                    if self.HasFileChanged(MediaFile, CurrentSizeMB, CurrentFileName, CurrentModificationTime):
                        return True
                else:
                    # File doesn't exist, should be cleaned up
                    LoggingService.LogWarning(f"File {MediaFile.FilePath} no longer exists", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                    return False
            except Exception as e:
                LoggingService.LogException(f"Error checking file changes for {MediaFile.FilePath}", e, 'ShouldExtractMetadata', 'FileScanningBusinessService')
                # If we can't check, assume it needs analysis to be safe
                return True

            # File hasn't changed and has metadata, skip extraction
            return False

        except Exception as e:
            LoggingService.LogException("Error determining if metadata should be extracted", e, 'ShouldExtractMetadata', 'FileScanningBusinessService')
            return False

    def GetFileModificationTime(self, FilePath: str) -> datetime:
        """Get the file modification time."""
        try:
            ModificationTime = os.path.getmtime(FilePath)
            # Windows datetime.fromtimestamp() cannot handle negative timestamps (pre-1970 dates)
            if ModificationTime < 0:
                ModificationTime = 0
            return datetime.fromtimestamp(ModificationTime)
        except Exception as e:
            LoggingService.LogException(f"Error getting file modification time for {FilePath}", e, 'GetFileModificationTime', 'FileScanningBusinessService')
            return datetime.now()

    def HasFileChanged(self, MediaFile: MediaFileModel, CurrentSizeMB: float, CurrentFileName: str, CurrentModificationTime: datetime) -> bool:
        """Check if a file has changed by comparing size, name, and modification time."""
        try:
            # Compare with stored values
            SizeChanged = abs(CurrentSizeMB - MediaFile.SizeMB) > 0.1  # Allow small floating point differences
            NameChanged = CurrentFileName != MediaFile.FileName

            # Compare modification time (allow 1 second tolerance for filesystem precision)
            ModificationTimeChanged = False
            if MediaFile.FileModificationTime and CurrentModificationTime:
                # Handle case where FileModificationTime might be a string from database
                StoredModificationTime = MediaFile.FileModificationTime
                if isinstance(StoredModificationTime, str):
                    try:
                        from datetime import datetime
                        StoredModificationTime = datetime.fromisoformat(StoredModificationTime.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # If we can't parse the string, assume it changed
                        ModificationTimeChanged = True
                else:
                    TimeDifference = abs((CurrentModificationTime - StoredModificationTime).total_seconds())
                    ModificationTimeChanged = TimeDifference > 1.0

            if SizeChanged or NameChanged or ModificationTimeChanged:
                LoggingService.LogDebug(f"File changed detected for {MediaFile.FilePath}: Size={SizeChanged}, Name={NameChanged}, ModTime={ModificationTimeChanged}", 'FileScanningBusinessService', 'HasFileChanged')
                return True

            return False

        except Exception as e:
            LoggingService.LogException("Error checking if file has changed", e, 'HasFileChanged', 'FileScanningBusinessService')
            # If we can't check, assume it changed to be safe
            return True

    def IsSameFile(self, DbFile: MediaFileModel, FilePath: str) -> bool:
        """Check if a file at a given path is the same as a database file record."""
        try:
            if not os.path.exists(FilePath):
                return False

            # Get current file information
            CurrentSize = os.path.getsize(FilePath) / (1024 * 1024)  # MB
            CurrentModTime = datetime.fromtimestamp(os.path.getmtime(FilePath))

            # Allow 1MB size difference (to account for transcoding compression)
            SizeMatch = abs(CurrentSize - DbFile.SizeMB) < 1.0

            # Allow 2 second modification time difference (to account for filesystem precision)
            TimeMatch = True
            if DbFile.FileModificationTime and CurrentModTime:
                # Handle case where FileModificationTime might be a string from database
                StoredModTime = DbFile.FileModificationTime
                if isinstance(StoredModTime, str):
                    try:
                        StoredModTime = datetime.fromisoformat(StoredModTime.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # If we can't parse, just use size match
                        TimeMatch = True
                else:
                    TimeDifference = abs((CurrentModTime - StoredModTime).total_seconds())
                    TimeMatch = TimeDifference < 2.0

            IsMatch = SizeMatch and TimeMatch
            if IsMatch:
                LoggingService.LogDebug(f"File match confirmed: DB '{DbFile.FilePath}' matches '{FilePath}' (Size: {DbFile.SizeMB}MB vs {CurrentSize}MB)", 'IsSameFile', 'FileScanningBusinessService')

            return IsMatch

        except Exception as e:
            LoggingService.LogException("Error checking if files are the same", e, 'IsSameFile', 'FileScanningBusinessService')
            return False

    def UpdateLastScannedDate(self, MediaFileId: int, LastScannedDate: datetime):
        """Update only the LastScannedDate for a media file without full save."""
        try:
            Query = "UPDATE MediaFiles SET LastScannedDate = %s WHERE Id = %s"
            self.Repository.DatabaseService.ExecuteNonQuery(Query, (LastScannedDate, MediaFileId))
        except Exception as e:
            LoggingService.LogException(f"Error updating LastScannedDate for file ID {MediaFileId}", e, 'UpdateLastScannedDate', 'FileScanningBusinessService')

    def ExtractAndUpdateMetadata(self, MediaFile: MediaFileModel, FilePath: str):
        """Extract metadata and update the media file model."""
        try:
            LoggingService.LogDebug(f"Extracting metadata for: {FilePath}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')

            # Update file size, name, and modification time to current values (in case file changed)
            MediaFile.SizeMB = self.FileManager.GetFileSizeMB(FilePath)
            MediaFile.FileName = self.FileManager.GetFileNameFromPath(FilePath)
            MediaFile.FileModificationTime = self.GetFileModificationTime(FilePath)

            # Extract metadata using FileManagerService
            MetadataResult = self.FileManager.ExtractMediaMetadata(FilePath)

            # Log what metadata we extracted

            if MetadataResult.get('Success', False):
                # Update the media file with extracted metadata
                MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
                MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
                MediaFile.Resolution = MetadataResult.get('Resolution')
                MediaFile.Codec = MetadataResult.get('VideoCodec')
                MediaFile.DurationMinutes = MetadataResult.get('DurationMinutes')
                MediaFile.FrameRate = MetadataResult.get('FrameRate')

                # Extract new metadata fields
                MediaFile.TotalFrames = MetadataResult.get('TotalFrames')
                MediaFile.CodecProfile = MetadataResult.get('CodecProfile')
                MediaFile.ColorRange = MetadataResult.get('ColorRange')
                MediaFile.FieldOrder = MetadataResult.get('FieldOrder')
                MediaFile.HasBFrames = MetadataResult.get('HasBFrames')
                MediaFile.RefFrames = MetadataResult.get('RefFrames')
                MediaFile.PixelFormat = MetadataResult.get('PixelFormat')
                MediaFile.Level = MetadataResult.get('Level')
                MediaFile.AudioChannels = MetadataResult.get('AudioChannels')
                MediaFile.AudioSampleRate = MetadataResult.get('AudioSampleRate')
                MediaFile.AudioSampleFormat = MetadataResult.get('AudioSampleFormat')
                MediaFile.AudioChannelLayout = MetadataResult.get('AudioChannelLayout')
                MediaFile.AudioCodec = MetadataResult.get('AudioCodec')
                MediaFile.SubtitleFormats = MetadataResult.get('SubtitleFormats')
                MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
                MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')

                # Derive ResolutionCategory from Resolution
                if MediaFile.Resolution and 'x' in MediaFile.Resolution:
                    try:
                        Height = int(MediaFile.Resolution.split('x')[1])
                        if Height >= 2160:
                            MediaFile.ResolutionCategory = "2160p"
                        elif Height >= 1080:
                            MediaFile.ResolutionCategory = "1080p"
                        elif Height >= 720:
                            MediaFile.ResolutionCategory = "720p"
                        else:
                            MediaFile.ResolutionCategory = "480p"
                    except (ValueError, IndexError):
                        pass

                LoggingService.LogDebug(f"Successfully extracted metadata for: {FilePath}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
                # Clear failure tracking on success
                MediaFile.FFprobeFailureCount = 0
                MediaFile.LastFFprobeError = None
                MediaFile.LastFFprobeAttemptDate = datetime.now()
            else:
                # Record failure
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"Failed to extract metadata for {FilePath}: {ErrorMessage}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
                MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
                MediaFile.LastFFprobeError = ErrorMessage
                MediaFile.LastFFprobeAttemptDate = datetime.now()

        except Exception as e:
            LoggingService.LogException("Error extracting and updating metadata", e, 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
            MediaFile.LastFFprobeError = str(e)
            MediaFile.LastFFprobeAttemptDate = datetime.now()

    def CleanupMissingFiles(self, RootFolderId: Optional[int] = None):
        """Remove database records for files that no longer exist on disk."""
        try:
            LoggingService.LogInfo("=== CLEANUP MISSING FILES STARTED ===", 'CleanupMissingFiles', 'FileScanningBusinessService')

            if RootFolderId:
                # Get root folder path
                RootFolder = self.Repository.GetRootFolderById(RootFolderId)
                if not RootFolder:
                    LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'CleanupMissingFiles', 'FileScanningBusinessService')
                    return

                # Get all files in database for this root folder path
                DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(RootFolder.RootFolder)
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} database files for root folder: {RootFolder.RootFolder}", 'CleanupMissingFiles', 'FileScanningBusinessService')
            else:
                # Get all files in database
                DatabaseFiles = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} total database files", 'CleanupMissingFiles', 'FileScanningBusinessService')

            # Check each database file to see if it actually exists on disk
            DeletedCount = 0
            for DbFile in DatabaseFiles:
                if not os.path.exists(DbFile.FilePath):
                    LoggingService.LogInfo(f"FILE NOT FOUND ON DISK - DELETING FROM DATABASE: {DbFile.FilePath}", 'CleanupMissingFiles', 'FileScanningBusinessService')

                    # Delete directly using the database service
                    DeleteQuery = "DELETE FROM MediaFiles WHERE Id = %s"
                    AffectedRows = self.Repository.DatabaseService.ExecuteNonQuery(DeleteQuery, (DbFile.Id,))

                    if AffectedRows > 0:
                        LoggingService.LogInfo(f"SUCCESS: Deleted missing file from database: {DbFile.FilePath} (ID: {DbFile.Id})", 'CleanupMissingFiles', 'FileScanningBusinessService')
                        DeletedCount += 1
                    else:
                        LoggingService.LogWarning(f"Failed to delete missing file from database: {DbFile.FilePath} (ID: {DbFile.Id})", 'CleanupMissingFiles', 'FileScanningBusinessService')

            LoggingService.LogInfo("=== CLEANUP MISSING FILES COMPLETED ===", 'CleanupMissingFiles', 'FileScanningBusinessService')
            if DeletedCount > 0:
                LoggingService.LogInfo(f"SUCCESS: Cleaned up {DeletedCount} missing files from database", 'CleanupMissingFiles', 'FileScanningBusinessService')
            else:
                LoggingService.LogInfo("No missing files found to clean up", 'CleanupMissingFiles', 'FileScanningBusinessService')

        except Exception as e:
            LoggingService.LogException("CRITICAL ERROR in CleanupMissingFiles", e, 'CleanupMissingFiles', 'FileScanningBusinessService')

    def FindMovedFile(self, DbFile: MediaFileModel) -> Optional[Dict[str, str]]:
        """Try to find a moved file by searching all root folders."""
        try:
            LoggingService.LogDebug(f"Searching for moved file: {DbFile.FileName}", 'FindMovedFile', 'FileScanningBusinessService')

            # Get the filename to search for
            SearchFileName = DbFile.FileName

            # Get all root folders
            AllRootFolders = self.Repository.GetAllRootFolders()

            # Search each root folder for matching filename
            for RootFolder in AllRootFolders:
                if not os.path.exists(RootFolder.RootFolder):
                    LoggingService.LogDebug(f"Root folder does not exist: {RootFolder.RootFolder}", 'FindMovedFile', 'FileScanningBusinessService')
                    continue

                try:
                    # Use os.walk to search for file
                    for root, dirs, files in os.walk(RootFolder.RootFolder):
                        for file in files:
                            if file == SearchFileName:
                                FoundPath = os.path.join(root, file)

                                # Skip if this is the original path (not moved)
                                if FoundPath.lower() == DbFile.FilePath.lower():
                                    continue

                                # Verify it's the same file (size + modification time)
                                if self.IsSameFile(DbFile, FoundPath):
                                    LoggingService.LogInfo(f"MOVED FILE FOUND: '{DbFile.FilePath}' -> '{FoundPath}'", 'FindMovedFile', 'FileScanningBusinessService')
                                    return {
                                        'OldPath': DbFile.FilePath,
                                        'NewPath': FoundPath
                                    }

                except Exception as e:
                    LoggingService.LogException(f"Error searching root folder: {RootFolder.RootFolder}", e, 'FindMovedFile', 'FileScanningBusinessService')
                    continue

            LoggingService.LogDebug(f"No moved location found for: {DbFile.FileName}", 'FindMovedFile', 'FileScanningBusinessService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding moved file", e, 'FindMovedFile', 'FileScanningBusinessService')
            return None

    def DetectMovedFiles(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Detect files that have been moved and update their paths."""
        try:
            LoggingService.LogInfo("=== DETECT MOVED FILES STARTED ===", 'DetectMovedFiles', 'FileScanningBusinessService')

            MovedFiles = []
            DeletedFiles = []

            # Get all files (or files for specific root folder)
            if RootFolderId:
                RootFolder = self.Repository.GetRootFolderById(RootFolderId)
                if not RootFolder:
                    LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'DetectMovedFiles', 'FileScanningBusinessService')
                    return {'Success': False, 'ErrorMessage': 'Root folder not found'}

                DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(RootFolder.RootFolder)
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} files in root folder: {RootFolder.RootFolder}", 'DetectMovedFiles', 'FileScanningBusinessService')
            else:
                DatabaseFiles = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} total database files", 'DetectMovedFiles', 'FileScanningBusinessService')

            # Performance optimization: Skip move detection for very large datasets
            MaxFiles = 10000  # Configurable threshold
            if len(DatabaseFiles) > MaxFiles:
                LoggingService.LogWarning(f"Skipping move detection: Database has {len(DatabaseFiles)} files (exceeds limit of {MaxFiles})", 'DetectMovedFiles', 'FileScanningBusinessService')
                return {
                    'Success': True,
                    'MovedFiles': 0,
                    'DeletedFiles': 0,
                    'Skipped': True,
                    'Reason': f'File count exceeds limit ({len(DatabaseFiles)} > {MaxFiles})'
                }

            # Check each file for moves
            for DbFile in DatabaseFiles:
                if not os.path.exists(DbFile.FilePath):
                    # File missing - try to find it
                    MovedFile = self.FindMovedFile(DbFile)

                    if MovedFile:
                        # File was moved, update path
                        LoggingService.LogInfo(f"Updating moved file: {MovedFile['OldPath']} -> {MovedFile['NewPath']}", 'DetectMovedFiles', 'FileScanningBusinessService')
                        DbFile.FilePath = MovedFile['NewPath']
                        DbFile.FileName = os.path.basename(MovedFile['NewPath'])
                        DbFile.LastScannedDate = datetime.now()
                        self.Repository.SaveMediaFile(DbFile)
                        MovedFiles.append({
                            'OldPath': MovedFile['OldPath'],
                            'NewPath': MovedFile['NewPath'],
                            'FileName': DbFile.FileName
                        })
                    else:
                        # File was deleted (will be cleaned up by CleanupMissingFiles)
                        DeletedFiles.append({
                            'FilePath': DbFile.FilePath,
                            'FileName': DbFile.FileName
                        })

            LoggingService.LogInfo("=== DETECT MOVED FILES COMPLETED ===", 'DetectMovedFiles', 'FileScanningBusinessService')
            LoggingService.LogInfo(f"Results: {len(MovedFiles)} files moved, {len(DeletedFiles)} files deleted", 'DetectMovedFiles', 'FileScanningBusinessService')

            return {
                'Success': True,
                'MovedFiles': len(MovedFiles),
                'DeletedFiles': len(DeletedFiles),
                'MovedFilesList': MovedFiles,
                'DeletedFilesList': DeletedFiles
            }

        except Exception as e:
            LoggingService.LogException("Error detecting moved files", e, 'DetectMovedFiles', 'FileScanningBusinessService')
            return {
                'Success': False,
                'ErrorMessage': str(e),
                'MovedFiles': 0,
                'DeletedFiles': 0
            }

    def ProcessMediaFilesWithMetadata(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process media files with optional metadata extraction using parallel processing."""
        try:
            LoggingService.LogFunctionEntry("ProcessMediaFilesWithMetadata", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")

            # Detect moved files first, then cleanup remaining missing files
            if RootFolderId:
                LoggingService.LogInfo("=== CALLING DETECT MOVED FILES ===", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                MoveDetectionResult = self.DetectMovedFiles(RootFolderId)
                LoggingService.LogInfo(f"=== DETECT MOVED FILES COMPLETED === Moved: {MoveDetectionResult.get('MovedFiles', 0)}, Deleted: {MoveDetectionResult.get('DeletedFiles', 0)}", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')

                LoggingService.LogInfo("=== CALLING CLEANUP MISSING FILES ===", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                self.CleanupMissingFiles(RootFolderId)
                LoggingService.LogInfo("=== CLEANUP MISSING FILES CALL COMPLETED ===", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')

            TotalFiles = len(MediaFiles)
            ProcessedCount = 0
            ProgressLock = threading.Lock()

            def ProcessSingleFile(FilePath: str):
                """Process a single file and return result."""
                nonlocal ProcessedCount

                try:
                    # Process the file with metadata extraction
                    self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath, ExtractMetadata)

                    # Update progress thread-safely
                    with ProgressLock:
                        ProcessedCount += 1
                        Progress = 30.0 + (60.0 * ProcessedCount / TotalFiles)
                        self.ScanProgress = Progress

                    return {'Success': True, 'FilePath': FilePath}
                except Exception as e:
                    LoggingService.LogException(f"Error processing media file: {FilePath}", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                    ErrorMessage = f"Error processing {FilePath}: {str(e)}"
                    with ProgressLock:
                        self.ScanErrors.append(ErrorMessage)
                    return {'Success': False, 'FilePath': FilePath, 'Error': str(e)}

            # Process files in parallel with 5 workers
            MaxWorkers = 5
            with ThreadPoolExecutor(max_workers=MaxWorkers) as Executor:
                # Submit all files for processing
                FutureToFile = {Executor.submit(ProcessSingleFile, FilePath): FilePath for FilePath in MediaFiles}

                # Wait for all tasks to complete
                for Future in as_completed(FutureToFile):
                    FilePath = FutureToFile[Future]
                    try:
                        Result = Future.result()
                        if not Result.get('Success', False):
                            LoggingService.LogWarning(f"Failed to process file: {FilePath}", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                    except Exception as e:
                        LoggingService.LogException(f"Exception in future for file: {FilePath}", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                        with ProgressLock:
                            self.ScanErrors.append(f"Error processing {FilePath}: {str(e)}")

            # Note: Duplicate file detection has been moved to a separate process
            # to avoid slowing down the scanning process. Use the dedicated
            # duplicate detection methods when needed.


        except Exception as e:
            LoggingService.LogException("Error processing media files with metadata", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
            raise

    def ExtractMetadataForExistingFiles(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Extract metadata for existing files that don't have metadata."""
        try:
            LoggingService.LogFunctionEntry("ExtractMetadataForExistingFiles", 'FileScanningBusinessService', f"RootFolderId: {RootFolderId}")

            if not self.FileManager.IsMediaAnalysisAvailable():
                return {
                    'Success': False,
                    'Message': 'Media analysis service not available',
                    'Error': 'MediaAnalysisNotAvailable'
                }

            # Get files that need metadata extraction
            # Filter by root folder if RootFolderId is provided, otherwise get all files
            if RootFolderId is not None:
                FilesNeedingMetadata = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)
                LoggingService.LogInfo(f"Found {len(FilesNeedingMetadata)} files for RootFolderId: {RootFolderId}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
            else:
                FilesNeedingMetadata = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Found {len(FilesNeedingMetadata)} total files for metadata extraction", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

            # Filter files that need metadata
            FilesToProcess = []
            for File in FilesNeedingMetadata:
                if self.ShouldExtractMetadata(File):
                    FilesToProcess.append(File)

            LoggingService.LogInfo(f"Files needing metadata extraction: {len(FilesToProcess)} out of {len(FilesNeedingMetadata)}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

            if not FilesToProcess:
                return {
                    'Success': True,
                    'Message': 'No files need metadata extraction',
                    'ProcessedFiles': 0
                }


            # Process files in batches
            BatchSize = 10
            ProcessedCount = 0

            for i in range(0, len(FilesToProcess), BatchSize):
                Batch = FilesToProcess[i:i + BatchSize]

                for File in Batch:
                    try:
                        # Extract metadata and update file
                        self.ExtractAndUpdateMetadata(File, File.FilePath)
                        self.Repository.SaveMediaFile(File)
                        ProcessedCount += 1

                        LoggingService.LogDebug(f"Extracted metadata for: {File.FilePath}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

                    except Exception as e:
                        LoggingService.LogException(f"Error extracting metadata for: {File.FilePath}", e, 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
                        continue


            return {
                'Success': True,
                'Message': f'Successfully extracted metadata for {ProcessedCount} files',
                'ProcessedFiles': ProcessedCount
            }

        except Exception as e:
            LoggingService.LogException("Error extracting metadata for existing files", e, 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
            return {
                'Success': False,
                'Message': f'Error extracting metadata: {str(e)}',
                'Error': 'MetadataExtractionError'
            }

    def AddOrUpdateScanDirectory(self, Key: Optional[str], Path: str, Description: str) -> Dict[str, Any]:
        """Add or update a scan directory in SystemSettings."""
        try:

            # If no key provided, find the next available ScanDir key
            if not Key:
                # Get existing scan directory keys
                ExistingKeys = self.Repository.GetScanDirectories()
                ExistingKeyNumbers = []

                for existingDir in ExistingKeys:
                    if existingDir['Key'].startswith('ScanDir'):
                        try:
                            # Extract number from ScanDir1, ScanDir2, etc.
                            Number = int(existingDir['Key'].replace('ScanDir', ''))
                            ExistingKeyNumbers.append(Number)
                        except ValueError:
                            continue

                # Find the next available number
                NextNumber = 1
                while NextNumber in ExistingKeyNumbers:
                    NextNumber += 1

                Key = f'ScanDir{NextNumber}'

            # Add or update the scan directory setting
            result = self.Repository.AddOrUpdateScanDirectory(Key, Path, Description, 'string')

            if result:
                return {
                    'Success': True,
                    'Message': f'Successfully saved scan directory: {Path}'
                }
            else:
                return {
                    'Success': False,
                    'Error': 'Failed to save scan directory to database'
                }

        except Exception as e:
            LoggingService.LogException("Error adding/updating scan directory", e, "AddOrUpdateScanDirectory", "FileScanningBusinessService")
            return {
                'Success': False,
                'Error': f'Error adding/updating scan directory: {str(e)}'
            }

    def DeleteScanDirectory(self, Key: str) -> Dict[str, Any]:
        """Delete a scan directory from SystemSettings."""
        try:

            # Delete the scan directory setting
            result = self.Repository.DeleteScanDirectory(Key)

            if result:
                return {
                    'Success': True,
                    'Message': f'Successfully deleted scan directory: {Key}'
                }
            else:
                return {
                    'Success': False,
                    'Error': f'Scan directory {Key} not found or could not be deleted'
                }

        except Exception as e:
            LoggingService.LogException("Error deleting scan directory", e, "DeleteScanDirectory", "FileScanningBusinessService")
            return {
                'Success': False,
                'Error': f'Error deleting scan directory: {str(e)}'
            }

