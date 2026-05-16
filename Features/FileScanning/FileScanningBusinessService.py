import os
import ntpath
import uuid
import re
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
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

        # Pick up CurrentJobId if a scan is already running (so StopScanning
        # can target it). Single repository call -- the eight is-running
        # wrappers were retired with criterion 18b.
        try:
            running = self.Repository.GetRunningScans()
            if running:
                self.CurrentJobId = running[-1].get('JobId')
                LoggingService.LogInfo(f"Found existing running scan: JobId={self.CurrentJobId}", 'FileScanningBusinessService', '__init__')
        except Exception as Ex:
            LoggingService.LogException("Error checking existing scans on init", Ex, 'FileScanningBusinessService', '__init__')

    def _ToLocalPath(self, CanonicalPath: str) -> str:
        """Translate a canonical (Windows-style, e.g. 'T:\\Foo') DB path to the
        local worker filesystem path (e.g. '/mnt/media_tv/Foo' on a Linux
        container). No-op on Windows or when WorkerContext has no mappings.

        Use for any os.path.exists / os.walk / os.listdir / os.path.isdir
        call against a path that came out of RootFolders or MediaFiles.
        """
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx and Ctx.PathTranslation:
                return Ctx.PathTranslation.ToLocalPath(CanonicalPath)
        except Exception:
            pass
        return CanonicalPath

    def _ToCanonicalPath(self, LocalPath: str) -> str:
        """Inverse of _ToLocalPath -- translate a local worker filesystem path
        back to canonical (Windows-style) for DB persistence. Use whenever
        os.walk / os.listdir on Linux returns a path that needs to be stored
        in MediaFiles.FilePath / RootFolders.RootFolder.
        """
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx and Ctx.PathTranslation:
                return Ctx.PathTranslation.ToCanonicalPath(LocalPath)
        except Exception:
            pass
        return LocalPath

    def StartScanning(self, RootFolderPath: str, Recursive: bool = True, SkipDuplicateCleanup: bool = False, WorkerName: Optional[str] = None) -> Dict[str, Any]:
        """Start scanning a root folder for media files directly in the main process.

        WorkerName is recorded on the ScanJobs row for observability and used by the
        per-rootfolder duplicate guard. When None, falls back to WorkerContext.Current().
        """
        try:
            LoggingService.LogFunctionEntry("StartScanning", 'FileScanningBusinessService', RootFolderPath, Recursive=Recursive)

            if WorkerName is None:
                try:
                    from Core.WorkerContext import WorkerContext
                    Ctx = WorkerContext.Current()
                    if Ctx is not None:
                        WorkerName = Ctx.WorkerName
                except Exception:
                    pass

            # Per-rootfolder claim guard (criterion 11): refuse a duplicate scan
            # when another worker (or this one) already has a Pending/Running
            # ScanJobs row for this path. Prevents two ScanEnabled workers from
            # racing when their continuous-scan ticks land in the same window.
            # Global concurrency cap removed with criterion 18c -- it
            # contradicted the per-rootfolder claim semantics.
            if self.Repository.GetRunningScans(RootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Scan already running for {RootFolderPath}',
                    'Error': 'ScanAlreadyRunning'
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

            # Translate canonical (Windows-style) path to local for filesystem
            # checks. RootFolderPath stays canonical for DB persistence; only
            # the validation path uses the translated form. On Windows or
            # without share mappings, this is a no-op.
            LocalPath = self._ToLocalPath(RootFolderPath)
            NormalizedPath = os.path.normpath(LocalPath)
            LoggingService.LogInfo(f"Normalized local path: '{NormalizedPath}' (canonical: '{RootFolderPath}')", 'FileScanningBusinessService', 'StartScanning')

            # Check if path exists
            PathExists = os.path.exists(NormalizedPath)

            if not PathExists:
                LoggingService.LogError(f"Path does not exist: local='{NormalizedPath}', canonical='{RootFolderPath}'", 'FileScanningBusinessService', 'StartScanning')
                try:
                    ListDirResult = os.listdir(NormalizedPath)
                    LoggingService.LogInfo(f"os.listdir succeeded, found {len(ListDirResult)} items", 'FileScanningBusinessService', 'StartScanning')
                    PathExists = True
                except Exception as e:
                    LoggingService.LogError(f"os.listdir also failed: {str(e)}", 'FileScanningBusinessService', 'StartScanning')

                if not PathExists:
                    return {
                        'Success': False,
                        'Message': f'Root folder does not exist: {RootFolderPath} (local: {NormalizedPath})',
                        'Error': 'InvalidPath'
                    }

            if not os.path.isdir(NormalizedPath):
                return {
                    'Success': False,
                    'Message': f'Path is not a directory: {RootFolderPath}',
                    'Error': 'NotDirectory'
                }

            # Generate unique job ID
            JobId = str(uuid.uuid4())
            self.CurrentJobId = JobId

            # Create scan job record
            self.CreateScanJob(JobId, RootFolderPath, Recursive, WorkerName=WorkerName)

            # Set scanning state
            self.IsScanning = True
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = RootFolderPath

            LoggingService.LogInfo(f"Starting direct scan for {RootFolderPath}", 'FileScanningBusinessService', 'StartScanning')

            # Criterion 17 (progress writer): heartbeat the ScanJobs row every
            # 5s while the walk runs so operators (and StuckJobDetectionService)
            # can distinguish a live scan from a hung one. Stop the heartbeat
            # BEFORE writing the terminal status so an in-flight beat cannot
            # overwrite Completed/Failed back to Running.
            self._StartProgressHeartbeat(JobId)
            try:
                result = self.PerformScan(RootFolderPath, Recursive, SkipDuplicateCleanup=SkipDuplicateCleanup)
            finally:
                self._StopProgressHeartbeat()

            if result.get('Success', False):
                self.UpdateJobStatus(JobId, 'Completed', Progress=100.0, EndTime=datetime.now(timezone.utc), ScanResults=self.ScanResults)
            else:
                self.UpdateJobStatus(JobId, 'Failed', ErrorMessage=result.get('Message', 'Unknown error'), EndTime=datetime.now(timezone.utc), ScanResults=self.ScanResults)

            return result

        except Exception as e:
            LoggingService.LogException("Error starting scan", e, 'FileScanningBusinessService', 'StartScanning')
            return {
                'Success': False,
                'Message': f'Error starting scan: {str(e)}',
                'Error': 'ScanError'
            }

    def CreateScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool, WorkerName: Optional[str] = None):
        """Create a new scan job record in the database."""
        try:
            Query = """
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated, ScanType, WorkerName)
            VALUES (%s, %s, %s, 'Running', %s, %s, 'File', %s)
            """
            Now = datetime.now(timezone.utc)
            self.Repository.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now, WorkerName))

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
                    "EncodingErrors = %s",
                    "NewFiles = %s",
                    "UpdatedFiles = %s",
                    "DeletedFiles = %s"
                ])
                UpdateValues.extend([
                    ScanResults.TotalFilesFound,
                    ScanResults.TotalFilesProcessed,
                    ScanResults.TotalFilesSkipped,
                    ScanResults.TotalFilesWithErrors,
                    ScanResults.NewFilesCount,
                    ScanResults.UpdatedFilesCount,
                    ScanResults.DeletedFilesCount
                ])

            # Always update LastUpdated
            UpdateFields.append("LastUpdated = %s")
            UpdateValues.append(datetime.now(timezone.utc))

            # Add JobId for WHERE clause
            UpdateValues.append(JobId)

            Query = f"UPDATE ScanJobs SET {', '.join(UpdateFields)} WHERE JobId = %s"
            self.Repository.DatabaseService.ExecuteNonQuery(Query, UpdateValues)

        except Exception as e:
            LoggingService.LogException(f"Error updating job status for {JobId}", e, 'UpdateJobStatus', 'FileScanningBusinessService')


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
            self.UpdateJobStatus(self.CurrentJobId, 'Stopped', EndTime=datetime.now(timezone.utc))

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

    def _StartProgressHeartbeat(self, JobId: str, IntervalSec: int = 5):
        """Owns FileScanning.feature.md criterion 17 (producer side).
        Without this loop, ScanJobs only sees writes at start and end -- a
        healthy walking scan and a hung scan are indistinguishable until
        StuckJobDetectionService fires at the 15-minute threshold.
        """
        self._HeartbeatStopEvent = threading.Event()

        def _Beat():
            while not self._HeartbeatStopEvent.wait(timeout=IntervalSec):
                try:
                    self.UpdateJobStatus(
                        JobId,
                        Status='Running',
                        Progress=float(self.ScanProgress) if self.ScanProgress is not None else None,
                        CurrentDirectory=self.CurrentScanDirectory or None,
                        ScanResults=self.ScanResults,
                    )
                except Exception as Ex:
                    LoggingService.LogException("Heartbeat write failed", Ex, 'FileScanningBusinessService', '_StartProgressHeartbeat')

        self._HeartbeatThread = threading.Thread(
            target=_Beat, daemon=True, name=f"ScanHeartbeat-{JobId[:8]}"
        )
        self._HeartbeatThread.start()

    def _StopProgressHeartbeat(self):
        Ev = getattr(self, '_HeartbeatStopEvent', None)
        if Ev is not None:
            Ev.set()
        Th = getattr(self, '_HeartbeatThread', None)
        if Th is not None and Th.is_alive():
            Th.join(timeout=2)
        self._HeartbeatStopEvent = None
        self._HeartbeatThread = None

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
        """Perform the actual scanning process.

        RootFolderPath is the canonical (Windows-style) path stored in the DB.
        On Linux containers we translate to a local mount for filesystem ops
        and translate the walked file paths back to canonical for DB writes.
        """
        try:
            LoggingService.LogInfo("Starting scan of directory: {}", RootFolderPath)

            # Reset per-scan counters (was carrying over between consecutive scans on
            # the same FileScanningBusinessService instance, polluting heartbeats with
            # stale numbers from the previous rootfolder).
            self.ScanResults = FileScanResultModel()

            LocalRootPath = self._ToLocalPath(RootFolderPath)

            # Step 0: Clean up any existing duplicate records before scanning
            # Skipped during continuous scans where cleanup runs once before the loop
            if not SkipDuplicateCleanup:
                CleanupResult = self.Repository.CleanupDuplicateMediaFiles()
                if CleanupResult.get('DuplicatesRemoved', 0) > 0:
                    LoggingService.LogInfo(f"Pre-scan cleanup removed {CleanupResult['DuplicatesRemoved']} duplicate records", 'PerformScan', 'FileScanningBusinessService')

            # Step 1: Calculate directory size (uses local path)
            self.ScanProgress = 10.0
            TotalSizeGB = self.FileManager.CalculateDirectorySize(LocalRootPath)

            # Step 2: Get or create root folder record (canonical path stored in DB)
            self.ScanProgress = 20.0
            RootFolder = self.GetOrCreateRootFolder(RootFolderPath, TotalSizeGB)

            if not RootFolder or not RootFolder.Id:
                LoggingService.LogError(f"Failed to create or get root folder for: {RootFolderPath}", 'PerformScan', 'FileScanningBusinessService')
                return {
                    'Success': False,
                    'Message': f'Failed to create root folder record for: {RootFolderPath}',
                    'Error': 'RootFolderCreationFailed'
                }

            # Step 3: Walk the LOCAL path; convert results back to canonical
            # for DB storage so MediaFiles.FilePath stays portable across hosts.
            self.ScanProgress = 30.0
            LocalMediaFiles = self.FileManager.ScanDirectory(LocalRootPath, Recursive)
            MediaFiles = [self._ToCanonicalPath(p) for p in LocalMediaFiles]
            self.ScanResults.TotalFilesFound = len(MediaFiles)
            self.ScanResults.RootFolderId = RootFolder.Id

            # Build per-scan show/episode index ONCE (criterion 25). Without
            # this, FindFuzzyFileMatch reloads + regex-parses all RootFolder
            # rows for every new file -- O(N x M) wall clock.
            self._ShowEpisodeIndex = self._BuildShowEpisodeIndex(RootFolder.Id)
            try:
                # Step 4: Process each media file (without metadata extraction for speed)
                self.ProcessMediaFiles(MediaFiles, RootFolder.Id, RootFolderPath, ExtractMetadata=False)
            finally:
                self._ShowEpisodeIndex = None

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
        """Get existing root folder or create a new one.

        RootFolderPath is canonical (Windows-style). On Windows we walk the
        filesystem to recover correct case; on Linux containers the raw path
        does not exist on the fs (it's an SMB drive letter), so we trust the
        canonical input as authoritative and skip fs canonicalization.
        """
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            UseFsCanonicalization = not (Ctx and Ctx.PathTranslation and Ctx.PathTranslation.IsLinux)

            CanonicalPath = (self.GetCanonicalPathFromFilesystem(RootFolderPath)
                             if UseFsCanonicalization else RootFolderPath)

            # Find an existing row by canonical match. On Linux we compare strings
            # directly (case-sensitive); on Windows we additionally pass through
            # GetCanonicalPathFromFilesystem to recover the on-disk case.
            ExistingFolders = self.Repository.GetAllRootFolders()
            for Folder in ExistingFolders:
                try:
                    if UseFsCanonicalization:
                        if os.path.exists(Folder.RootFolder):
                            ExistingCanonical = self.GetCanonicalPathFromFilesystem(Folder.RootFolder)
                            if ExistingCanonical == CanonicalPath:
                                Folder.RootFolder = CanonicalPath
                                Folder.LastScannedDate = datetime.now(timezone.utc)
                                Folder.TotalSizeGB = TotalSizeGB
                                FolderId = self.Repository.SaveRootFolder(Folder)
                                Folder.Id = FolderId
                                LoggingService.LogInfo(f"Updated existing root folder: {CanonicalPath}")
                                return Folder
                    else:
                        # Linux container: trust the canonical strings.
                        if Folder.RootFolder == CanonicalPath:
                            Folder.LastScannedDate = datetime.now(timezone.utc)
                            Folder.TotalSizeGB = TotalSizeGB
                            FolderId = self.Repository.SaveRootFolder(Folder)
                            Folder.Id = FolderId
                            LoggingService.LogInfo(f"Updated existing root folder: {CanonicalPath}")
                            return Folder
                except Exception:
                    continue

            NewFolder = RootFolderModel(
                RootFolder=CanonicalPath,
                LastScannedDate=datetime.now(timezone.utc),
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

    def _BuildShowEpisodeIndex(self, RootFolderId: int) -> Dict[tuple, List[MediaFileModel]]:
        """Owns FileScanning.feature.md criterion 25 (per-scan precompute).
        Single GetMediaFilesByRootFolderId call + one ExtractShowInfo per row;
        FindFuzzyFileMatch then looks up candidates in O(1) instead of
        re-loading and re-parsing all RootFolder rows for every new file.
        Read-only after build, safe for the parallel processor pool.
        """
        Index: Dict[tuple, List[MediaFileModel]] = {}
        try:
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)
            for DbFile in DatabaseFiles:
                if not DbFile.FileName:
                    continue
                Info = self.ExtractShowInfo(DbFile.FileName)
                if not (Info.get('ShowName') and Info.get('Season') and Info.get('Episode')):
                    continue
                Key = (Info['ShowName'].lower(), Info['Season'], Info['Episode'])
                Index.setdefault(Key, []).append(DbFile)
            LoggingService.LogInfo(
                f"Built show/episode index: {len(DatabaseFiles)} rows -> {len(Index)} (show, season, episode) keys",
                'FileScanningBusinessService', '_BuildShowEpisodeIndex'
            )
        except Exception as e:
            LoggingService.LogException("Error building show/episode index", e, 'FileScanningBusinessService', '_BuildShowEpisodeIndex')
        return Index

    def FindFuzzyFileMatch(self, FilePath: str, FileName: str, FileSizeMB: float, RootFolderId: int) -> Optional[MediaFileModel]:
        """Find a fuzzy match for a file in the database. When a per-scan
        show/episode index is set on `self._ShowEpisodeIndex` (criterion 25),
        candidate lookup is O(1); otherwise falls back to the legacy O(N)
        per-call scan for safety on out-of-band callers.
        """
        try:
            FileShowInfo = self.ExtractShowInfo(FileName)
            if not FileShowInfo['ShowName'] or not FileShowInfo['Season'] or not FileShowInfo['Episode']:
                return None

            Index = getattr(self, '_ShowEpisodeIndex', None)
            if Index is not None:
                Candidates = Index.get((FileShowInfo['ShowName'].lower(), FileShowInfo['Season'], FileShowInfo['Episode']), [])
            else:
                Candidates = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)

            for DbFile in Candidates:
                if Index is None:
                    DbShowInfo = self.ExtractShowInfo(DbFile.FileName)
                    if not self.IsFuzzyMatch(FileShowInfo, DbShowInfo, FileSizeMB, DbFile.SizeMB):
                        continue
                else:
                    if abs((FileSizeMB or 0) - (DbFile.SizeMB or 0)) >= 1.0:
                        continue

                if not os.path.exists(self._ToLocalPath(DbFile.FilePath)):
                    return DbFile
                else:
                    return None

            return None

        except Exception as e:
            LoggingService.LogException("Error in fuzzy file matching", e)
            return None

    def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process a single media file with fuzzy matching and optional metadata extraction.

        FilePath is the canonical (Windows-style) path stored in the DB. On Linux
        containers, fs ops use LocalPath (translated via WorkerContext); DB lookups
        and inserts use the canonical FilePath so MediaFiles rows stay portable.
        """
        try:
            # Canonicalize path string for DB consistency (lookups vs inserts).
            FilePath = os.path.normpath(FilePath)
            LocalPath = self._ToLocalPath(FilePath)

            # Existence check uses the translated local path.
            if not os.path.exists(LocalPath):
                LoggingService.LogWarning(f"File does not exist on disk: {FilePath} (local: {LocalPath})", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                ExistingFile = self.Repository.GetMediaFileByPath(FilePath)
                if ExistingFile:
                    LoggingService.LogInfo(f"Deleting database entry for missing file: {FilePath} (ID: {ExistingFile.Id})", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    self.Repository.DeleteMediaFile(ExistingFile.Id)
                else:
                    LoggingService.LogDebug(f"No database entry found for missing file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                return

            # Filesystem reads use LocalPath; DB writes use canonical FilePath.
            FileSizeMB = self.FileManager.GetFileSizeMB(LocalPath)
            FileName = self.FileManager.GetFileNameFromPath(FilePath)
            FileModificationTime = self.GetFileModificationTime(LocalPath)

            try:
                FileSize = os.path.getsize(LocalPath)
            except Exception:
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
                    ExistingFile.LastScannedDate = datetime.now(timezone.utc)

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                        self.ExtractAndUpdateMetadata(ExistingFile, LocalPath)

                    self.Repository.SaveMediaFile(ExistingFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.UpdatedFilesCount += 1
                else:
                    # FILE UNCHANGED - SKIP PROCESSING (HUGE PERFORMANCE WIN!)
                    # Only update LastScannedDate to mark it was checked
                    ExistingFile.LastScannedDate = datetime.now(timezone.utc)
                    self.UpdateLastScannedDate(ExistingFile.Id, ExistingFile.LastScannedDate)
                    self.ScanResults.TotalFilesSkipped += 1
                    LoggingService.LogDebug(f"Skipped unchanged file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

            else:
                # File doesn't exist in database - check for fuzzy match (renamed file)
                FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)

                from Core.PathStorage import LoadStorageRoots, Parse as PathParse
                StorageRootId, RelativePath = PathParse(FilePath, LoadStorageRoots())

                if FuzzyMatch:
                    # Found a fuzzy match - this is likely a renamed file
                    FuzzyMatch.FilePath = FilePath  # Update to new path
                    FuzzyMatch.StorageRootId = StorageRootId
                    FuzzyMatch.RelativePath = RelativePath or ''
                    FuzzyMatch.FileName = FileName  # Update to new filename
                    FuzzyMatch.SizeMB = FileSizeMB  # Update to new size
                    FuzzyMatch.FileModificationTime = FileModificationTime
                    FuzzyMatch.SeasonId = None  # Season functionality disabled
                    FuzzyMatch.LastScannedDate = datetime.now(timezone.utc)

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(FuzzyMatch):
                        self.ExtractAndUpdateMetadata(FuzzyMatch, LocalPath)

                    self.Repository.SaveMediaFile(FuzzyMatch)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.UpdatedFilesCount += 1
                else:
                    # No fuzzy match found - create new file record. The
                    # transcoded-file-match path was retired with criterion 18a
                    # (post-FileReplacement, transcoded outputs land at the
                    # original path atomically; there is no _transcoded/ dir).
                    LoggingService.LogInfo(f"New file discovered: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    NewFile = MediaFileModel(
                        SeasonId=None,  # Season functionality disabled
                        StorageRootId=StorageRootId,
                        RelativePath=RelativePath or '',
                        FilePath=FilePath,
                        FileName=FileName,
                        SizeMB=FileSizeMB,
                        FileModificationTime=FileModificationTime,
                        LastModifiedDate=FileModificationTime,
                        FileSize=FileSize,
                        LastScannedDate=datetime.now(timezone.utc)
                    )

                    if ExtractMetadata:
                        self.ExtractAndUpdateMetadata(NewFile, LocalPath)

                    self.Repository.SaveMediaFile(NewFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.NewFilesCount += 1

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
        """Get current scan status and progress (public API for /api/Scan/Status).

        Aggregates the running ScanJobs rows into the UI-shaped dict the
        FileScanning page expects. Uses the unified Repository.GetRunningScans
        per criterion 18b -- the eight is-running wrappers are gone.
        """
        try:
            RunningScans = self.Repository.GetRunningScans()

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

            PrimaryScan = RunningScans[0]
            Results = FileScanResultModel()
            Results.Id = PrimaryScan['JobId']
            Results.RootFolderId = None
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

            self.IsScanning = True
            self.ScanProgress = PrimaryScan['Progress'] or 0.0
            self.CurrentScanDirectory = PrimaryScan['CurrentDirectory'] or ''

            return {
                'Success': True,
                'IsScanning': True,
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
            LoggingService.LogException("Error getting scan status", e, "FileScanningBusinessService", "GetScanStatus")
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

    def AddRootFolder(self, RootFolderPath: str, PreferredWorkerName: str = None) -> Dict[str, Any]:
        """Add a new root folder for scanning.

        Validates the path format, checks for duplicates, and inserts into RootFolders.
        Does NOT require the path to be accessible from the WebService host -- the
        worker that scans it validates accessibility at scan time (criterion 20).
        """
        try:
            if not RootFolderPath or not RootFolderPath.strip():
                return {'Success': False, 'Message': 'Root folder path is required'}

            RootFolderPath = RootFolderPath.strip()
            # Ensure trailing backslash for drive roots (e.g. T:\ not T:)
            if len(RootFolderPath) == 2 and RootFolderPath[1] == ':':
                RootFolderPath += '\\'

            # Check for duplicates (case-insensitive)
            Existing = self.Repository.GetAllRootFolders()
            for Folder in Existing:
                if Folder.RootFolder.lower().rstrip('\\') == RootFolderPath.lower().rstrip('\\'):
                    return {'Success': False, 'Message': f'Root folder already exists: {Folder.RootFolder}'}

            NewFolder = RootFolderModel(
                Id=None,
                RootFolder=RootFolderPath,
                LastScannedDate=None,
                TotalSizeGB=0.0,
                PreferredWorkerName=PreferredWorkerName,
            )
            NewId = self.Repository.SaveRootFolder(NewFolder)
            LoggingService.LogInfo(f"Added root folder: {RootFolderPath} (Id={NewId}, PreferredWorker={PreferredWorkerName})", 'FileScanningBusinessService', 'AddRootFolder')
            return {'Success': True, 'Message': 'Root folder added successfully', 'Data': {'Id': NewId, 'RootFolder': RootFolderPath}}

        except Exception as e:
            LoggingService.LogException("Error adding root folder", e, 'FileScanningBusinessService', 'AddRootFolder')
            return {'Success': False, 'Message': f'Error adding root folder: {str(e)}'}

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
        """Get all ScanDir%-prefixed entries from SystemSettings.

        Routed through SystemSettingsRepository per criterion 18d -- the
        FileScanningRepository duplicate methods were retired.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            return SystemSettingsRepository().GetScanDirectories()
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
                    CurrentFileName = ntpath.basename(MediaFile.FilePath)
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
            return datetime.now(timezone.utc)

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
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)
            else:
                # Record failure
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"Failed to extract metadata for {FilePath}: {ErrorMessage}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
                MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
                MediaFile.LastFFprobeError = ErrorMessage
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)

        except Exception as e:
            LoggingService.LogException("Error extracting and updating metadata", e, 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
            MediaFile.LastFFprobeError = str(e)
            MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)

    def ReconcileWithDisk(self, MediaFiles: List[str], RootFolderId: int) -> Dict[str, Any]:
        """Single-pass merge of move-detection and missing-file cleanup against
        the disk file list already produced by `FileManager.ScanDirectory`.
        Owns FileScanning.feature.md criterion 23 (throughput dimension) and
        moves this code path to the path-storage Phase 4 read pattern: set
        membership is computed on `(StorageRootId, RelativePath.lower())`
        tuples, not on OS-coupled `FilePath` strings. Same comparison works
        identically on Windows and Linux workers; no `_ToCanonicalPath`
        round-trip in the comparison hot path.

        Per-row decision:
          - DB row's `(StorageRootId, RelativePath.lower())` in disk set ->
            skip; the per-file processor handles it normally.
          - DB row has NULL StorageRootId (rows that missed the Phase 2
            backfill, ~2 in production) -> preserve; never delete.
          - Not in disk set, fuzzy match found by basename + IsSameFile ->
            update DB row's FilePath / FileName / StorageRootId /
            RelativePath in place (preserves Id and metadata).
          - Not in disk set, no fuzzy match -> delete DB row.

        Safety guard: if proposed delete count exceeds 90% of DatabaseFiles,
        abort the reconcile entirely and log an error. This catches the
        catastrophic translation-failure case where every disk path falls
        outside any registered StorageRoot (e.g. WorkerShareMappings missing
        on a worker that shouldn't have been ScanEnabled).

        Move-detection cap (criterion 12) is preserved: above the cap, the
        fuzzy-match step is skipped and missing rows are deleted directly
        rather than reassigned. The throughput win still applies; only the
        rename-recovery semantics degrade.
        """
        try:
            LoggingService.LogInfo(
                f"=== RECONCILE WITH DISK STARTED ({len(MediaFiles)} disk files) ===",
                'ReconcileWithDisk', 'FileScanningBusinessService'
            )

            from Core.PathStorage import LoadStorageRoots, Parse as PathParse
            StorageRoots = LoadStorageRoots()

            # Build OS-independent disk set keyed on (StorageRootId, RelativePath.lower()).
            # Disk paths that don't parse to any registered StorageRoot are skipped --
            # that's the right behavior (we won't claim those files exist).
            DiskSet: set = set()
            DiskByBasenameLower: Dict[str, List[tuple]] = {}
            UnparseableCount = 0
            for CanonicalPath in MediaFiles:
                Sid, Rel = PathParse(CanonicalPath, StorageRoots)
                if Sid is None or Rel is None:
                    UnparseableCount += 1
                    continue
                DiskSet.add((Sid, Rel.lower()))
                Basename = os.path.basename(CanonicalPath).lower()
                DiskByBasenameLower.setdefault(Basename, []).append((CanonicalPath, Sid, Rel))
            if UnparseableCount > 0:
                LoggingService.LogWarning(
                    f"Reconcile: {UnparseableCount} disk paths did not match any registered StorageRoot prefix; skipped from disk set",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )

            RootFolder = self.Repository.GetRootFolderById(RootFolderId)
            if not RootFolder:
                LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'ReconcileWithDisk', 'FileScanningBusinessService')
                return {'Success': False, 'ErrorMessage': 'Root folder not found'}
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(RootFolder.RootFolder)

            MaxFiles = self._GetMoveDetectionMaxFiles()
            MoveDetectionEnabled = len(DatabaseFiles) <= MaxFiles
            if not MoveDetectionEnabled:
                LoggingService.LogWarning(
                    f"Move detection disabled: {len(DatabaseFiles)} DB rows exceed limit {MaxFiles}; missing files will be deleted, not reassigned",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )

            # First pass: classify every DB row as keep / reassign / delete WITHOUT
            # mutating the database. Lets the safety guard veto the whole reconcile
            # before a single row is touched.
            ToReassign: List[tuple] = []  # (DbFile, CandidateCanonical, CandidateSid, CandidateRel)
            ToDelete: List = []  # DbFile rows to delete
            PreservedNullStorageRoot = 0
            for DbFile in DatabaseFiles:
                DbSid = getattr(DbFile, 'StorageRootId', None)
                DbRel = getattr(DbFile, 'RelativePath', None) or ''
                if DbSid is None:
                    PreservedNullStorageRoot += 1
                    continue  # row missed Phase 2 backfill; never delete here
                if (DbSid, DbRel.lower()) in DiskSet:
                    continue  # exists on disk

                ResolvedMove = None
                if MoveDetectionEnabled and DbFile.FileName:
                    Candidates = DiskByBasenameLower.get(DbFile.FileName.lower(), [])
                    for (CandidateCanonical, CandidateSid, CandidateRel) in Candidates:
                        if (CandidateSid, CandidateRel.lower()) == (DbSid, DbRel.lower()):
                            continue  # same logical path
                        LocalCandidate = self._ToLocalPath(CandidateCanonical)
                        if self.IsSameFile(DbFile, LocalCandidate):
                            ResolvedMove = (CandidateCanonical, CandidateSid, CandidateRel)
                            break

                if ResolvedMove:
                    ToReassign.append((DbFile, *ResolvedMove))
                else:
                    ToDelete.append(DbFile)

            # Safety guard: refuse to delete >90% of DB rows in one reconcile pass.
            # Catches the "translation broken on this worker, every row looks
            # missing" failure mode that would otherwise wipe the rootfolder.
            if DatabaseFiles and len(ToDelete) > 0.9 * len(DatabaseFiles):
                LoggingService.LogError(
                    f"Reconcile ABORTED: would delete {len(ToDelete)} of {len(DatabaseFiles)} rows "
                    f"({100.0 * len(ToDelete) / len(DatabaseFiles):.1f}%). Likely translation failure -- "
                    f"check StorageRootResolutions for this worker. Disk set has {len(DiskSet)} entries; "
                    f"{UnparseableCount} disk paths were unparseable.",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                return {
                    'Success': False,
                    'ErrorMessage': 'Reconcile safety guard tripped (>90% delete proposal)',
                    'ProposedDeletes': len(ToDelete),
                    'DatabaseRows': len(DatabaseFiles),
                }

            # Second pass: execute the planned mutations.
            MovedCount = 0
            DeletedCount = 0
            for (DbFile, CandidateCanonical, CandidateSid, CandidateRel) in ToReassign:
                LoggingService.LogInfo(
                    f"Reassigning moved file: {DbFile.FilePath} -> {CandidateCanonical}",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                DbFile.FilePath = CandidateCanonical
                DbFile.FileName = ntpath.basename(CandidateCanonical)
                DbFile.StorageRootId = CandidateSid
                DbFile.RelativePath = CandidateRel
                DbFile.LastScannedDate = datetime.now(timezone.utc)
                self.Repository.SaveMediaFile(DbFile)
                MovedCount += 1
                self.ScanResults.UpdatedFilesCount += 1
            for DbFile in ToDelete:
                LoggingService.LogInfo(
                    f"Deleting DB row for missing file: {DbFile.FilePath} (Id={DbFile.Id})",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                self.Repository.DeleteMediaFile(DbFile.Id)
                DeletedCount += 1
                self.ScanResults.DeletedFilesCount += 1

            LoggingService.LogInfo(
                f"=== RECONCILE WITH DISK COMPLETED === moved={MovedCount} deleted={DeletedCount} preserved_null_storageroot={PreservedNullStorageRoot}",
                'ReconcileWithDisk', 'FileScanningBusinessService'
            )
            return {'Success': True, 'MovedFiles': MovedCount, 'DeletedFiles': DeletedCount, 'PreservedNullStorageRoot': PreservedNullStorageRoot}
        except Exception as e:
            LoggingService.LogException("Error in ReconcileWithDisk", e, 'ReconcileWithDisk', 'FileScanningBusinessService')
            return {'Success': False, 'ErrorMessage': str(e)}

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
            # Translate canonical (Windows-style) DB path to local for the fs check.
            DeletedCount = 0
            for DbFile in DatabaseFiles:
                if not os.path.exists(self._ToLocalPath(DbFile.FilePath)):
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

            # Search each root folder for matching filename. Translate the
            # canonical RootFolder path to local for fs ops; convert any found
            # local path back to canonical before returning so DB stays portable.
            for RootFolder in AllRootFolders:
                LocalRoot = self._ToLocalPath(RootFolder.RootFolder)
                if not os.path.exists(LocalRoot):
                    LoggingService.LogDebug(f"Root folder does not exist (local: {LocalRoot}): {RootFolder.RootFolder}", 'FindMovedFile', 'FileScanningBusinessService')
                    continue

                try:
                    for root, dirs, files in os.walk(LocalRoot):
                        for file in files:
                            if file == SearchFileName:
                                FoundLocalPath = os.path.join(root, file)
                                FoundCanonicalPath = self._ToCanonicalPath(FoundLocalPath)

                                # Skip if this is the original path (not moved)
                                if FoundCanonicalPath.lower() == DbFile.FilePath.lower():
                                    continue

                                # Verify it's the same file (uses local path for fs reads)
                                if self.IsSameFile(DbFile, FoundLocalPath):
                                    LoggingService.LogInfo(f"MOVED FILE FOUND: '{DbFile.FilePath}' -> '{FoundCanonicalPath}'", 'FindMovedFile', 'FileScanningBusinessService')
                                    return {
                                        'OldPath': DbFile.FilePath,
                                        'NewPath': FoundCanonicalPath,
                                    }

                except Exception as e:
                    LoggingService.LogException(f"Error searching root folder: {RootFolder.RootFolder}", e, 'FindMovedFile', 'FileScanningBusinessService')
                    continue

            LoggingService.LogDebug(f"No moved location found for: {DbFile.FileName}", 'FindMovedFile', 'FileScanningBusinessService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding moved file", e, 'FindMovedFile', 'FileScanningBusinessService')
            return None

    def _GetMoveDetectionMaxFiles(self) -> int:
        """Read the move-detection ceiling from SystemSettings each call (no cache)."""
        Default = 100000
        try:
            Result = self.Repository.DatabaseService.ExecuteQuery(
                "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s",
                ('MoveDetectionMaxFiles',),
            )
            if Result:
                Value = Result[0].get('SettingValue')
                if Value is not None:
                    return int(Value)
        except Exception as e:
            LoggingService.LogException("Error reading MoveDetectionMaxFiles, using default", e, 'FileScanningBusinessService', '_GetMoveDetectionMaxFiles')
        return Default

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

            # Performance ceiling: skip move detection above SystemSettings('MoveDetectionMaxFiles').
            # Read fresh from the DB on every call (do not cache) so an operator can raise the cap
            # without restarting workers. Default 100000 mirrors the migration seed.
            MaxFiles = self._GetMoveDetectionMaxFiles()
            if len(DatabaseFiles) > MaxFiles:
                LoggingService.LogWarning(f"Skipping move detection: Database has {len(DatabaseFiles)} files (exceeds limit of {MaxFiles})", 'DetectMovedFiles', 'FileScanningBusinessService')
                return {
                    'Success': True,
                    'MovedFiles': 0,
                    'DeletedFiles': 0,
                    'Skipped': True,
                    'Reason': f'File count exceeds limit ({len(DatabaseFiles)} > {MaxFiles})'
                }

            # Check each file for moves (translate canonical -> local for fs check)
            for DbFile in DatabaseFiles:
                if not os.path.exists(self._ToLocalPath(DbFile.FilePath)):
                    # File missing - try to find it
                    MovedFile = self.FindMovedFile(DbFile)

                    if MovedFile:
                        # File was moved, update path
                        LoggingService.LogInfo(f"Updating moved file: {MovedFile['OldPath']} -> {MovedFile['NewPath']}", 'DetectMovedFiles', 'FileScanningBusinessService')
                        DbFile.FilePath = MovedFile['NewPath']
                        DbFile.FileName = ntpath.basename(MovedFile['NewPath'])
                        DbFile.LastScannedDate = datetime.now(timezone.utc)
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

            # Reconcile DB rows against the disk file list in a single pass.
            # Replaces the previous DetectMovedFiles + CleanupMissingFiles
            # sequence which serially stat-checked every DB row twice over
            # NFS (criterion 23 fix).
            if RootFolderId:
                ReconcileResult = self.ReconcileWithDisk(MediaFiles, RootFolderId)
                LoggingService.LogInfo(
                    f"Reconcile result: moved={ReconcileResult.get('MovedFiles', 0)} deleted={ReconcileResult.get('DeletedFiles', 0)}",
                    'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService'
                )

            TotalFiles = len(MediaFiles)
            ProcessedCount = 0
            ProgressLock = threading.Lock()

            def ProcessSingleFile(FilePath: str):
                """Process a single file and return result."""
                nonlocal ProcessedCount

                try:
                    # Process the file with metadata extraction
                    self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath, ExtractMetadata)

                    # Update progress thread-safely. Mirror to ScanResults so
                    # the heartbeat thread (criterion 17) writes a real
                    # ProcessedFiles count, not zero, mid-scan.
                    with ProgressLock:
                        ProcessedCount += 1
                        Progress = 30.0 + (60.0 * ProcessedCount / TotalFiles)
                        self.ScanProgress = Progress
                        self.ScanResults.TotalFilesProcessed = ProcessedCount
                        self.CurrentScanDirectory = os.path.dirname(FilePath)

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
        """Add or update a ScanDir%% SystemSettings entry. Routes through
        SystemSettingsRepository per criterion 18d.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            settings = SystemSettingsRepository()

            if not Key:
                # Pick next ScanDir<N>
                Existing = settings.GetScanDirectories()
                Numbers = []
                for E in Existing:
                    K = E.get('Key', '')
                    if K.startswith('ScanDir'):
                        try:
                            Numbers.append(int(K.replace('ScanDir', '')))
                        except ValueError:
                            continue
                NextNumber = 1
                while NextNumber in Numbers:
                    NextNumber += 1
                Key = f'ScanDir{NextNumber}'

            result = settings.AddOrUpdateSystemSetting(Key, Path, Description, 'string')
            if result:
                return {'Success': True, 'Message': f'Successfully saved scan directory: {Path}'}
            return {'Success': False, 'Error': 'Failed to save scan directory to database'}

        except Exception as e:
            LoggingService.LogException("Error adding/updating scan directory", e, "AddOrUpdateScanDirectory", "FileScanningBusinessService")
            return {'Success': False, 'Error': f'Error adding/updating scan directory: {str(e)}'}

    def DeleteScanDirectory(self, Key: str) -> Dict[str, Any]:
        """Delete a ScanDir%% SystemSettings entry. Routes through
        SystemSettingsRepository per criterion 18d.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            result = SystemSettingsRepository().DeleteSystemSetting(Key)
            if result:
                return {'Success': True, 'Message': f'Successfully deleted scan directory: {Key}'}
            return {'Success': False, 'Error': f'Scan directory {Key} not found or could not be deleted'}

        except Exception as e:
            LoggingService.LogException("Error deleting scan directory", e, "DeleteScanDirectory", "FileScanningBusinessService")
            return {'Success': False, 'Error': f'Error deleting scan directory: {str(e)}'}

