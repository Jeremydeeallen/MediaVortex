from typing import List, Dict, Any, Optional
from datetime import datetime
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
            LoggingService.LogInfoException("Error in StartScanning", e)
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
            LoggingService.LogInfoException("Error in StopScanning", e)
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
            LoggingService.LogInfoException("Error loading root folders", e)
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
            LoggingService.LogInfoException("Error loading media files", e)
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
            LoggingService.LogInfoException("Error deleting root folder", e)
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
            LoggingService.LogInfoException("Error deleting media file", e)
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
            LoggingService.LogInfoException("Error getting paginated root folders", e)
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
            # Load media files first
            if RootFolderPath:
                self.LoadMediaFiles(RootFolderPath)
            else:
                self.LoadMediaFiles()
            
            # Apply search filter
            FilteredFiles = self.MediaFiles
            if Search:
                SearchLower = Search.lower()
                FilteredFiles = [file for file in self.MediaFiles 
                               if SearchLower in file.FileName.lower() or SearchLower in file.FilePath.lower()]
            
            # Apply sorting
            if SortBy == 'SizeMB':
                # Handle None values properly - put them at the end for DESC, beginning for ASC
                LoggingService.LogInfo(f"Sorting {len(FilteredFiles)} files by SizeMB {SortOrder}. Sample sizes: {[f.SizeMB for f in FilteredFiles[:5]]}", "FileScanningViewModel", "GetMediaFilesPaginated")
                FilteredFiles.sort(key=lambda x: (x.SizeMB is None, x.SizeMB or 0), reverse=(SortOrder == 'DESC'))
                LoggingService.LogInfo(f"After sorting. Sample sizes: {[f.SizeMB for f in FilteredFiles[:5]]}", "FileScanningViewModel", "GetMediaFilesPaginated")
            elif SortBy == 'FileName':
                FilteredFiles.sort(key=lambda x: x.FileName or '', reverse=(SortOrder == 'DESC'))
            elif SortBy == 'Directory':
                FilteredFiles.sort(key=lambda x: x.Directory or '', reverse=(SortOrder == 'DESC'))
            elif SortBy == 'Resolution':
                FilteredFiles.sort(key=lambda x: x.Resolution or '', reverse=(SortOrder == 'DESC'))
            elif SortBy == 'AssignedProfile':
                FilteredFiles.sort(key=lambda x: x.AssignedProfile or '', reverse=(SortOrder == 'DESC'))
            
            # Calculate pagination
            TotalCount = len(FilteredFiles)
            TotalPages = (TotalCount + PageSize - 1) // PageSize
            
            # Get page slice
            StartIndex = (Page - 1) * PageSize
            EndIndex = StartIndex + PageSize
            PageFiles = FilteredFiles[StartIndex:EndIndex]
            
            # Format for display
            DisplayFiles = []
            for file in PageFiles:
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
            
            return {
                'MediaFiles': DisplayFiles,
                'TotalCount': TotalCount,
                'TotalPages': TotalPages
            }
            
        except Exception as e:
            LoggingService.LogInfoException("Error getting paginated media files", e)
            return {
                'MediaFiles': [],
                'TotalCount': 0,
                'TotalPages': 0
            }
    
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
            LoggingService.LogInfoException("Error refreshing data", e)
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