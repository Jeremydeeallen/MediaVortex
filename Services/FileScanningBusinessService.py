import os
import subprocess
import uuid
import psutil
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
        self.ScanProcess = None
        self.ScriptPath = Path(__file__).parent.parent / "Scripts" / "ScanDirectoryProcess.py"
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
        """Start scanning a root folder for media files using subprocess."""
        try:
            LoggingService.LogFunctionEntry("StartScanning", 'FileScanningBusinessService', RootFolderPath, Recursive=Recursive)
            
            # Check if there's already a running scan
            if self.IsScanRunning():
                return {
                    'Success': False,
                    'Message': 'Scan is already in progress',
                    'Error': 'ScanInProgress'
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
            
            # Start subprocess with environment variables to preserve Unicode characters
            ProcessArgs = [
                'py', str(self.ScriptPath), JobId, str(Recursive)
            ]
            
            # Set environment variables to preserve Unicode characters in paths
            env = os.environ.copy()
            env['MEDIAVORTEX_ROOT_FOLDER_PATH'] = RootFolderPath
            env['PYTHONIOENCODING'] = 'utf-8'
            
            LoggingService.LogInfo(f"Starting subprocess with args: {ProcessArgs}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Root folder path (env): {RootFolderPath}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Script path: {self.ScriptPath}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Script exists: {self.ScriptPath.exists()}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Working directory: {Path(__file__).parent.parent}", 'FileScanningBusinessService', 'StartScanning')
            
            try:
                self.ScanProcess = subprocess.Popen(
                    ProcessArgs,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=Path(__file__).parent.parent,
                    env=env
                )
                
                # Set scanning state
                self.IsScanning = True
                self.ScanProgress = 0.0
                self.CurrentScanDirectory = RootFolderPath
                
                LoggingService.LogInfo(f"Started scan process {self.ScanProcess.pid} for job {JobId}", 'FileScanningBusinessService', 'StartScanning')
                
                return {
                    'Success': True,
                    'Message': 'Scan started successfully',
                    'JobId': JobId,
                    'ProcessId': self.ScanProcess.pid
                }
                
            except Exception as subprocessError:
                LoggingService.LogException(f"Error starting subprocess for job {JobId}", subprocessError, 'FileScanningBusinessService', 'StartScanning')
                return {
                    'Success': False,
                    'Message': f'Error starting subprocess: {str(subprocessError)}',
                    'Error': 'SubprocessStartError'
                }
            
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
            LoggingService.LogInfo(f"Creating scan job {JobId} for {RootFolderPath}, Recursive: {Recursive}", 'FileScanningBusinessService', 'CreateScanJob')
            
            Query = """
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated, ScanType)
            VALUES (?, ?, ?, 'Pending', ?, ?, 'File')
            """
            Now = datetime.now()
            LoggingService.LogInfo(f"Executing query with params: JobId={JobId}, RootFolderPath={RootFolderPath}, Recursive={Recursive}, Now={Now}")
            
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now))
            LoggingService.LogInfo(f"Successfully created scan job {JobId} for {RootFolderPath}")
            
        except Exception as e:
            LoggingService.LogException(f"Error creating scan job {JobId}", e, 'FileScanningBusinessService', 'CreateScanJob')
            raise
    
    
    def IsScanRunning(self) -> bool:
        """Check if there's currently a scan running."""
        try:
            # Check if we have a current job
            if self.CurrentJobId:
                JobStatus = self.GetScanJobStatus(self.CurrentJobId)
                if JobStatus and JobStatus['Status'] in ['Pending', 'Running']:
                    return True
            
            # Check for any running scans in database
            Query = "SELECT COUNT(*) as Count FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
            Result = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            return Result[0]['Count'] > 0 if Result else False
            
        except Exception as e:
            LoggingService.LogException("Error checking scan status", e)
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
        """Get the status of the current scan job."""
        try:
            if not self.CurrentJobId:
                return {
                    'Success': True,
                    'IsScanning': False,
                    'Progress': 0.0,
                    'CurrentDirectory': '',
                    'RootFolderPath': '',
                    'Results': FileScanResultModel(),
                    'Errors': []
                }
            
            JobStatus = self.GetScanJobStatus(self.CurrentJobId)
            if not JobStatus:
                return {
                    'Success': True,
                    'IsScanning': False,
                    'Progress': 0.0,
                    'CurrentDirectory': '',
                    'RootFolderPath': '',
                    'Results': FileScanResultModel(),
                    'Errors': []
                }
            
            IsScanning = JobStatus['Status'] in ['Pending', 'Running']
            
            # Create FileScanResultModel from database results
            Results = FileScanResultModel()
            Results.Id = JobStatus['JobId']
            Results.RootFolderId = None  # Will be set by the scan process
            Results.ScanStartTime = JobStatus['StartTime']
            Results.ScanEndTime = JobStatus['EndTime']
            Results.TotalFilesFound = JobStatus['TotalFiles'] or 0
            Results.TotalFilesProcessed = JobStatus['ProcessedFiles'] or 0
            Results.TotalFilesSkipped = JobStatus['SkippedFiles'] or 0
            Results.TotalFilesWithErrors = JobStatus['EncodingErrors'] or 0
            Results.ScanStatus = JobStatus['Status']
            Results.ErrorMessage = JobStatus['ErrorMessage']
            Results.ProcessId = JobStatus['ProcessId']
            
            Errors = [JobStatus['ErrorMessage']] if JobStatus['ErrorMessage'] else []
            
            # Sync instance state with database state
            self.IsScanning = IsScanning
            self.ScanProgress = JobStatus['Progress'] or 0.0
            self.CurrentScanDirectory = JobStatus['CurrentDirectory'] or ''
            
            return {
                'Success': True,
                'IsScanning': IsScanning,
                'Progress': JobStatus['Progress'] or 0.0,
                'CurrentDirectory': JobStatus['CurrentDirectory'] or '',
                'RootFolderPath': JobStatus['RootFolderPath'] or '',
                'Results': Results,
                'Errors': Errors,
                'Status': JobStatus['Status'],
                'JobId': JobStatus['JobId'],
                'ProcessId': JobStatus['ProcessId']
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
                'Errors': [str(e)]
            }
    
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
            Query = "UPDATE ScanJobs SET Status = 'Stopped', EndTime = ?, LastUpdated = ? WHERE JobId = ?"
            Now = datetime.now()
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (Now, Now, self.CurrentJobId))
            
            # Terminate the subprocess if it's still running
            if self.ScanProcess and self.ScanProcess.poll() is None:
                try:
                    self.ScanProcess.terminate()
                    # Wait a bit for graceful termination
                    try:
                        self.ScanProcess.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        self.ScanProcess.kill()
                        self.ScanProcess.wait()
                    
                    LoggingService.LogInfo(f"Terminated scan process {self.ScanProcess.pid}")
                except Exception as e:
                    LoggingService.LogException("Error terminating scan process", e)
            
            # Clear current job and update scanning state
            self.CurrentJobId = None
            self.ScanProcess = None
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
            LoggingService.LogInfo("Calculating directory size...")
            self.ScanProgress = 10.0
            TotalSizeGB = self.FileManager.CalculateDirectorySize(RootFolderPath)
            
            # Step 2: Get or create root folder record
            LoggingService.LogInfo("Managing root folder record...")
            self.ScanProgress = 20.0
            RootFolder = self.GetOrCreateRootFolder(RootFolderPath, TotalSizeGB)
            
            # Step 3: Scan for media files
            LoggingService.LogInfo("Scanning for media files...")
            self.ScanProgress = 30.0
            MediaFiles = self.FileManager.ScanDirectory(RootFolderPath, Recursive)
            self.ScanResults.TotalFilesFound = len(MediaFiles)
            self.ScanResults.RootFolderId = RootFolder.Id
            
            # Step 4: Process each media file with metadata extraction
            LoggingService.LogInfo("Processing {} media files with metadata extraction...", len(MediaFiles))
            self.ProcessMediaFiles(MediaFiles, RootFolder.Id, RootFolderPath, ExtractMetadata=True)
            
            # Step 5: Update scan results
            self.ScanProgress = 90.0
            self.UpdateScanResults()
            
            # Step 6: Complete scan
            self.ScanProgress = 100.0
            self.IsScanning = False
            
            LoggingService.LogInfo("Scan completed successfully")
            
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
    
    def GetOrCreateSeason(self, SeasonName: str, RootFolderId: int) -> SeasonModel:
        """Get existing season or create a new one with enhanced organization logic."""
        try:
            # Check if season already exists
            ExistingSeasons = self.DatabaseManager.GetAllSeasons()
            for Season in ExistingSeasons:
                if Season.SeasonName == SeasonName and Season.RootFolderId == RootFolderId:
                    return Season
            
            # Extract season number from name if possible
            SeasonNumber = self.ExtractSeasonNumber(SeasonName)
            
            # Create new season
            NewSeason = SeasonModel(
                RootFolderId=RootFolderId,
                SeasonName=SeasonName,
                SeasonNumber=SeasonNumber,
                EpisodeCount=0,
                TotalSizeGB=0.0
            )
            self.DatabaseManager.SaveSeason(NewSeason)
            LoggingService.LogInfo("Created new season: {} (Number: {})", SeasonName, SeasonNumber)
            return NewSeason
            
        except Exception as e:
            LoggingService.LogException("Error getting or creating season", e, 'FileScanningBusinessService', 'GetOrCreateSeason')
            raise
    
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
            LoggingService.LogException("Error processing media files", e, 'FileScanningBusinessService', 'ProcessMediaFiles')
            raise
    
    def ExtractSeasonFromPath(self, FilePath: str, RootFolderPath: str) -> str:
        """Extract season information from file path."""
        try:
            # Get relative path from root folder
            RelativePath = os.path.relpath(FilePath, RootFolderPath)
            PathParts = RelativePath.split(os.sep)
            
            # Look for season indicators in path
            for Part in PathParts:
                PartLower = Part.lower()
                if 'season' in PartLower or 's' in PartLower:
                    # Extract season number or name
                    if 'season' in PartLower:
                        # Format: "Season 1", "Season1", etc.
                        SeasonPart = Part
                    elif PartLower.startswith('s') and len(Part) > 1:
                        # Format: "S01", "S1", etc.
                        SeasonPart = f"Season {Part[1:]}"
                    else:
                        SeasonPart = Part
                    return SeasonPart
            
            # If no season found, use the first directory after root
            if len(PathParts) > 1:
                return PathParts[0]  # Use first subdirectory as season
            
            return "Default Season"
            
        except Exception as e:
            LoggingService.LogException("Error extracting season from path", e)
            return "Default Season"
    
    
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
                        LoggingService.LogInfo("Found fuzzy match (old file missing): {} -> {}", DbFile.FilePath, FilePath)
                        return DbFile
                    else:
                        LoggingService.LogInfo("Found fuzzy match but both files exist - creating new record: {} and {}", DbFile.FilePath, FilePath)
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
            
            # Extract season information and get/create season
            SeasonName = self.ExtractSeasonFromPath(FilePath, RootFolderPath)
            Season = self.GetOrCreateSeason(SeasonName, RootFolderId)
            
            # Check if this file already exists in database (exact match)
            ExistingFile = self.DatabaseManager.GetMediaFileByPath(FilePath)
            if ExistingFile:
                # File exists in database and on disk - update if needed
                ExistingFile.SizeMB = FileSizeMB
                ExistingFile.FileName = FileName
                ExistingFile.SeasonId = Season.Id
                ExistingFile.LastScannedDate = datetime.now()
                
                # Extract metadata if requested and not already present
                if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                    self.ExtractAndUpdateMetadata(ExistingFile, FilePath)
                
                self.DatabaseManager.SaveMediaFile(ExistingFile)
                self.ScanResults.TotalFilesProcessed += 1
                LoggingService.LogInfo("Updated existing file: {}", FilePath)
                
            else:
                # File doesn't exist in database - check for fuzzy match (renamed file)
                FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)
                
                if FuzzyMatch:
                    # Found a fuzzy match - this is likely a renamed file
                    LoggingService.LogInfo("Found renamed file: {} -> {}", FuzzyMatch.FilePath, FilePath)
                    FuzzyMatch.FilePath = FilePath  # Update to new path
                    FuzzyMatch.FileName = FileName  # Update to new filename
                    FuzzyMatch.SizeMB = FileSizeMB  # Update to new size
                    FuzzyMatch.SeasonId = Season.Id  # Update season if needed
                    FuzzyMatch.LastScannedDate = datetime.now()
                    
                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(FuzzyMatch):
                        self.ExtractAndUpdateMetadata(FuzzyMatch, FilePath)
                    
                    self.DatabaseManager.SaveMediaFile(FuzzyMatch)
                    self.ScanResults.TotalFilesProcessed += 1
                    LoggingService.LogInfo("Updated fuzzy match: {} -> {}", FuzzyMatch.FilePath, FilePath)
                else:
                    # Create new file record
                    NewFile = MediaFileModel(
                        SeasonId=Season.Id,
                        FilePath=FilePath,
                        FileName=FileName,
                        SizeMB=FileSizeMB,
                        LastScannedDate=datetime.now()
                    )
                    
                    # Extract metadata if requested
                    if ExtractMetadata:
                        self.ExtractAndUpdateMetadata(NewFile, FilePath)
                    
                    self.DatabaseManager.SaveMediaFile(NewFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    LoggingService.LogInfo("Added new media file: {} to season: {}", FilePath, SeasonName)
            
        except Exception as e:
            LoggingService.LogException("Error processing single media file", e)
            self.ScanResults.TotalFilesSkipped += 1
            raise
    
    def CleanupMissingFiles(self, FoundFiles: List[str], RootFolderId: int):
        """Remove database records for files that no longer exist on disk."""
        try:
            LoggingService.LogInfo("=== CLEANUP MISSING FILES STARTED ===")
            LoggingService.LogInfo(f"RootFolderId: {RootFolderId}")
            LoggingService.LogInfo(f"FoundFiles count: {len(FoundFiles)}")
            
            # Get ALL files from database, not just current root folder
            LoggingService.LogInfo("Querying database for ALL files in MediaFiles table")
            Query = "SELECT Id, FilePath, SizeMB FROM MediaFiles"
            DatabaseFiles = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            LoggingService.LogInfo(f"Database returned {len(DatabaseFiles)} files for cleanup check")
            
            if len(DatabaseFiles) == 0:
                LoggingService.LogWarning("No files found in database")
                return
            
            # Check each database file to see if it actually exists on disk
            DeletedCount = 0
            for i, DbFile in enumerate(DatabaseFiles):
                FilePath = DbFile['FilePath']
                FileId = DbFile['Id']
                SizeMB = DbFile['SizeMB']
                
                # Only log progress every 100 files to reduce verbosity
                if i % 100 == 0:
                    LoggingService.LogInfo(f"Cleanup progress: {i+1}/{len(DatabaseFiles)} files checked")
                
                if not os.path.exists(FilePath):
                    LoggingService.LogInfo(f"FILE NOT FOUND ON DISK - DELETING FROM DATABASE: {FilePath}")
                    try:
                        # Delete directly using the database service
                        DeleteQuery = "DELETE FROM MediaFiles WHERE Id = ?"
                        AffectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(DeleteQuery, (FileId,))
                        
                        if AffectedRows > 0:
                            LoggingService.LogInfo(f"SUCCESS: Deleted missing file from database: {FilePath} (ID: {FileId})")
                            DeletedCount += 1
                            self.ScanResults.TotalFilesWithErrors += 1
                        else:
                            LoggingService.LogError(f"FAILED: No rows affected when deleting file: {FilePath} (ID: {FileId})")
                    except Exception as DeleteError:
                        LoggingService.LogException(f"EXCEPTION: Error deleting file from database: {DeleteError}", DeleteError, 'FileScanningBusinessService', 'CleanupMissingFiles')
            
            LoggingService.LogInfo("=== CLEANUP MISSING FILES COMPLETED ===")
            if DeletedCount > 0:
                LoggingService.LogInfo(f"SUCCESS: Cleaned up {DeletedCount} missing files from database")
            else:
                LoggingService.LogInfo("No missing files found to clean up")
                        
        except Exception as e:
            LoggingService.LogException(f"CRITICAL ERROR in CleanupMissingFiles: {e}", e, 'FileScanningBusinessService', 'CleanupMissingFiles')
            LoggingService.LogException(f"RootFolderId: {RootFolderId}, FoundFiles count: {len(FoundFiles)}", e, 'FileScanningBusinessService', 'CleanupMissingFiles')
    
    def CleanupOrphanedFiles(self, RootFolderId: int) -> Dict[str, Any]:
        """Remove files on disk that don't have corresponding database records."""
        try:
            LoggingService.LogInfo("Starting cleanup of orphaned files for root folder: {}", RootFolderId)
            
            # Get root folder path
            RootFolder = self.DatabaseManager.GetRootFolderById(RootFolderId)
            if not RootFolder:
                LoggingService.LogWarning("Root folder not found: {}", RootFolderId)
                return {'Success': False, 'Message': 'Root folder not found', 'DeletedCount': 0}
            
            # Get all files on disk
            FoundFiles = self.FileManager.ScanDirectory(RootFolder.Path, True)
            LoggingService.LogInfo("Found {} files on disk", len(FoundFiles))
            
            # Get all database file paths
            DatabaseFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderId)
            DatabasePaths = {DbFile.FilePath for DbFile in DatabaseFiles}
            LoggingService.LogInfo("Found {} files in database", len(DatabasePaths))
            
            # Find orphaned files (exist on disk but not in database)
            OrphanedFiles = []
            for FilePath in FoundFiles:
                if FilePath not in DatabasePaths:
                    OrphanedFiles.append(FilePath)
                    LoggingService.LogInfo("Found orphaned file: {}", FilePath)
            
            # Delete orphaned files from disk
            DeletedCount = 0
            for OrphanedFile in OrphanedFiles:
                try:
                    if os.path.exists(OrphanedFile):
                        os.remove(OrphanedFile)
                        LoggingService.LogInfo("Deleted orphaned file: {}", OrphanedFile)
                        DeletedCount += 1
                        self.ScanResults.TotalFilesWithErrors += 1
                    else:
                        LoggingService.LogWarning("Orphaned file no longer exists: {}", OrphanedFile)
                except Exception as DeleteError:
                    LoggingService.LogException("Failed to delete orphaned file: {}", DeleteError, OrphanedFile)
            
            if DeletedCount > 0:
                LoggingService.LogInfo("Cleaned up {} orphaned files from disk", DeletedCount)
            else:
                LoggingService.LogInfo("No orphaned files found to clean up")
            
            return {
                'Success': True,
                'Message': f'Cleaned up {DeletedCount} orphaned files',
                'DeletedCount': DeletedCount
            }
                
        except Exception as e:
            LoggingService.LogException("Error cleaning up orphaned files", e)
            return {'Success': False, 'Message': f'Error: {str(e)}', 'DeletedCount': 0}
    
    def FindDuplicateMediaFiles(self, RootFolderId: int) -> List[Dict[str, Any]]:
        """Find duplicate media files on disk based on file size and content."""
        try:
            LoggingService.LogInfo("Starting duplicate media file detection for root folder: {}", RootFolderId)
            
            # Get root folder path
            RootFolder = self.DatabaseManager.GetRootFolderById(RootFolderId)
            if not RootFolder:
                LoggingService.LogWarning("Root folder not found: {}", RootFolderId)
                return []
            
            # Get all files on disk
            FoundFiles = self.FileManager.ScanDirectory(RootFolder.Path, True)
            LoggingService.LogInfo("Scanning {} files for duplicates", len(FoundFiles))
            
            # Group files by size (first pass - files with same size are potential duplicates)
            SizeGroups = {}
            for FilePath in FoundFiles:
                try:
                    FileSize = os.path.getsize(FilePath)
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
                for FileToDelete in FilesToDelete:
                    try:
                        if os.path.exists(FileToDelete):
                            os.remove(FileToDelete)
                            LoggingService.LogInfo("Deleted duplicate file: {}", FileToDelete)
                            DeletedCount += 1
                            self.ScanResults.TotalFilesWithErrors += 1
                            
                            # Also remove from database if it exists
                            self.DatabaseManager.DeleteMediaFileByPath(FileToDelete)
                        else:
                            LoggingService.LogWarning("Duplicate file no longer exists: {}", FileToDelete)
                    except Exception as DeleteError:
                        LoggingService.LogException("Failed to delete duplicate file: {}", DeleteError, FileToDelete)
                
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
                FileName = os.path.basename(FilePath).lower()
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
            
            LoggingService.LogInfo("Scan results updated: TotalFiles={}, Processed={}, Skipped={}, Errors={}", 
                                 self.ScanResults.TotalFilesFound, 
                                 self.ScanResults.TotalFilesProcessed,
                                 self.ScanResults.TotalFilesSkipped,
                                 self.ScanResults.TotalFilesWithErrors)
            
        except Exception as e:
            LoggingService.LogException("Error updating scan results", e)
    
    
    def GetScanStatus(self) -> Dict[str, Any]:
        """Get current scan status and progress."""
        return self.GetCurrentScanStatus()
    
    def GetRootFolders(self) -> List[RootFolderModel]:
        """Get all root folders."""
        try:
            return self.DatabaseManager.GetAllRootFolders()
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
    
    def ResetScanState(self):
        """Reset the scan state to allow new scans."""
        # Clear current job reference
        self.CurrentJobId = None
        self.ScanProcess = None
        # Clean up old completed jobs
        self.CleanupCompletedJobs()
    
    def ShouldExtractMetadata(self, MediaFile: MediaFileModel) -> bool:
        """Determine if metadata should be extracted for a media file based on change detection."""
        try:
            # Don't extract if media analysis is not available
            if not self.FileManager.IsMediaAnalysisAvailable():
                return False
            
            # Always extract for new files (no metadata at all)
            if (MediaFile.VideoBitrateKbps is None and 
                MediaFile.AudioBitrateKbps is None and 
                MediaFile.Resolution is None and 
                MediaFile.Codec is None and 
                MediaFile.DurationMinutes is None and 
                MediaFile.FrameRate is None):
                return True
            
            # Check if file has changed (size or name)
            if self.HasFileChanged(MediaFile):
                return True
            
            # File hasn't changed and has metadata, skip extraction
            return False
            
        except Exception as e:
            LoggingService.LogException("Error determining if metadata should be extracted", e, 'FileScanningBusinessService', 'ShouldExtractMetadata')
            return False
    
    def HasFileChanged(self, MediaFile: MediaFileModel) -> bool:
        """Check if a file has changed by comparing size and name with current file."""
        try:
            # Get current file information
            CurrentSizeMB = self.FileManager.GetFileSizeMB(MediaFile.FilePath)
            CurrentFileName = self.FileManager.GetFileNameFromPath(MediaFile.FilePath)
            
            # Compare with stored values
            SizeChanged = abs(CurrentSizeMB - MediaFile.SizeMB) > 0.1  # Allow small floating point differences
            NameChanged = CurrentFileName != MediaFile.FileName
            
            if SizeChanged or NameChanged:
                LoggingService.LogDebug(f"File changed detected for {MediaFile.FilePath}: Size={SizeChanged}, Name={NameChanged}", 'FileScanningBusinessService', 'HasFileChanged')
                return True
            
            return False
            
        except Exception as e:
            LoggingService.LogException("Error checking if file has changed", e, 'FileScanningBusinessService', 'HasFileChanged')
            # If we can't check, assume it changed to be safe
            return True
    
    def ExtractAndUpdateMetadata(self, MediaFile: MediaFileModel, FilePath: str):
        """Extract metadata and update the media file model."""
        try:
            LoggingService.LogDebug(f"Extracting metadata for: {FilePath}", 'FileScanningBusinessService', 'ExtractAndUpdateMetadata')
            
            # Update file size and name to current values (in case file changed)
            MediaFile.SizeMB = self.FileManager.GetFileSizeMB(FilePath)
            MediaFile.FileName = self.FileManager.GetFileNameFromPath(FilePath)
            
            # Extract metadata using FileManagerService
            MetadataResult = self.FileManager.ExtractMediaMetadata(FilePath)
            
            # Log what metadata we extracted
            LoggingService.LogInfo(f"Extracted metadata for {FilePath}: VideoBitrate={MetadataResult.get('VideoBitrateKbps')}, AudioBitrate={MetadataResult.get('AudioBitrateKbps')}, Codec={MetadataResult.get('VideoCodec')}", 'FileScanningBusinessService', 'ExtractAndUpdateMetadata')
            
            if MetadataResult.get('Success', False):
                # Update the media file with extracted metadata
                MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
                MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
                MediaFile.Resolution = MetadataResult.get('Resolution')
                MediaFile.Codec = MetadataResult.get('VideoCodec')
                MediaFile.DurationMinutes = MetadataResult.get('DurationMinutes')
                MediaFile.FrameRate = MetadataResult.get('FrameRate')
                MediaFile.CompressionPotential = MetadataResult.get('CompressionPotential')
                MediaFile.AssignedProfile = MetadataResult.get('AssignedProfile')
                
                
                LoggingService.LogDebug(f"Successfully extracted metadata for: {FilePath}", 'FileScanningBusinessService', 'ExtractAndUpdateMetadata')
            else:
                # Set default values for failed extraction
                MediaFile.CompressionPotential = 'Unknown'
                MediaFile.AssignedProfile = 'Default'
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"Failed to extract metadata for {FilePath}: {ErrorMessage}", 'FileScanningBusinessService', 'ExtractAndUpdateMetadata')
            
        except Exception as e:
            LoggingService.LogException("Error extracting and updating metadata", e, 'FileScanningBusinessService', 'ExtractAndUpdateMetadata')
            # Set default values on error
            MediaFile.CompressionPotential = 'Unknown'
            MediaFile.AssignedProfile = 'Default'
    
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
                    LoggingService.LogException("Error processing media file with metadata", e, 'FileScanningBusinessService', 'ProcessMediaFilesWithMetadata')
                    self.ScanErrors.append(f"Error processing {FilePath}: {str(e)}")
                    continue
            
            # Find and report duplicate files after processing
            if RootFolderId:
                DuplicateGroups = self.FindDuplicateMediaFiles(RootFolderId)
                if DuplicateGroups:
                    LoggingService.LogInfo(f"Found {len(DuplicateGroups)} duplicate file groups during scan")
                    for Group in DuplicateGroups:
                        LoggingService.LogInfo(f"Duplicate group: {Group['Count']} files with size {Group['Size']} bytes")
                        for FilePath in Group['Files']:
                            LoggingService.LogInfo(f"  - {FilePath}")
            
            LoggingService.LogInfo(f"Completed processing {len(MediaFiles)} media files with metadata extraction: {ExtractMetadata}", 'FileScanningBusinessService', 'ProcessMediaFilesWithMetadata')
            
        except Exception as e:
            LoggingService.LogException("Error processing media files with metadata", e, 'FileScanningBusinessService', 'ProcessMediaFilesWithMetadata')
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
            if RootFolderId:
                FilesNeedingMetadata = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderId)
            else:
                FilesNeedingMetadata = self.DatabaseManager.GetAllMediaFiles()
            
            # Filter files that need metadata
            FilesToProcess = []
            for File in FilesNeedingMetadata:
                if self.ShouldExtractMetadata(File):
                    FilesToProcess.append(File)
            
            if not FilesToProcess:
                return {
                    'Success': True,
                    'Message': 'No files need metadata extraction',
                    'ProcessedFiles': 0
                }
            
            LoggingService.LogInfo(f"Found {len(FilesToProcess)} files that need metadata extraction", 'FileScanningBusinessService', 'ExtractMetadataForExistingFiles')
            
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
                        
                        LoggingService.LogDebug(f"Extracted metadata for: {File.FilePath}", 'FileScanningBusinessService', 'ExtractMetadataForExistingFiles')
                        
                    except Exception as e:
                        LoggingService.LogException(f"Error extracting metadata for: {File.FilePath}", e, 'FileScanningBusinessService', 'ExtractMetadataForExistingFiles')
                        continue
            
            LoggingService.LogInfo(f"Completed metadata extraction for {ProcessedCount} files", 'FileScanningBusinessService', 'ExtractMetadataForExistingFiles')
            
            return {
                'Success': True,
                'Message': f'Successfully extracted metadata for {ProcessedCount} files',
                'ProcessedFiles': ProcessedCount
            }
            
        except Exception as e:
            LoggingService.LogException("Error extracting metadata for existing files", e, 'FileScanningBusinessService', 'ExtractMetadataForExistingFiles')
            return {
                'Success': False,
                'Message': f'Error extracting metadata: {str(e)}',
                'Error': 'MetadataExtractionError'
            }
    
    def ExtractSeasonNumber(self, SeasonName: str) -> Optional[int]:
        """Extract season number from season name."""
        try:
            import re
            
            # Try various patterns to extract season number
            Patterns = [
                r'season\s*(\d+)',  # "Season 1", "season1"
                r's(\d+)',          # "S1", "S01"
                r'(\d+)',           # Just a number
                r'season\s*(\d+)\s*episode',  # "Season 1 Episode"
                r's(\d+)e\d+',      # "S1E1"
            ]
            
            SeasonNameLower = SeasonName.lower()
            
            for Pattern in Patterns:
                Match = re.search(Pattern, SeasonNameLower)
                if Match:
                    try:
                        SeasonNumber = int(Match.group(1))
                        return SeasonNumber
                    except (ValueError, IndexError):
                        continue
            
            # If no pattern matches, return None
            return None
            
        except Exception as e:
            LoggingService.LogException("Error extracting season number", e, 'FileScanningBusinessService', 'ExtractSeasonNumber')
            return None
    
    def UpdateSeasonStatistics(self, SeasonId: int):
        """Update season statistics (episode count, total size)."""
        try:
            LoggingService.LogFunctionEntry("UpdateSeasonStatistics", 'FileScanningBusinessService', f"SeasonId: {SeasonId}")
            
            # Get all media files for this season
            SeasonFiles = self.DatabaseManager.GetMediaFilesBySeason(SeasonId)
            
            if not SeasonFiles:
                LoggingService.LogWarning(f"No files found for season {SeasonId}", 'FileScanningBusinessService', 'UpdateSeasonStatistics')
                return
            
            # Calculate statistics
            EpisodeCount = len(SeasonFiles)
            TotalSizeGB = sum(File.SizeMB for File in SeasonFiles) / 1024.0  # Convert MB to GB
            
            # Get the season record
            Season = self.DatabaseManager.GetSeasonById(SeasonId)
            if not Season:
                LoggingService.LogWarning(f"Season {SeasonId} not found", 'FileScanningBusinessService', 'UpdateSeasonStatistics')
                return
            
            # Update season statistics
            Season.EpisodeCount = EpisodeCount
            Season.TotalSizeGB = TotalSizeGB
            Season.LastUpdatedDate = datetime.now()
            
            # Save updated season
            self.DatabaseManager.SaveSeason(Season)
            
            LoggingService.LogInfo(f"Updated season {Season.SeasonName}: {EpisodeCount} episodes, {TotalSizeGB:.2f} GB", 'FileScanningBusinessService', 'UpdateSeasonStatistics')
            
        except Exception as e:
            LoggingService.LogException("Error updating season statistics", e, 'FileScanningBusinessService', 'UpdateSeasonStatistics')
    
    def OrganizeFilesBySeason(self, RootFolderId: int) -> Dict[str, Any]:
        """Organize files by season and update season statistics."""
        try:
            LoggingService.LogFunctionEntry("OrganizeFilesBySeason", 'FileScanningBusinessService', f"RootFolderId: {RootFolderId}")
            
            # Get all media files for this root folder
            MediaFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderId)
            
            if not MediaFiles:
                return {
                    'Success': True,
                    'Message': 'No media files found to organize',
                    'SeasonsUpdated': 0
                }
            
            # Group files by season
            SeasonGroups = {}
            for File in MediaFiles:
                SeasonId = File.SeasonId
                if SeasonId not in SeasonGroups:
                    SeasonGroups[SeasonId] = []
                SeasonGroups[SeasonId].append(File)
            
            # Update statistics for each season
            SeasonsUpdated = 0
            for SeasonId, Files in SeasonGroups.items():
                try:
                    self.UpdateSeasonStatistics(SeasonId)
                    SeasonsUpdated += 1
                except Exception as e:
                    LoggingService.LogException(f"Error updating season {SeasonId} statistics", e, 'FileScanningBusinessService', 'OrganizeFilesBySeason')
                    continue
            
            LoggingService.LogInfo(f"Organized {len(MediaFiles)} files into {len(SeasonGroups)} seasons", 'FileScanningBusinessService', 'OrganizeFilesBySeason')
            
            return {
                'Success': True,
                'Message': f'Successfully organized {len(MediaFiles)} files into {len(SeasonGroups)} seasons',
                'SeasonsUpdated': SeasonsUpdated,
                'TotalFiles': len(MediaFiles),
                'TotalSeasons': len(SeasonGroups)
            }
            
        except Exception as e:
            LoggingService.LogException("Error organizing files by season", e, 'FileScanningBusinessService', 'OrganizeFilesBySeason')
            return {
                'Success': False,
                'Message': f'Error organizing files by season: {str(e)}',
                'Error': 'SeasonOrganizationError'
            }
    
    def GetSeasonSummary(self, RootFolderId: int) -> List[Dict[str, Any]]:
        """Get summary of all seasons for a root folder."""
        try:
            LoggingService.LogFunctionEntry("GetSeasonSummary", 'FileScanningBusinessService', f"RootFolderId: {RootFolderId}")
            
            # Get all seasons for this root folder
            Seasons = self.DatabaseManager.GetSeasonsByRootFolder(RootFolderId)
            
            SeasonSummary = []
            for Season in Seasons:
                # Get media files for this season
                SeasonFiles = self.DatabaseManager.GetMediaFilesBySeason(Season.Id)
                
                Summary = {
                    'SeasonId': Season.Id,
                    'SeasonName': Season.SeasonName,
                    'SeasonNumber': Season.SeasonNumber,
                    'EpisodeCount': len(SeasonFiles),
                    'TotalSizeGB': sum(File.SizeMB for File in SeasonFiles) / 1024.0,
                    'CreatedDate': Season.CreatedDate,
                    'LastUpdatedDate': Season.LastUpdatedDate,
                    'Files': [
                        {
                            'Id': File.Id,
                            'FileName': File.FileName,
                            'SizeMB': File.SizeMB,
                            'Resolution': File.Resolution,
                            'Codec': File.Codec,
                            'DurationMinutes': File.DurationMinutes
                        }
                        for File in SeasonFiles
                    ]
                }
                SeasonSummary.append(Summary)
            
            # Sort by season number
            SeasonSummary.sort(key=lambda x: x['SeasonNumber'] or 0)
            
            LoggingService.LogInfo(f"Generated season summary for {len(SeasonSummary)} seasons", 'FileScanningBusinessService', 'GetSeasonSummary')
            return SeasonSummary
            
        except Exception as e:
            LoggingService.LogException("Error getting season summary", e, 'FileScanningBusinessService', 'GetSeasonSummary')
            return []
    
    def MergeSeasons(self, SourceSeasonId: int, TargetSeasonId: int) -> Dict[str, Any]:
        """Merge files from source season into target season."""
        try:
            LoggingService.LogFunctionEntry("MergeSeasons", 'FileScanningBusinessService', f"SourceSeasonId: {SourceSeasonId}, TargetSeasonId: {TargetSeasonId}")
            
            # Get both seasons
            SourceSeason = self.DatabaseManager.GetSeasonById(SourceSeasonId)
            TargetSeason = self.DatabaseManager.GetSeasonById(TargetSeasonId)
            
            if not SourceSeason or not TargetSeason:
                return {
                    'Success': False,
                    'Message': 'One or both seasons not found',
                    'Error': 'SeasonNotFound'
                }
            
            # Get files from source season
            SourceFiles = self.DatabaseManager.GetMediaFilesBySeason(SourceSeasonId)
            
            if not SourceFiles:
                return {
                    'Success': True,
                    'Message': 'No files to merge',
                    'FilesMerged': 0
                }
            
            # Move files to target season
            FilesMerged = 0
            for File in SourceFiles:
                try:
                    File.SeasonId = TargetSeasonId
                    self.DatabaseManager.SaveMediaFile(File)
                    FilesMerged += 1
                except Exception as e:
                    LoggingService.LogException(f"Error moving file {File.FileName} to target season", e, 'FileScanningBusinessService', 'MergeSeasons')
                    continue
            
            # Update target season statistics
            self.UpdateSeasonStatistics(TargetSeasonId)
            
            # Delete source season if it's now empty
            RemainingFiles = self.DatabaseManager.GetMediaFilesBySeason(SourceSeasonId)
            if not RemainingFiles:
                self.DatabaseManager.DeleteSeason(SourceSeasonId)
                LoggingService.LogInfo(f"Deleted empty source season: {SourceSeason.SeasonName}", 'FileScanningBusinessService', 'MergeSeasons')
            
            LoggingService.LogInfo(f"Merged {FilesMerged} files from {SourceSeason.SeasonName} to {TargetSeason.SeasonName}", 'FileScanningBusinessService', 'MergeSeasons')
            
            return {
                'Success': True,
                'Message': f'Successfully merged {FilesMerged} files from {SourceSeason.SeasonName} to {TargetSeason.SeasonName}',
                'FilesMerged': FilesMerged
            }
            
        except Exception as e:
            LoggingService.LogException("Error merging seasons", e, 'FileScanningBusinessService', 'MergeSeasons')
            return {
                'Success': False,
                'Message': f'Error merging seasons: {str(e)}',
                'Error': 'SeasonMergeError'
            }
