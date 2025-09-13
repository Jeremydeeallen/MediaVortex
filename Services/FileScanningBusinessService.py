import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Services.FileManagerService import FileManagerService
from Repositories.DatabaseManager import DatabaseManager
from Services.DebugService import DebugService


class FileScanningBusinessService:
    """Orchestrates the file scanning process and coordinates between services."""
    
    def __init__(self, databaseManager: DatabaseManager = None, fileManager: FileManagerService = None):
        self.DatabaseManager = databaseManager or DatabaseManager()
        self.FileManager = fileManager or FileManagerService()
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
        self.ScanErrors = []
    
    def StartScanning(self, rootFolderPath: str, recursive: bool = True) -> Dict[str, Any]:
        """Start scanning a root folder for media files."""
        try:
            DebugService.LogFunctionEntry("StartScanning", rootFolderPath, recursive)
            
            if self.IsScanning:
                return {
                    'Success': False,
                    'Message': 'Scan is already in progress',
                    'Error': 'ScanInProgress'
                }
            
            # Validate the root folder path
            if not rootFolderPath or not os.path.exists(rootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Root folder does not exist: {rootFolderPath}',
                    'Error': 'InvalidPath'
                }
            
            if not os.path.isdir(rootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Path is not a directory: {rootFolderPath}',
                    'Error': 'NotDirectory'
                }
            
            # Initialize scan state
            self.IsScanning = True
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = rootFolderPath
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
            self.FileManager.ResetStats()
            
            # Start the scanning process
            scanResult = self.PerformScan(rootFolderPath, recursive)
            
            return scanResult
            
        except Exception as e:
            DebugService.LogException("Error starting scan", e)
            self.IsScanning = False
            return {
                'Success': False,
                'Message': f'Error starting scan: {str(e)}',
                'Error': 'ScanError'
            }
    
    def PerformScan(self, rootFolderPath: str, recursive: bool) -> Dict[str, Any]:
        """Perform the actual scanning process."""
        try:
            DebugService.Log("Starting scan of directory: {}", rootFolderPath)
            
            # Step 1: Calculate directory size
            DebugService.Log("Calculating directory size...")
            self.ScanProgress = 10.0
            totalSizeGB = self.FileManager.CalculateDirectorySize(rootFolderPath)
            
            # Step 2: Get or create root folder record
            DebugService.Log("Managing root folder record...")
            self.ScanProgress = 20.0
            rootFolder = self.GetOrCreateRootFolder(rootFolderPath, totalSizeGB)
            
            # Step 3: Scan for media files
            DebugService.Log("Scanning for media files...")
            self.ScanProgress = 30.0
            mediaFiles = self.FileManager.ScanDirectory(rootFolderPath, recursive)
            self.ScanResults['TotalFiles'] = len(mediaFiles)
            
            # Step 4: Process each media file
            DebugService.Log("Processing {} media files...", len(mediaFiles))
            self.ProcessMediaFiles(mediaFiles, rootFolder.Id)
            
            # Step 5: Update scan results
            self.ScanProgress = 90.0
            self.UpdateScanResults()
            
            # Step 6: Complete scan
            self.ScanProgress = 100.0
            self.IsScanning = False
            
            DebugService.Log("Scan completed successfully")
            
            return {
                'Success': True,
                'Message': 'Scan completed successfully',
                'Results': self.ScanResults.copy(),
                'RootFolderId': rootFolder.Id,
                'TotalSizeGB': totalSizeGB
            }
            
        except Exception as e:
            DebugService.LogException("Error during scan", e)
            self.IsScanning = False
            self.ScanErrors.append(f"Scan error: {str(e)}")
            return {
                'Success': False,
                'Message': f'Error during scan: {str(e)}',
                'Error': 'ScanError',
                'Results': self.ScanResults.copy()
            }
    
    def GetOrCreateRootFolder(self, rootFolderPath: str, totalSizeGB: float) -> RootFolderModel:
        """Get existing root folder or create a new one."""
        try:
            # Check if root folder already exists
            existingFolders = self.DatabaseManager.GetAllRootFolders()
            
            for folder in existingFolders:
                if folder.RootFolder == rootFolderPath:
                    # Update existing folder
                    folder.LastScannedDate = datetime.now()
                    folder.TotalSizeGB = totalSizeGB
                    folderId = self.DatabaseManager.SaveRootFolder(folder)
                    folder.Id = folderId
                    DebugService.Log("Updated existing root folder: {}", rootFolderPath)
                    return folder
            
            # Create new root folder
            newFolder = RootFolderModel(
                RootFolder=rootFolderPath,
                LastScannedDate=datetime.now(),
                TotalSizeGB=totalSizeGB
            )
            folderId = self.DatabaseManager.SaveRootFolder(newFolder)
            newFolder.Id = folderId
            DebugService.Log("Created new root folder: {}", rootFolderPath)
            return newFolder
            
        except Exception as e:
            DebugService.LogException("Error managing root folder", e)
            raise
    
    def ProcessMediaFiles(self, mediaFiles: List[str], rootFolderId: Optional[int]):
        """Process each media file found during scanning."""
        try:
            totalFiles = len(mediaFiles)
            
            for i, filePath in enumerate(mediaFiles):
                try:
                    # Update progress
                    progress = 30.0 + (60.0 * (i + 1) / totalFiles)
                    self.ScanProgress = progress
                    
                    # Process the file
                    self.ProcessSingleMediaFile(filePath, rootFolderId)
                    
                except Exception as e:
                    DebugService.LogException("Error processing media file", e)
                    self.ScanErrors.append(f"Error processing {filePath}: {str(e)}")
                    continue
            
        except Exception as e:
            DebugService.LogException("Error processing media files", e)
            raise
    
    def ProcessSingleMediaFile(self, filePath: str, rootFolderId: Optional[int]):
        """Process a single media file."""
        try:
            # Get file information
            fileSizeMB = self.FileManager.GetFileSizeMB(filePath)
            fileName = self.FileManager.GetFileNameFromPath(filePath)
            
            # Check if file already exists in database
            existingFiles = self.DatabaseManager.GetAllMediaFiles()
            existingFile = None
            
            for mediaFile in existingFiles:
                if mediaFile.FilePath == filePath:
                    existingFile = mediaFile
                    break
            
            if existingFile:
                # Update existing file
                existingFile.SizeMB = fileSizeMB
                existingFile.LastScannedDate = datetime.now()
                self.DatabaseManager.SaveMediaFile(existingFile)
                self.ScanResults['UpdatedFiles'] += 1
                DebugService.Log("Updated existing media file: {}", filePath)
            else:
                # Create new file record
                newFile = MediaFileModel(
                    SeasonId=rootFolderId,  # Using root folder ID as season ID for now
                    FilePath=filePath,
                    FileName=fileName,
                    SizeMB=fileSizeMB,
                    LastScannedDate=datetime.now()
                )
                self.DatabaseManager.SaveMediaFile(newFile)
                self.ScanResults['NewFiles'] += 1
                DebugService.Log("Added new media file: {}", filePath)
            
            self.ScanResults['ProcessedFiles'] += 1
            
        except Exception as e:
            DebugService.LogException("Error processing single media file", e)
            self.ScanResults['SkippedFiles'] += 1
            raise
    
    def UpdateScanResults(self):
        """Update scan results with file manager statistics."""
        try:
            fileManagerStats = self.FileManager.GetProcessingStats()
            encodingErrors = self.FileManager.GetEncodingErrors()
            
            self.ScanResults['SkippedFiles'] = fileManagerStats['SkippedFiles']
            self.ScanResults['EncodingErrors'] = fileManagerStats['EncodingErrors']
            
            # Add encoding errors to scan errors
            self.ScanErrors.extend(encodingErrors)
            
            DebugService.Log("Scan results updated: {}", self.ScanResults)
            
        except Exception as e:
            DebugService.LogException("Error updating scan results", e)
    
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
            
            DebugService.Log("Scan stopped by user request")
            
            return {
                'Success': True,
                'Message': 'Scan stopped successfully',
                'Results': self.ScanResults.copy()
            }
            
        except Exception as e:
            DebugService.LogException("Error stopping scan", e)
            return {
                'Success': False,
                'Message': f'Error stopping scan: {str(e)}',
                'Error': 'StopError'
            }
    
    def GetScanStatus(self) -> Dict[str, Any]:
        """Get current scan status and progress."""
        return {
            'IsScanning': self.IsScanning,
            'Progress': self.ScanProgress,
            'CurrentDirectory': self.CurrentScanDirectory,
            'Results': self.ScanResults.copy(),
            'Errors': self.ScanErrors.copy()
        }
    
    def GetRootFolders(self) -> List[RootFolderModel]:
        """Get all root folders."""
        try:
            return self.DatabaseManager.GetAllRootFolders()
        except Exception as e:
            DebugService.LogException("Error getting root folders", e)
            return []
    
    def GetMediaFiles(self, rootFolderPath: Optional[str] = None) -> List[MediaFileModel]:
        """Get media files, optionally filtered by root folder."""
        try:
            if rootFolderPath:
                return self.DatabaseManager.GetMediaFilesByRootFolder(rootFolderPath)
            else:
                return self.DatabaseManager.GetAllMediaFiles()
        except Exception as e:
            DebugService.LogException("Error getting media files", e)
            return []
    
    def DeleteRootFolder(self, rootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            return self.DatabaseManager.DeleteRootFolder(rootFolderId)
        except Exception as e:
            DebugService.LogException("Error deleting root folder", e)
            return False
    
    def DeleteMediaFile(self, mediaFileId: int) -> bool:
        """Delete a media file."""
        try:
            return self.DatabaseManager.DeleteMediaFile(mediaFileId)
        except Exception as e:
            DebugService.LogException("Error deleting media file", e)
            return False
    
    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings from SystemSettings table."""
        try:
            return self.DatabaseManager.GetScanDirectories()
        except Exception as e:
            DebugService.LogException("Error getting scan directories", e)
            return []
    
    def ResetScanState(self):
        """Reset the scan state to allow new scans."""
        self.IsScanning = False
        self.ScanProgress = 0
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
        self.ScanErrors = []
