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
            
            # Start subprocess
            ProcessArgs = [
                'py', str(self.ScriptPath), JobId, RootFolderPath, str(Recursive)
            ]
            
            LoggingService.LogInfo(f"Starting subprocess with args: {ProcessArgs}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Script path: {self.ScriptPath}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Script exists: {self.ScriptPath.exists()}", 'FileScanningBusinessService', 'StartScanning')
            LoggingService.LogInfo(f"Working directory: {Path(__file__).parent.parent}", 'FileScanningBusinessService', 'StartScanning')
            
            try:
                self.ScanProcess = subprocess.Popen(
                    ProcessArgs,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=Path(__file__).parent.parent
                )
                
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
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated)
            VALUES (?, ?, ?, 'Pending', ?, ?)
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
            
            # Clear current job
            self.CurrentJobId = None
            self.ScanProcess = None
            
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
            
            # Step 4: Process each media file
            LoggingService.LogInfo("Processing {} media files...", len(MediaFiles))
            self.ProcessMediaFiles(MediaFiles, RootFolder.Id, RootFolderPath)
            
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
        """Get existing season or create a new one."""
        try:
            # Check if season already exists
            ExistingSeasons = self.DatabaseManager.GetAllSeasons()
            for Season in ExistingSeasons:
                if Season.SeasonName == SeasonName and Season.RootFolderId == RootFolderId:
                    return Season
            
            # Create new season
            NewSeason = SeasonModel(
                RootFolderId=RootFolderId,
                SeasonName=SeasonName,
                SeasonNumber=1,  # Default to 1, could be extracted from name later
                EpisodeCount=0,
                TotalSizeGB=0.0
            )
            self.DatabaseManager.SaveSeason(NewSeason)
            LoggingService.LogInfo("Created new season: {}", SeasonName)
            return NewSeason
            
        except Exception as e:
            LoggingService.LogException("Error getting or creating season", e)
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
    
    def ProcessMediaFiles(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = ""):
        """Process each media file found during scanning."""
        try:
            TotalFiles = len(MediaFiles)
            
            for i, FilePath in enumerate(MediaFiles):
                try:
                    # Update progress
                    Progress = 30.0 + (60.0 * (i + 1) / TotalFiles)
                    self.ScanProgress = Progress
                    
                    # Process the file
                    self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath)
                    
                except Exception as e:
                    LoggingService.LogException("Error processing media file", e)
                    self.ScanErrors.append(f"Error processing {FilePath}: {str(e)}")
                    continue
            
            # Clean up missing files after processing all found files
            if RootFolderId:
                self.CleanupMissingFiles(MediaFiles, RootFolderId)
            
        except Exception as e:
            LoggingService.LogException("Error processing media files", e)
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
    
    def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = ""):
        """Process a single media file with fuzzy matching."""
        try:
            # Get file information
            FileSizeMB = self.FileManager.GetFileSizeMB(FilePath)
            FileName = self.FileManager.GetFileNameFromPath(FilePath)
            
            # Extract season information and get/create season
            SeasonName = self.ExtractSeasonFromPath(FilePath, RootFolderPath)
            Season = self.GetOrCreateSeason(SeasonName, RootFolderId)
            
            # Try fuzzy match first
            FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)
            
            if FuzzyMatch:
                # Update the fuzzy match
                FuzzyMatch.FilePath = FilePath  # Update to new path
                FuzzyMatch.FileName = FileName  # Update to new filename
                FuzzyMatch.SizeMB = FileSizeMB  # Update to new size
                FuzzyMatch.SeasonId = Season.Id  # Update season if needed
                FuzzyMatch.LastScannedDate = datetime.now()
                
                self.DatabaseManager.SaveMediaFile(FuzzyMatch)
                self.ScanResults.TotalFilesProcessed += 1
                LoggingService.LogInfo("Updated fuzzy match: {} -> {}", FuzzyMatch.FilePath, FilePath)
                
            else:
                # Check for exact path match
                ExistingFile = self.DatabaseManager.GetMediaFileByPath(FilePath)
                
                if ExistingFile:
                    # Update existing exact match
                    ExistingFile.SizeMB = FileSizeMB
                    ExistingFile.SeasonId = Season.Id
                    ExistingFile.LastScannedDate = datetime.now()
                    self.DatabaseManager.SaveMediaFile(ExistingFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    LoggingService.LogInfo("Updated existing media file: {}", FilePath)
                else:
                    # Create new file record
                    NewFile = MediaFileModel(
                        SeasonId=Season.Id,
                        FilePath=FilePath,
                        FileName=FileName,
                        SizeMB=FileSizeMB,
                        LastScannedDate=datetime.now()
                    )
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
            LoggingService.LogInfo("Starting cleanup of missing files for root folder: {}", RootFolderId)
            
            # Get all files in database for this root folder
            DatabaseFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderId)
            
            # Create set of found file paths for efficient lookup
            FoundFilePaths = set(FoundFiles)
            
            # Find files that are in database but not found on disk
            MissingFiles = []
            for DbFile in DatabaseFiles:
                if DbFile.FilePath not in FoundFilePaths:
                    MissingFiles.append(DbFile)
            
            # Remove missing files from database
            for MissingFile in MissingFiles:
                self.DatabaseManager.DeleteMediaFileByPath(MissingFile.FilePath)
                LoggingService.LogInfo("Removed missing file from database: {}", MissingFile.FilePath)
                self.ScanResults.TotalFilesWithErrors += 1  # Track as "error" for reporting
            
            if MissingFiles:
                LoggingService.LogInfo("Cleaned up {} missing files from database", len(MissingFiles))
            else:
                LoggingService.LogInfo("No missing files found to clean up")
                
        except Exception as e:
            LoggingService.LogException("Error cleaning up missing files", e)
    
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
    
    def StopScanning(self) -> Dict[str, Any]:
        """Stop the current scanning process."""
        try:
            if not self.IsScanning:
                return {
                    'Success': False,
                    'Message': 'No scan is currently in progress',
                    'Error': 'NoScanInProgress'
                }
            
            self.IsScanning = False
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = ""
            
            LoggingService.LogInfo("Scan stopped by user request")
            
            return {
                'Success': True,
                'Message': 'Scan stopped successfully',
                'Results': self.ScanResults
            }
            
        except Exception as e:
            LoggingService.LogException("Error stopping scan", e)
            return {
                'Success': False,
                'Message': f'Error stopping scan: {str(e)}',
                'Error': 'StopError'
            }
    
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
