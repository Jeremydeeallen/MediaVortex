import os
import uuid
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Services.FileManagerService import FileManagerService
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class FileScanningBusinessService:
    """Orchestrates the file scanning process and coordinates between services."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, FileManagerInstance: FileManagerService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService()
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
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            if Result:
                self.CurrentJobId = Result[0]['JobId']
                LoggingService.LogInfo(f"Found existing running scan with JobId: {self.CurrentJobId}", 'FileScanningBusinessService', 'CheckForExistingRunningScan')
            else:
                LoggingService.LogInfo("No existing running scans found", 'FileScanningBusinessService', 'CheckForExistingRunningScan')
        except Exception as e:
            LoggingService.LogException("Error checking for existing running scans", e, 'FileScanningBusinessService', 'CheckForExistingRunningScan')
    
    def StartScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
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
            
            # Validate the root folder path
            if not RootFolderPath or not os.path.exists(RootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Root folder does not exist: {RootFolderPath}',
                    'Error': 'InvalidPath'
                }
            
            if not os.path.isdir(RootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Path is not a directory: {RootFolderPath}',
                    'Error': 'NotDirectory'
                }
            
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
            result = self.PerformScan(RootFolderPath, Recursive)
            
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
            VALUES (?, ?, ?, 'Running', ?, ?, 'File')
            """
            Now = datetime.now()
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now))
            
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
                UpdateFields.append("Status = ?")
                UpdateValues.append(Status)
            
            if Progress is not None:
                UpdateFields.append("Progress = ?")
                UpdateValues.append(Progress)
            
            if CurrentDirectory is not None:
                UpdateFields.append("CurrentDirectory = ?")
                UpdateValues.append(CurrentDirectory)
            
            if ProcessId is not None:
                UpdateFields.append("ProcessId = ?")
                UpdateValues.append(ProcessId)
            
            if StartTime is not None:
                UpdateFields.append("StartTime = ?")
                UpdateValues.append(StartTime)
            
            if EndTime is not None:
                UpdateFields.append("EndTime = ?")
                UpdateValues.append(EndTime)
            
            if ErrorMessage is not None:
                UpdateFields.append("ErrorMessage = ?")
                UpdateValues.append(ErrorMessage)
            
            if ScanResults is not None:
                UpdateFields.extend([
                    "TotalFiles = ?",
                    "ProcessedFiles = ?", 
                    "SkippedFiles = ?",
                    "EncodingErrors = ?"
                ])
                UpdateValues.extend([
                    ScanResults.TotalFilesFound,
                    ScanResults.TotalFilesProcessed,
                    ScanResults.TotalFilesSkipped,
                    ScanResults.TotalFilesWithErrors
                ])
            
            # Always update LastUpdated
            UpdateFields.append("LastUpdated = ?")
            UpdateValues.append(datetime.now())
            
            # Add JobId for WHERE clause
            UpdateValues.append(JobId)
            
            Query = f"UPDATE ScanJobs SET {', '.join(UpdateFields)} WHERE JobId = ?"
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, UpdateValues)
            
        except Exception as e:
            LoggingService.LogException(f"Error updating job status for {JobId}", e, 'UpdateJobStatus', 'FileScanningBusinessService')
    
    
    def IsScanRunning(self) -> bool:
        """Check if there's currently a scan running."""
        try:
            # Check for any running scans in database
            Query = "SELECT COUNT(*) as Count FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            return Result[0]['Count'] > 0 if Result else False
            
        except Exception as e:
            LoggingService.LogException("Error checking scan status", e)
            return False
    
    def GetRunningScanCount(self) -> int:
        """Get the number of currently running scans."""
        try:
            Query = "SELECT COUNT(*) as Count FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
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
            FROM ScanJobs WHERE JobId = ?
            """
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (JobId,))
            
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
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
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
            AND LastUpdated < datetime('now', '-7 days')
            """
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query)
            LoggingService.LogInfo("Cleaned up old scan jobs")
        except Exception as e:
            LoggingService.LogException("Error cleaning up scan jobs", e)
    
    def PerformScan(self, RootFolderPath: str, Recursive: bool) -> Dict[str, Any]:
        """Perform the actual scanning process."""
        try:
            LoggingService.LogInfo("Starting scan of directory: {}", RootFolderPath)
            
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
                    metadataResult = self.ExtractMetadataForExistingFiles(RootFolder.Id)
                else:
                    LoggingService.LogWarning("No RootFolderId available - skipping automatic metadata extraction", 'PerformScan', 'FileScanningBusinessService')
                    metadataResult = {'Success': True, 'Message': 'No RootFolderId - metadata extraction skipped', 'ProcessedFiles': 0}
                if metadataResult.get('Success', False):
                    processedFiles = metadataResult.get('ProcessedFiles', 0)
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
        """Get existing root folder or create a new one."""
        try:
            # Check if root folder already exists
            ExistingFolders = self.DatabaseManager.GetAllRootFolders()
            
            for Folder in ExistingFolders:
                if Folder.RootFolder == RootFolderPath:
                    # Update existing folder
                    Folder.LastScannedDate = datetime.now()
                    Folder.TotalSizeGB = TotalSizeGB
                    FolderId = self.DatabaseManager.SaveRootFolder(Folder)
                    Folder.Id = FolderId
                    LoggingService.LogInfo("Updated existing root folder: {}", RootFolderPath)
                    return Folder
            
            # Create new root folder
            NewFolder = RootFolderModel(
                RootFolder=RootFolderPath,
                LastScannedDate=datetime.now(),
                TotalSizeGB=TotalSizeGB
            )
            FolderId = self.DatabaseManager.SaveRootFolder(NewFolder)
            NewFolder.Id = FolderId
            LoggingService.LogInfo("Created new root folder: {}", RootFolderPath)
            return NewFolder
            
        except Exception as e:
            LoggingService.LogException("Error managing root folder", e)
            raise
    
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
    
    def FindFuzzyFileMatch(self, FilePath: str, FileName: str, FileSizeMB: float, RootFolderId: int) -> Optional[MediaFileModel]:
        """Find a fuzzy match for a file in the database."""
        try:
            # Get all files for this root folder
            DatabaseFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderId)
            
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
    
    
    
    
    def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process a single media file with fuzzy matching and optional metadata extraction."""
        try:
            # Get file information
            FileSizeMB = self.FileManager.GetFileSizeMB(FilePath)
            FileName = self.FileManager.GetFileNameFromPath(FilePath)
            FileModificationTime = self.GetFileModificationTime(FilePath)
            
            # Check if this file already exists in database (exact match)
            ExistingFile = self.DatabaseManager.GetMediaFileByPath(FilePath)
            if ExistingFile:
                # Check if file has actually changed
                if self.HasFileChanged(ExistingFile, FileSizeMB, FileName, FileModificationTime):
                    # File has changed - update it
                    ExistingFile.SizeMB = FileSizeMB
                    ExistingFile.FileName = FileName
                    ExistingFile.FileModificationTime = FileModificationTime
                    ExistingFile.SeasonId = None  # Season functionality disabled
                    ExistingFile.LastScannedDate = datetime.now()
                    # Note: RootFolderId is not stored in MediaFiles table - files are associated by FilePath
                    
                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                        self.ExtractAndUpdateMetadata(ExistingFile, FilePath)
                    
                    self.DatabaseManager.SaveMediaFile(ExistingFile)
                    self.ScanResults.TotalFilesProcessed += 1
                else:
                    # File hasn't changed - just update scan date and skip database update
                    ExistingFile.LastScannedDate = datetime.now()
                    # Only update the LastScannedDate without triggering a full save
                    self.UpdateLastScannedDate(ExistingFile.Id, ExistingFile.LastScannedDate)
                    self.ScanResults.TotalFilesSkipped += 1
                    LoggingService.LogDebug("Skipped unchanged file: {}", FilePath)
                
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
                    
                    self.DatabaseManager.SaveMediaFile(FuzzyMatch)
                    self.ScanResults.TotalFilesProcessed += 1
                else:
                    # Create new file record
                    NewFile = MediaFileModel(
                        SeasonId=None,  # Season functionality disabled
                        FilePath=FilePath,
                        FileName=FileName,
                        SizeMB=FileSizeMB,
                        FileModificationTime=FileModificationTime,
                        LastScannedDate=datetime.now()
                    )
                    # Note: RootFolderId is not stored in MediaFiles table - files are associated by FilePath
                    
                    # Extract metadata if requested
                    if ExtractMetadata:
                        self.ExtractAndUpdateMetadata(NewFile, FilePath)
                    
                    self.DatabaseManager.SaveMediaFile(NewFile)
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
            return self.DatabaseManager.GetAllRootFolders(SortColumn, SortOrder)
        except Exception as e:
            LoggingService.LogException("Error getting root folders", e)
            return []
    
    def GetMediaFiles(self, RootFolderPath: Optional[str] = None) -> List[MediaFileModel]:
        """Get media files, optionally filtered by root folder."""
        try:
            if RootFolderPath:
                return self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderPath)
            else:
                return self.DatabaseManager.GetAllMediaFiles()
        except Exception as e:
            LoggingService.LogException("Error getting media files", e)
            return []
    
    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            return self.DatabaseManager.DeleteRootFolder(RootFolderId)
        except Exception as e:
            LoggingService.LogException("Error deleting root folder", e)
            return False
    
    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete a media file."""
        try:
            return self.DatabaseManager.DeleteMediaFile(MediaFileId)
        except Exception as e:
            LoggingService.LogException("Error deleting media file", e)
            return False
    
    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings from SystemSettings table."""
        try:
            return self.DatabaseManager.GetScanDirectories()
        except Exception as e:
            LoggingService.LogException("Error getting scan directories", e)
            return []
    
    def GetStatistics(self) -> Dict[str, Any]:
        """Get database statistics for display."""
        try:
            # Get total media files count
            TotalMediaFilesQuery = "SELECT COUNT(*) as Count FROM MediaFiles"
            TotalMediaFilesResult = self.DatabaseManager.DatabaseService.ExecuteQuery(TotalMediaFilesQuery)
            TotalMediaFiles = TotalMediaFilesResult[0]['Count'] if TotalMediaFilesResult else 0
            
            # Get files without profiles count
            FilesWithoutProfilesQuery = "SELECT COUNT(*) as Count FROM MediaFiles WHERE AssignedProfile IS NULL OR AssignedProfile = ''"
            FilesWithoutProfilesResult = self.DatabaseManager.DatabaseService.ExecuteQuery(FilesWithoutProfilesQuery)
            FilesWithoutProfiles = FilesWithoutProfilesResult[0]['Count'] if FilesWithoutProfilesResult else 0
            
            # Get total root folders count
            TotalRootFoldersQuery = "SELECT COUNT(*) as Count FROM RootFolders"
            TotalRootFoldersResult = self.DatabaseManager.DatabaseService.ExecuteQuery(TotalRootFoldersQuery)
            TotalRootFolders = TotalRootFoldersResult[0]['Count'] if TotalRootFoldersResult else 0
            
            # Get total size in GB
            TotalSizeQuery = "SELECT SUM(TotalSizeGB) as TotalSize FROM RootFolders"
            TotalSizeResult = self.DatabaseManager.DatabaseService.ExecuteQuery(TotalSizeQuery)
            TotalSizeGB = TotalSizeResult[0]['TotalSize'] if TotalSizeResult and TotalSizeResult[0]['TotalSize'] else 0.0
            
            # Get last scan date
            LastScanQuery = "SELECT MAX(LastScannedDate) as LastScanDate FROM RootFolders"
            LastScanResult = self.DatabaseManager.DatabaseService.ExecuteQuery(LastScanQuery)
            LastScanDate = LastScanResult[0]['LastScanDate'] if LastScanResult and LastScanResult[0]['LastScanDate'] else 'Never'
            
            # Get files with metadata count
            FilesWithMetadataQuery = """
                SELECT COUNT(*) as Count FROM MediaFiles 
                WHERE VideoBitrateKbps IS NOT NULL 
                AND AudioBitrateKbps IS NOT NULL 
                AND Resolution IS NOT NULL 
                AND Codec IS NOT NULL
            """
            FilesWithMetadataResult = self.DatabaseManager.DatabaseService.ExecuteQuery(FilesWithMetadataQuery)
            FilesWithMetadata = FilesWithMetadataResult[0]['Count'] if FilesWithMetadataResult else 0
            
            # Get files without metadata count
            FilesWithoutMetadata = TotalMediaFiles - FilesWithMetadata
            
            return {
                'TotalMediaFiles': TotalMediaFiles,
                'FilesWithoutProfiles': FilesWithoutProfiles,
                'TotalRootFolders': TotalRootFolders,
                'TotalSizeGB': TotalSizeGB,
                'LastScanDate': LastScanDate,
                'FilesWithMetadata': FilesWithMetadata,
                'FilesWithoutMetadata': FilesWithoutMetadata
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting statistics", e, "FileScanningBusinessService", "GetStatistics")
            return {
                'TotalMediaFiles': 0,
                'FilesWithoutProfiles': 0,
                'TotalRootFolders': 0,
                'TotalSizeGB': 0.0,
                'LastScanDate': 'Error',
                'FilesWithMetadata': 0,
                'FilesWithoutMetadata': 0
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
    
    def UpdateLastScannedDate(self, MediaFileId: int, LastScannedDate: datetime):
        """Update only the LastScannedDate for a media file without full save."""
        try:
            Query = "UPDATE MediaFiles SET LastScannedDate = ? WHERE Id = ?"
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (LastScannedDate, MediaFileId))
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
                MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
                MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')
                
                
                LoggingService.LogDebug(f"Successfully extracted metadata for: {FilePath}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            else:
                # Set default values for failed extraction
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"Failed to extract metadata for {FilePath}: {ErrorMessage}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            
        except Exception as e:
            LoggingService.LogException("Error extracting and updating metadata", e, 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            # Set default values on error
    
    def ProcessMediaFilesWithMetadata(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process media files with optional metadata extraction."""
        try:
            LoggingService.LogFunctionEntry("ProcessMediaFilesWithMetadata", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")
            
            # Cleanup is now handled by the subprocess before calling this method
            # This ensures proper status updates and progress tracking
            
            TotalFiles = len(MediaFiles)
            
            for i, FilePath in enumerate(MediaFiles):
                try:
                    # Update progress
                    Progress = 30.0 + (60.0 * (i + 1) / TotalFiles)
                    self.ScanProgress = Progress
                    
                    # Process the file with metadata extraction
                    self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath, ExtractMetadata)
                    
                except Exception as e:
                    LoggingService.LogException("Error processing media file with metadata", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                    self.ScanErrors.append(f"Error processing {FilePath}: {str(e)}")
                    continue
            
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
                FilesNeedingMetadata = self.DatabaseManager.GetMediaFilesByRootFolderId(RootFolderId)
                LoggingService.LogInfo(f"Found {len(FilesNeedingMetadata)} files for RootFolderId: {RootFolderId}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
            else:
                FilesNeedingMetadata = self.DatabaseManager.GetAllMediaFiles()
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
                        self.DatabaseManager.SaveMediaFile(File)
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
                ExistingKeys = self.DatabaseManager.GetScanDirectories()
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
            result = self.DatabaseManager.AddOrUpdateSystemSetting(Key, Path, Description, 'string')
            
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
            result = self.DatabaseManager.DeleteSystemSetting(Key)
            
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
    
    