from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Services.FileScanningBusinessService import FileScanningBusinessService
from Services.LoggingService import LoggingService


class FileScanningViewModel:
    """Manages scanning UI state, progress tracking, and error handling with Unicode character support."""
    
    def __init__(self, BusinessService: FileScanningBusinessService = None):
        self.BusinessService = BusinessService or FileScanningBusinessService()
        self.IsScanning = False
        self.ScanProgress = 0.0
        self.CurrentScanDirectory = ""
        self.ScanResults = FileScanResultModel()
        self.ScanDirectories = []
        self.LoadScanDirectories()
        self.ScanErrors = []
        self.RootFolders = []
        self.MediaFiles = []
        self.SelectedRootFolder = None
        self.LastScanTime = None
        self.ScanStatusMessage = ""
        self.IsError = False
        self.ErrorMessage = ""
    
    def StartScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
        """Start scanning a root folder using subprocess and update UI state."""
        try:
            LoggingService.LogFunctionEntry("StartScanning", RootFolderPath, Recursive)
            
            # Start the scan using subprocess
            result = self.BusinessService.StartScanning(RootFolderPath, Recursive)
            
            if result['Success']:
                # Update UI state with subprocess info
                self.CurrentScanDirectory = RootFolderPath
                self.ScanStatusMessage = "Scan started successfully"
                self.IsError = False
                self.ErrorMessage = ""
                self.LastScanTime = datetime.now()
            else:
                self.IsError = True
                self.ErrorMessage = result.get('Message', 'Unknown error occurred')
                self.ScanStatusMessage = f"Scan failed: {self.ErrorMessage}"
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error in StartScanning", e, "StartScanning", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error starting scan: {str(e)}"
            self.ScanStatusMessage = self.ErrorMessage
            return {
                'Success': False,
                'Message': self.ErrorMessage,
                'Error': 'StartScanError'
            }
    
    def StopScanning(self) -> Dict[str, Any]:
        """Stop the current scan and update UI state."""
        try:
            result = self.BusinessService.StopScanning()
            
            if result['Success']:
                self.IsScanning = False
                self.ScanProgress = 0.0
                self.CurrentScanDirectory = ""
                self.ScanStatusMessage = "Scan stopped by user"
                self.IsError = False
                self.ErrorMessage = ""
            else:
                self.IsError = True
                self.ErrorMessage = result.get('Message', 'Unknown error occurred')
                self.ScanStatusMessage = f"Stop failed: {self.ErrorMessage}"
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error in StopScanning", e, "StopScanning", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error stopping scan: {str(e)}"
            self.ScanStatusMessage = self.ErrorMessage
            return {
                'Success': False,
                'Message': self.ErrorMessage,
                'Error': 'StopScanError'
            }
    
    def UpdateScanStatus(self) -> Dict[str, Any]:
        """Update the current scan status and progress from subprocess data."""
        try:
            # Remove verbose logging - only log errors
            status = self.BusinessService.GetScanStatus()
            
            # Update UI state from business service
            self.IsScanning = status['IsScanning']
            self.ScanProgress = status['Progress']
            self.CurrentScanDirectory = status['CurrentDirectory']
            # Update scan results from business service
            if 'Results' in status and status['Results']:
                self.ScanResults = status['Results']
            self.ScanErrors = status['Errors'].copy()
            
            # Update status message based on subprocess status
            if self.IsScanning:
                self.ScanStatusMessage = f"Scanning: {self.CurrentScanDirectory} ({self.ScanProgress:.1f}%)"
            else:
                if status.get('Status') == 'Completed':
                    self.ScanStatusMessage = f"Scan completed: {self.ScanResults.TotalFilesProcessed} files processed"
                elif status.get('Status') == 'Failed':
                    self.ScanStatusMessage = f"Scan failed: {status.get('ErrorMessage', 'Unknown error')}"
                elif status.get('Status') == 'Stopped':
                    self.ScanStatusMessage = "Scan stopped by user"
                else:
                    self.ScanStatusMessage = "Ready to scan"
            
            # Check for errors
            if self.ScanErrors:
                self.IsError = True
                self.ErrorMessage = f"Found {len(self.ScanErrors)} errors during scan"
            else:
                self.IsError = False
                self.ErrorMessage = ""
            
            return status
            
        except Exception as e:
            LoggingService.LogException("Error in UpdateScanStatus", e, "FileScanningViewModel", "UpdateScanStatus")
            self.IsError = True
            self.ErrorMessage = f"Error updating scan status: {str(e)}"
            self.ScanStatusMessage = self.ErrorMessage
            return {
                'Success': False,
                'Message': self.ErrorMessage,
                'Error': 'StatusUpdateError'
            }
    
    def LoadRootFolders(self, SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> List[RootFolderModel]:
        """Load all root folders and update UI state with optional sorting."""
        try:
            self.RootFolders = self.BusinessService.GetRootFolders(SortColumn, SortOrder)
            LoggingService.LogInfo("Loaded {} root folders", len(self.RootFolders))
            return self.RootFolders
            
        except Exception as e:
            LoggingService.LogException("Error loading root folders", e, "LoadRootFolders", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error loading root folders: {str(e)}"
            return []
    
    def LoadMediaFiles(self, RootFolderPath: Optional[str] = None) -> List[MediaFileModel]:
        """Load media files and update UI state."""
        try:
            self.MediaFiles = self.BusinessService.GetMediaFiles(RootFolderPath)
            self.SelectedRootFolder = RootFolderPath
            LoggingService.LogInfo("Loaded {} media files", len(self.MediaFiles))
            return self.MediaFiles
            
        except Exception as e:
            LoggingService.LogException("Error loading media files", e, "LoadMediaFiles", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error loading media files: {str(e)}"
            return []
    
    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        """Delete a root folder and update UI state."""
        try:
            success = self.BusinessService.DeleteRootFolder(RootFolderId)
            
            if success:
                # Remove from local list
                self.RootFolders = [rf for rf in self.RootFolders if rf.Id != RootFolderId]
                self.ScanStatusMessage = "Root folder deleted successfully"
                self.IsError = False
                self.ErrorMessage = ""
            else:
                self.IsError = True
                self.ErrorMessage = "Failed to delete root folder"
                self.ScanStatusMessage = self.ErrorMessage
            
            return success
            
        except Exception as e:
            LoggingService.LogException("Error deleting root folder", e, "DeleteRootFolder", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error deleting root folder: {str(e)}"
            self.ScanStatusMessage = self.ErrorMessage
            return False
    
    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete a media file and update UI state."""
        try:
            success = self.BusinessService.DeleteMediaFile(MediaFileId)
            
            if success:
                # Remove from local list
                self.MediaFiles = [mf for mf in self.MediaFiles if mf.Id != MediaFileId]
                self.ScanStatusMessage = "Media file deleted successfully"
                self.IsError = False
                self.ErrorMessage = ""
            else:
                self.IsError = True
                self.ErrorMessage = "Failed to delete media file"
                self.ScanStatusMessage = self.ErrorMessage
            
            return success
            
        except Exception as e:
            LoggingService.LogException("Error deleting media file", e, "DeleteMediaFile", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error deleting media file: {str(e)}"
            self.ScanStatusMessage = self.ErrorMessage
            return False
    
    def GetScanProgressPercentage(self) -> float:
        """Get scan progress as a percentage."""
        return self.ScanProgress
    
    def GetScanStatusText(self) -> str:
        """Get current scan status text for display."""
        return self.ScanStatusMessage
    
    def GetErrorText(self) -> str:
        """Get current error text for display."""
        return self.ErrorMessage
    
    def HasErrors(self) -> bool:
        """Check if there are any errors."""
        return self.IsError or len(self.ScanErrors) > 0
    
    def GetScanErrors(self) -> List[str]:
        """Get list of scan errors."""
        return self.ScanErrors.copy()
    
    def GetScanResults(self) -> FileScanResultModel:
        """Get current scan results."""
        return self.ScanResults
    
    def GetRootFoldersForDisplay(self) -> List[Dict[str, Any]]:
        """Get root folders formatted for display."""
        DisplayFolders = []
        for folder in self.RootFolders:
            DisplayFolders.append({
                'Id': folder.Id,
                'RootFolder': folder.RootFolder,
                'LastScannedDate': folder.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if folder.LastScannedDate and hasattr(folder.LastScannedDate, 'strftime') else str(folder.LastScannedDate) if folder.LastScannedDate else 'Never',
                'TotalSizeGB': f"{folder.TotalSizeGB:.2f} GB"
            })
        return DisplayFolders
    
    def GetRootFoldersPaginated(self, Page: int, PageSize: int, Search: str = '', SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> Dict[str, Any]:
        """Get root folders with pagination, filtering, and sorting."""
        try:
            # Load all root folders first with sorting
            self.LoadRootFolders(SortColumn, SortOrder)
            
            # Apply search filter
            FilteredFolders = self.RootFolders
            if Search:
                SearchLower = Search.lower()
                FilteredFolders = [folder for folder in self.RootFolders 
                                 if SearchLower in folder.RootFolder.lower()]
            
            # Calculate pagination
            TotalCount = len(FilteredFolders)
            TotalPages = (TotalCount + PageSize - 1) // PageSize
            
            # Get page slice
            StartIndex = (Page - 1) * PageSize
            EndIndex = StartIndex + PageSize
            PageFolders = FilteredFolders[StartIndex:EndIndex]
            
            # Format for display
            DisplayFolders = []
            for folder in PageFolders:
                DisplayFolders.append({
                    'Id': folder.Id,
                    'RootFolder': folder.RootFolder,
                    'LastScannedDate': folder.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if folder.LastScannedDate and hasattr(folder.LastScannedDate, 'strftime') else str(folder.LastScannedDate) if folder.LastScannedDate else 'Never',
                    'TotalSizeGB': f"{folder.TotalSizeGB:.2f} GB"
                })
            
            # Get all folders for filter dropdown
            AllDisplayFolders = self.GetRootFoldersForDisplay()
            
            return {
                'RootFolders': DisplayFolders,
                'TotalCount': TotalCount,
                'TotalPages': TotalPages,
                'AllRootFolders': AllDisplayFolders
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting paginated root folders", e, "GetRootFoldersPaginated", "FileScanningViewModel")
            return {
                'RootFolders': [],
                'TotalCount': 0,
                'TotalPages': 0,
                'AllRootFolders': []
            }
    
    def GetMediaFilesForDisplay(self) -> List[Dict[str, Any]]:
        """Get media files formatted for display."""
        DisplayFiles = []
        for file in self.MediaFiles:
            DisplayFiles.append({
                'Id': file.Id,
                'FileName': file.FileName,
                'FilePath': file.FilePath,
                'SizeMB': f"{file.SizeMB:.2f} MB",
                'LastScannedDate': file.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if file.LastScannedDate and hasattr(file.LastScannedDate, 'strftime') else str(file.LastScannedDate) if file.LastScannedDate else 'Unknown',
                'Codec': file.Codec or 'Unknown',
                'Resolution': file.Resolution or 'Unknown',
                'DurationMinutes': f"{file.DurationMinutes:.1f} min" if file.DurationMinutes else 'Unknown'
            })
        return DisplayFiles
    
    def GetMediaFilesPaginated(self, Page: int, PageSize: int, Search: str = '', RootFolderPath: str = '', SortBy: str = 'SizeMB', SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get media files with pagination and filtering."""
        try:
            # Get media files directly from business service
            MediaFiles = self.BusinessService.GetMediaFiles(RootFolderPath)
            
            # Apply search filter if provided
            if Search:
                SearchLower = Search.lower()
                
                # Check if it's a negative filter (starts with !)
                if SearchLower.startswith('!'):
                    # Negative filter - exclude files containing the term
                    ExcludeTerm = SearchLower[1:]  # Remove the ! prefix
                    MediaFiles = [file for file in MediaFiles if ExcludeTerm not in (file.FileName or '').lower()]
                else:
                    # Positive filter - include only files containing the term
                    MediaFiles = [file for file in MediaFiles if SearchLower in (file.FileName or '').lower()]
            
            # Sort by size descending (simple)
            MediaFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            
            # Calculate pagination
            TotalCount = len(MediaFiles)
            TotalPages = (TotalCount + PageSize - 1) // PageSize
            
            # Get page slice
            StartIndex = (Page - 1) * PageSize
            EndIndex = StartIndex + PageSize
            PageFiles = MediaFiles[StartIndex:EndIndex]
            
            # Format for display
            DisplayFiles = []
            for file in PageFiles:
                # Extract directory from file path
                import os
                Directory = os.path.dirname(file.FilePath) if file.FilePath else ''
                
                DisplayFiles.append({
                    'Id': file.Id,
                    'FileName': file.FileName,
                    'FilePath': file.FilePath,
                    'Directory': Directory,
                    'SizeMB': f"{file.SizeMB:.2f} MB" if file.SizeMB else 'Unknown',
                    'LastScannedDate': file.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if file.LastScannedDate and hasattr(file.LastScannedDate, 'strftime') else str(file.LastScannedDate) if file.LastScannedDate else 'Unknown',
                    'Codec': file.Codec or 'Unknown',
                    'Resolution': file.Resolution or 'Unknown',
                    'DurationMinutes': f"{file.DurationMinutes:.1f} min" if file.DurationMinutes else 'Unknown',
                    'AssignedProfile': file.AssignedProfile or None
                })
            
            return {
                'MediaFiles': DisplayFiles,
                'TotalCount': TotalCount,
                'TotalPages': TotalPages
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting paginated media files", e, "GetMediaFilesPaginated", "FileScanningViewModel")
            return {
                'MediaFiles': [],
                'TotalCount': 0,
                'TotalPages': 0
            }
    
    def RefreshMediaFile(self, MediaFileId: int) -> Dict[str, Any]:
        """Refresh a single media file using existing file scanning process."""
        try:
            MediaFile = self.BusinessService.DatabaseManager.GetMediaFileById(MediaFileId)
            if not MediaFile:
                return {'Success': False, 'Message': 'Media file not found'}
            
            # Step 1: Check if exact file still exists
            if os.path.exists(MediaFile.FilePath):
                # File exists - refresh it directly
                self.BusinessService.ProcessSingleMediaFile(
                    FilePath=MediaFile.FilePath,
                    RootFolderId=None,
                    ExtractMetadata=True
                )
                return {'Success': True, 'Message': f'Refreshed {MediaFile.FileName}'}
            
            # Step 2: File doesn't exist - delete from database
            LoggingService.LogWarning(f"File does not exist for refresh: {MediaFile.FilePath}", 'RefreshMediaFile', 'FileScanningViewModel')
            Deleted = self.BusinessService.DatabaseManager.DeleteMediaFile(MediaFileId)
            if Deleted:
                return {'Success': True, 'Message': f'Deleted missing file entry: {MediaFile.FileName}'}
            else:
                return {'Success': False, 'Message': f'Failed to delete missing file entry: {MediaFile.FileName}'}
        except Exception as e:
            return {'Success': False, 'Message': str(e)}
    
    def ClearScanState(self):
        """Clear all scan-related state."""
        self.IsScanning = False
        self.ScanProgress = 0.0
        self.CurrentScanDirectory = ""
        self.ScanResults = {
            'TotalFiles': 0,
            'ProcessedFiles': 0,
            'SkippedFiles': 0,
            'EncodingErrors': 0,
            'NewFiles': 0,
            'UpdatedFiles': 0,
            'DeletedFiles': 0
        }
        self.ScanErrors.clear()
        self.IsError = False
        self.ErrorMessage = ""
        self.ScanStatusMessage = "Ready to scan"
    
    def RefreshData(self):
        """Refresh all data from the business service."""
        try:
            self.LoadRootFolders()
            if self.SelectedRootFolder:
                self.LoadMediaFiles(self.SelectedRootFolder)
            else:
                self.LoadMediaFiles()
            self.UpdateScanStatus()
            
        except Exception as e:
            LoggingService.LogException("Error refreshing data", e, "RefreshData", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error refreshing data: {str(e)}"
    
    def LoadScanDirectories(self):
        """Load scan directories from SystemSettings table."""
        try:
            self.ScanDirectories = self.BusinessService.GetScanDirectories()
        except Exception as e:
            LoggingService.LogInfoError(f"Error loading scan directories: {str(e)}")
            self.ScanDirectories = []
    
    def GetScanDirectoriesForDisplay(self) -> List[Dict[str, str]]:
        """Get scan directories formatted for display."""
        DisplayDirectories = []
        for directory in self.ScanDirectories:
            DisplayDirectories.append({
                'Key': directory['Key'],
                'Path': directory['Path'],
                'Description': directory['Description'],
                'DisplayText': f"{directory['Description']} ({directory['Path']})"
            })
        return DisplayDirectories
    
    
    def ExtractMetadataForExistingFiles(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Extract metadata for existing files that need it."""
        try:
            LoggingService.LogFunctionEntry("ExtractMetadataForExistingFiles", 'FileScanningViewModel', f"RootFolderId: {RootFolderId}")
            
            # Call the business service to extract metadata
            result = self.BusinessService.ExtractMetadataForExistingFiles(RootFolderId)
            
            if result['Success']:
                # Refresh data to show updated metadata
                self.RefreshData()
                LoggingService.LogInfo(f"Successfully extracted metadata for {result.get('ProcessedFiles', 0)} files", 'FileScanningViewModel', 'ExtractMetadataForExistingFiles')
            else:
                LoggingService.LogWarning(f"Metadata extraction failed: {result.get('Message', '', 'Unknown error')}", 'FileScanningViewModel', 'ExtractMetadataForExistingFiles')
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error extracting metadata for existing files", e, 'ExtractMetadataForExistingFiles', 'FileScanningViewModel')
            return {
                'Success': False,
                'Message': f'Error extracting metadata: {str(e)}',
                'Error': 'MetadataExtractionError'
            }
    
    def GetStatistics(self) -> Dict[str, Any]:
        """Get database statistics for display."""
        try:
            # Get statistics from business service
            stats = self.BusinessService.GetStatistics()
            
            return {
                'TotalMediaFiles': stats.get('TotalMediaFiles', 0),
                'FilesWithoutProfiles': stats.get('FilesWithoutProfiles', 0),
                'TotalRootFolders': stats.get('TotalRootFolders', 0),
                'TotalSizeGB': stats.get('TotalSizeGB', 0.0),
                'LastScanDate': stats.get('LastScanDate', 'Never'),
                'FilesWithMetadata': stats.get('FilesWithMetadata', 0),
                'FilesWithoutMetadata': stats.get('FilesWithoutMetadata', 0)
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting statistics", e, "FileScanningViewModel", "GetStatistics")
            return {
                'TotalMediaFiles': 0,
                'FilesWithoutProfiles': 0,
                'TotalRootFolders': 0,
                'TotalSizeGB': 0.0,
                'LastScanDate': 'Error',
                'FilesWithMetadata': 0,
                'FilesWithoutMetadata': 0
            }
    
    def AddOrUpdateScanDirectory(self, Key: Optional[str], Path: str, Description: str) -> Dict[str, Any]:
        """Add or update a scan directory in SystemSettings."""
        try:
            from Services.LoggingService import LoggingService
            
            LoggingService.LogInfo(f"Adding/updating scan directory: {Path}", "AddOrUpdateScanDirectory", "FileScanningViewModel")
            
            result = self.BusinessService.AddOrUpdateScanDirectory(Key, Path, Description)
            
            if result['Success']:
                # Reload scan directories to reflect changes
                self.LoadScanDirectories()
                LoggingService.LogInfo(f"Successfully added/updated scan directory: {Path}", "AddOrUpdateScanDirectory", "FileScanningViewModel")
            else:
                LoggingService.LogWarning(f"Failed to add/update scan directory: {result.get('Error', 'Unknown error')}", "AddOrUpdateScanDirectory", "FileScanningViewModel")
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error adding/updating scan directory", e, "AddOrUpdateScanDirectory", "FileScanningViewModel")
            return {
                'Success': False,
                'Error': f'Error adding/updating scan directory: {str(e)}'
            }
    
    def DeleteScanDirectory(self, Key: str) -> Dict[str, Any]:
        """Delete a scan directory from SystemSettings."""
        try:
            from Services.LoggingService import LoggingService
            
            LoggingService.LogInfo(f"Deleting scan directory with key: {Key}", "DeleteScanDirectory", "FileScanningViewModel")
            
            result = self.BusinessService.DeleteScanDirectory(Key)
            
            if result['Success']:
                # Reload scan directories to reflect changes
                self.LoadScanDirectories()
                LoggingService.LogInfo(f"Successfully deleted scan directory: {Key}", "DeleteScanDirectory", "FileScanningViewModel")
            else:
                LoggingService.LogWarning(f"Failed to delete scan directory: {result.get('Error', 'Unknown error')}", "DeleteScanDirectory", "FileScanningViewModel")
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error deleting scan directory", e, "DeleteScanDirectory", "FileScanningViewModel")
            return {
                'Success': False,
                'Error': f'Error deleting scan directory: {str(e)}'
            }