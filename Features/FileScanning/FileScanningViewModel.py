from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os
from Features.FileScanning.Models.RootFolderModel import RootFolderModel
from Core.Models.MediaFileModel import MediaFileModel
from Features.FileScanning.Models.SeasonModel import SeasonModel
from Features.FileScanning.Models.FileScanResultModel import FileScanResultModel
from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
from Core.Logging.LoggingService import LoggingService
import ntpath
from Core.Path.PathFs import Exists as _Exists


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
                self.LastScanTime = datetime.now(timezone.utc)
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

    def AddRootFolder(self, RootFolderPath: str, PreferredWorkerName: str = None) -> Dict[str, Any]:
        """Add a new root folder."""
        try:
            result = self.BusinessService.AddRootFolder(RootFolderPath, PreferredWorkerName)
            if result.get('Success'):
                self.ScanStatusMessage = "Root folder added successfully"
                self.IsError = False
                self.ErrorMessage = ""
            else:
                self.IsError = True
                self.ErrorMessage = result.get('Message', 'Failed to add root folder')
                self.ScanStatusMessage = self.ErrorMessage
            return result
        except Exception as e:
            LoggingService.LogException("Error adding root folder", e, "AddRootFolder", "FileScanningViewModel")
            self.IsError = True
            self.ErrorMessage = f"Error adding root folder: {str(e)}"
            return {'Success': False, 'Message': self.ErrorMessage}

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
        # directive: path-class-perfection | # see path.C23
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMFS
        _Pm = _GPMFS()
        DisplayFolders = []
        for folder in self.RootFolders:
            P = folder.Path
            Display = P.CanonicalDisplay(_Pm) if P is not None else ""
            DisplayFolders.append({
                'Id': folder.Id,
                'RootFolder': Display,
                'LastScannedDate': folder.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if folder.LastScannedDate and hasattr(folder.LastScannedDate, 'strftime') else str(folder.LastScannedDate) if folder.LastScannedDate else 'Never',
                'TotalSizeGB': f"{folder.TotalSizeGB:.2f} GB"
            })
        return DisplayFolders

    def GetRootFoldersPaginated(self, Page: int, PageSize: int, Search: str = '', SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> Dict[str, Any]:
        """Get root folders with SQL-level pagination, filtering, and sorting."""
        # directive: path-class-perfection | # see path.C23
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMFS
        try:
            _Pm = _GPMFS()
            result = self.BusinessService.Repository.GetRootFoldersPaginated(Page, PageSize, Search, SortColumn, SortOrder)
            PageFolders = result['RootFolders']

            MkvCounts = self.BusinessService.Repository.GetMkvCountsByRootFolder()

            DisplayFolders = []
            for folder in PageFolders:
                P = folder.Path
                Display = P.CanonicalDisplay(_Pm) if P is not None else ""
                normalizedPath = Display.replace('/', '\\').rstrip('\\').lower()
                mkvCount = MkvCounts.get(normalizedPath, 0)
                DisplayFolders.append({
                    'Id': folder.Id,
                    'RootFolder': Display,
                    'LastScannedDate': folder.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if folder.LastScannedDate and hasattr(folder.LastScannedDate, 'strftime') else str(folder.LastScannedDate) if folder.LastScannedDate else 'Never',
                    'TotalSizeGB': f"{folder.TotalSizeGB:.2f} GB",
                    'MkvFileCount': mkvCount
                })

            AllDisplayFolders = []
            allFolders = self.BusinessService.Repository.GetAllRootFolders()
            for folder in allFolders:
                P = folder.Path
                Display = P.CanonicalDisplay(_Pm) if P is not None else ""
                AllDisplayFolders.append({
                    'Id': folder.Id,
                    'RootFolder': Display,
                    'LastScannedDate': folder.LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if folder.LastScannedDate and hasattr(folder.LastScannedDate, 'strftime') else str(folder.LastScannedDate) if folder.LastScannedDate else 'Never',
                    'TotalSizeGB': f"{folder.TotalSizeGB:.2f} GB"
                })

            return {
                'RootFolders': DisplayFolders,
                'TotalCount': result['TotalCount'],
                'TotalPages': result['TotalPages'],
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

    def GetSubfoldersPaginated(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                               Search: str = '', SortColumn: str = 'TotalSizeMB',
                               SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get subfolders under a root folder with aggregated stats, respecting ExcludedDirectories."""
        try:
            # Load excluded directories from SystemSettings
            excluded_dirs = []
            try:
                excluded_setting = self.BusinessService.Repository.ExecuteQuery(
                    "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s",
                    ('ExcludedDirectories',)
                )
                if excluded_setting and excluded_setting[0]['SettingValue']:
                    excluded_dirs = [d.strip() for d in excluded_setting[0]['SettingValue'].split(',') if d.strip()]
            except Exception:
                pass  # If we can't load exclusions, proceed without them

            result = self.BusinessService.Repository.GetSubfoldersByRootFolder(
                RootFolderPath, Page, PageSize, Search, SortColumn, SortOrder, excluded_dirs
            )

            # Format sizes for display
            for subfolder in result['Subfolders']:
                size_mb = subfolder['TotalSizeMB']
                if size_mb >= 1024:
                    subfolder['TotalSizeDisplay'] = f"{size_mb / 1024:.2f} GB"
                else:
                    subfolder['TotalSizeDisplay'] = f"{size_mb:.2f} MB"

            return result

        except Exception as e:
            LoggingService.LogException("Error getting subfolders", e, "GetSubfoldersPaginated", "FileScanningViewModel")
            return {
                'Subfolders': [],
                'TotalCount': 0,
                'TotalPages': 0
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
        """Get media files with SQL-level pagination, filtering, and sorting."""
        try:
            # SQL-level pagination, filtering, and sorting
            result = self.BusinessService.Repository.GetMediaFilesPaginated(
                Page, PageSize, Search, RootFolderPath, SortBy, SortOrder
            )

            # Format rows for display
            DisplayFiles = []
            for row in result['Rows']:
                FilePath = row['FilePath'] or ''
                Directory = ntpath.dirname(FilePath) if FilePath else ''
                SizeMB = row['SizeMB']
                DurationMinutes = row['DurationMinutes']
                LastScannedDate = row['LastScannedDate']

                DisplayFiles.append({
                    'Id': row['Id'],
                    'FileName': row['FileName'],
                    'FilePath': FilePath,
                    'Directory': Directory,
                    'SizeMB': f"{SizeMB:.2f} MB" if SizeMB else 'Unknown',
                    'LastScannedDate': LastScannedDate.strftime('%Y-%m-%d %H:%M:%S') if LastScannedDate and hasattr(LastScannedDate, 'strftime') else str(LastScannedDate) if LastScannedDate else 'Unknown',
                    'Codec': row['Codec'] or 'Unknown',
                    'Resolution': row['Resolution'] or 'Unknown',
                    'DurationMinutes': f"{DurationMinutes:.1f} min" if DurationMinutes else 'Unknown',
                    'AssignedProfile': row['AssignedProfile'] or None
                })

            return {
                'MediaFiles': DisplayFiles,
                'TotalCount': result['TotalCount'],
                'TotalPages': result['TotalPages']
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
            MediaFile = self.BusinessService.Repository.GetMediaFileById(MediaFileId)
            if not MediaFile:
                return {'Success': False, 'Message': 'Media file not found'}

            # directive: path-class-perfection | # see path.C21
            from Core.Path.Path import Path as _PathMF
            from Core.Path.Worker import Worker as _WMF
            if _Exists(_PathMF(MediaFile.StorageRootId, MediaFile.RelativePath or ''), _WMF.Current()):
                # File exists - refresh it directly
                self.BusinessService.ProcessSingleMediaFile(
                    FilePath=MediaFile.FilePath,
                    RootFolderId=None,
                    ExtractMetadata=True
                )
                return {'Success': True, 'Message': f'Refreshed {MediaFile.FileName}'}

            # Step 2: File doesn't exist - delete from database
            LoggingService.LogWarning(f"File does not exist for refresh: {MediaFile.FilePath}", 'RefreshMediaFile', 'FileScanningViewModel')
            Deleted = self.BusinessService.Repository.DeleteMediaFile(MediaFileId)
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


    def GetTranscodeCandidatesPaginated(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                         Search: str = '', SortColumn: str = 'EstimatedSavingsMB',
                                         SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get transcode candidate subfolders ranked by estimated savings."""
        try:
            result = self.BusinessService.Repository.GetTranscodeCandidatesByRootFolder(
                RootFolderPath, Page, PageSize, Search, SortColumn, SortOrder
            )

            # Format sizes for display
            for subfolder in result['Subfolders']:
                size_mb = subfolder['TotalSizeMB']
                if size_mb >= 1024:
                    subfolder['TotalSizeDisplay'] = f"{size_mb / 1024:.2f} GB"
                else:
                    subfolder['TotalSizeDisplay'] = f"{size_mb:.2f} MB"

                savings_mb = subfolder['EstimatedSavingsMB']
                if savings_mb >= 1024:
                    subfolder['EstimatedSavingsDisplay'] = f"~{savings_mb / 1024:.1f} GB"
                else:
                    subfolder['EstimatedSavingsDisplay'] = f"~{savings_mb:.0f} MB"

                bitrate = subfolder.get('AvgBitrateKbps', 0)
                if bitrate >= 1000:
                    subfolder['AvgBitrateDisplay'] = f"{bitrate / 1000:.1f} Mbps"
                else:
                    subfolder['AvgBitrateDisplay'] = f"{bitrate} Kbps" if bitrate else '-'

            return result

        except Exception as e:
            LoggingService.LogException("Error getting transcode candidates", e, "GetTranscodeCandidatesPaginated", "FileScanningViewModel")
            return {
                'Subfolders': [],
                'TotalCount': 0,
                'TotalPages': 0
            }

    def GetTranscodeCandidateFiles(self, SubfolderPath: str, Page: int = 1, PageSize: int = 25) -> Dict[str, Any]:
        """Get individual untranscoded files in a subfolder for drill-down."""
        try:
            result = self.BusinessService.Repository.GetTranscodeCandidateFiles(SubfolderPath, Page, PageSize)

            # Format sizes for display
            for file in result['Files']:
                size_mb = file['SizeMB']
                if size_mb >= 1024:
                    file['SizeDisplay'] = f"{size_mb / 1024:.2f} GB"
                else:
                    file['SizeDisplay'] = f"{size_mb:.2f} MB"

            return result

        except Exception as e:
            LoggingService.LogException("Error getting transcode candidate files", e, "GetTranscodeCandidateFiles", "FileScanningViewModel")
            return {
                'Files': [],
                'TotalCount': 0,
                'TotalPages': 0
            }

    def GetAllTranscodeCandidateFilesPaginated(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                                Search: str = '', SortColumn: str = 'VideoBitrateKbps',
                                                SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get individual transcode candidate files across a root folder, with display formatting."""
        try:
            Result = self.BusinessService.Repository.GetAllTranscodeCandidateFiles(
                RootFolderPath, Page, PageSize, Search, SortColumn, SortOrder
            )

            for File in Result['Files']:
                SizeMB = File['SizeMB']
                if SizeMB >= 1024:
                    File['SizeDisplay'] = f"{SizeMB / 1024:.2f} GB"
                else:
                    File['SizeDisplay'] = f"{SizeMB:.2f} MB"

                Bitrate = File.get('VideoBitrateKbps', 0)
                if Bitrate >= 1000:
                    File['BitrateDisplay'] = f"{Bitrate / 1000:.1f} Mbps"
                else:
                    File['BitrateDisplay'] = f"{Bitrate} Kbps" if Bitrate else '-'

            return Result

        except Exception as e:
            LoggingService.LogException("Error getting all transcode candidate files", e, "GetAllTranscodeCandidateFilesPaginated", "FileScanningViewModel")
            return {
                'Files': [],
                'TotalCount': 0,
                'TotalPages': 0
            }

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
        """Get library statistics for display."""
        try:
            stats = self.BusinessService.GetStatistics()

            return {
                'TotalMediaFiles': stats.get('TotalMediaFiles', 0),
                'EncodedByMediaVortex': stats.get('EncodedByMediaVortex', 0),
                'SpaceSavedGB': stats.get('SpaceSavedGB', 0.0),
                'TotalSizeGB': stats.get('TotalSizeGB', 0.0),
                'PossiblyCorrupt': stats.get('PossiblyCorrupt', 0)
            }

        except Exception as e:
            LoggingService.LogException("Error getting statistics", e, "FileScanningViewModel", "GetStatistics")
            return {
                'TotalMediaFiles': 0,
                'EncodedByMediaVortex': 0,
                'SpaceSavedGB': 0.0,
                'TotalSizeGB': 0.0,
                'PossiblyCorrupt': 0
            }

    def AddOrUpdateScanDirectory(self, Key: Optional[str], Path: str, Description: str) -> Dict[str, Any]:
        """Add or update a scan directory in SystemSettings."""
        try:
            from Core.Logging.LoggingService import LoggingService

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
            from Core.Logging.LoggingService import LoggingService

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
