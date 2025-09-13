#!/usr/bin/env python3
"""
Subprocess script for directory scanning.
This script runs as a separate process to scan directories and update the database.
"""

import os
import sys
import uuid
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService
from Services.FileManagerService import FileManagerService
from Services.LoggingService import LoggingService
from Models.FileScanResultModel import FileScanResultModel

# Enable debug mode for troubleshooting
LoggingService.EnableDebug()


class ScanDirectoryProcess:
    """Handles directory scanning in a separate process."""
    
    def __init__(self, JobId: str, RootFolderPath: str, Recursive: bool = True):
        self.JobId = JobId
        self.RootFolderPath = RootFolderPath
        self.Recursive = Recursive
        self.DatabaseService = DatabaseService()
        self.FileManagerService = FileManagerService()
        self.IsRunning = True
        self.ProcessId = os.getpid()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.SignalHandler)
        signal.signal(signal.SIGINT, self.SignalHandler)
    
    def SignalHandler(self, Signum, Frame):
        """Handle shutdown signals gracefully."""
        LoggingService.LogInfo(f"Scan process {self.ProcessId} received signal {Signum}, shutting down...", 'ScanDirectoryProcess', 'SignalHandler')
        self.IsRunning = False
    
    def UpdateJobStatus(self, Status: str, Progress: float = None, CurrentDirectory: str = None, 
                       ErrorMessage: str = None, EndTime: datetime = None, ProcessId: int = None, 
                       StartTime: datetime = None, ScanResults: FileScanResultModel = None, **Stats):
        """Update the scan job status in the database."""
        try:
            UpdateFields = ["Status = ?", "LastUpdated = ?"]
            UpdateValues = [Status, datetime.now()]
            
            if Progress is not None:
                UpdateFields.append("Progress = ?")
                UpdateValues.append(Progress)
            
            if CurrentDirectory is not None:
                UpdateFields.append("CurrentDirectory = ?")
                UpdateValues.append(CurrentDirectory)
            
            if ErrorMessage is not None:
                UpdateFields.append("ErrorMessage = ?")
                UpdateValues.append(ErrorMessage)
            
            if EndTime is not None:
                UpdateFields.append("EndTime = ?")
                UpdateValues.append(EndTime)
            
            if ProcessId is not None:
                UpdateFields.append("ProcessId = ?")
                UpdateValues.append(ProcessId)
            
            if StartTime is not None:
                UpdateFields.append("StartTime = ?")
                UpdateValues.append(StartTime)
            
            # Add scan results if provided
            if ScanResults is not None:
                UpdateFields.extend([
                    "TotalFiles = ?", "ProcessedFiles = ?", "SkippedFiles = ?", 
                    "EncodingErrors = ?", "NewFiles = ?", "UpdatedFiles = ?", "DeletedFiles = ?"
                ])
                UpdateValues.extend([
                    ScanResults.TotalFilesFound, ScanResults.TotalFilesProcessed, ScanResults.TotalFilesSkipped,
                    ScanResults.TotalFilesWithErrors, 0, 0, 0  # NewFiles, UpdatedFiles, DeletedFiles not tracked separately
                ])
            
            # Add any additional legacy stats for backward compatibility
            for Key, Value in Stats.items():
                if Key in ['TotalFiles', 'ProcessedFiles', 'SkippedFiles', 'EncodingErrors', 
                          'NewFiles', 'UpdatedFiles', 'DeletedFiles']:
                    UpdateFields.append(f"{Key} = ?")
                    UpdateValues.append(Value)
            
            UpdateValues.append(self.JobId)
            
            Query = f"UPDATE ScanJobs SET {', '.join(UpdateFields)} WHERE JobId = ?"
            self.DatabaseService.ExecuteNonQuery(Query, UpdateValues)
            
        except Exception as e:
            LoggingService.LogException(f"Error updating job status for {self.JobId}", e, 'ScanDirectoryProcess', 'UpdateJobStatus')
    
    def GetOrCreateRootFolder(self, RootFolderPath: str) -> int:
        """Get or create a root folder record."""
        try:
            # Check if root folder exists
            Query = "SELECT Id FROM RootFolders WHERE RootFolder = ?"
            Result = self.DatabaseService.ExecuteQuery(Query, (RootFolderPath,))
            
            if Result:
                return Result[0]['Id']
            
            # Create new root folder
            InsertQuery = """
            INSERT INTO RootFolders (RootFolder, LastScannedDate, TotalSizeGB)
            VALUES (?, ?, 0.0)
            """
            self.DatabaseService.ExecuteNonQuery(InsertQuery, (RootFolderPath, datetime.now()))
            
            # Get the new ID
            Result = self.DatabaseService.ExecuteQuery(Query, (RootFolderPath,))
            return Result[0]['Id'] if Result else None
            
        except Exception as e:
            LoggingService.LogException(f"Error getting/creating root folder for {RootFolderPath}", e, 'ScanDirectoryProcess', 'GetOrCreateRootFolder')
            return None
    
    def ProcessFile(self, FilePath: str, RootFolderId: int) -> Dict[str, Any]:
        """Process a single file and return stats."""
        try:
            FileName = os.path.basename(FilePath)
            FileSizeMB = self.FileManagerService.GetFileSizeMB(FilePath)
            
            # Check if file already exists
            Query = "SELECT Id FROM MediaFiles WHERE FilePath = ?"
            Result = self.DatabaseService.ExecuteQuery(Query, (FilePath,))
            
            if Result:
                # Update existing file
                UpdateQuery = """
                UPDATE MediaFiles 
                SET SizeMB = ?, LastScannedDate = ?
                WHERE FilePath = ?
                """
                self.DatabaseService.ExecuteNonQuery(UpdateQuery, (FileSizeMB, datetime.now(), FilePath))
                return {'UpdatedFiles': 1}
            else:
                # Insert new file
                InsertQuery = """
                INSERT INTO MediaFiles (SeasonId, FilePath, FileName, SizeMB, LastScannedDate)
                VALUES (?, ?, ?, ?, ?)
                """
                self.DatabaseService.ExecuteNonQuery(InsertQuery, (None, FilePath, FileName, FileSizeMB, datetime.now()))
                return {'NewFiles': 1}
                
        except Exception as e:
            LoggingService.LogException(f"Error processing file {FilePath}", e, 'ScanDirectoryProcess', 'ProcessFile')
            return {'EncodingErrors': 1}
    
    def CleanupMissingFiles(self, FoundFiles: List[str], RootFolderId: int):
        """Remove database records for files that no longer exist on disk."""
        try:
            LoggingService.LogInfo(f"Starting cleanup of missing files for root folder: {RootFolderId}", 'ScanDirectoryProcess', 'CleanupMissingFiles')
            
            # Get all files in database for this root folder
            Query = "SELECT Id, FilePath FROM MediaFiles WHERE SeasonId IN (SELECT Id FROM Seasons WHERE RootFolderId = ?)"
            DatabaseFiles = self.DatabaseService.ExecuteQuery(Query, (RootFolderId,))
            
            # Create set of found file paths for efficient lookup
            FoundFilePaths = set(FoundFiles)
            
            # Find files that are in database but not found on disk
            MissingFiles = []
            for DbFile in DatabaseFiles:
                if DbFile['FilePath'] not in FoundFilePaths:
                    MissingFiles.append(DbFile)
            
            # Remove missing files from database and log the deletion
            for MissingFile in MissingFiles:
                try:
                    # Log the deletion
                    LoggingService.LogInfo(f"Removing missing file from database: {MissingFile['FilePath']}", 'ScanDirectoryProcess', 'CleanupMissingFiles')
                    
                    # Delete the file record
                    DeleteQuery = "DELETE FROM MediaFiles WHERE Id = ?"
                    self.DatabaseService.ExecuteNonQuery(DeleteQuery, (MissingFile['Id'],))
                    
                except Exception as e:
                    LoggingService.LogException(f"Error removing missing file {MissingFile['FilePath']}", e, 'ScanDirectoryProcess', 'CleanupMissingFiles')
            
            if MissingFiles:
                LoggingService.LogInfo(f"Cleaned up {len(MissingFiles)} missing files from database", 'ScanDirectoryProcess', 'CleanupMissingFiles')
            else:
                LoggingService.LogInfo("No missing files found to clean up", 'ScanDirectoryProcess', 'CleanupMissingFiles')
                
        except Exception as e:
            LoggingService.LogException("Error cleaning up missing files", e, 'ScanDirectoryProcess', 'CleanupMissingFiles')
    
    def ScanDirectory(self):
        """Main scanning logic."""
        try:
            LoggingService.LogInfo(f"Starting scan process {self.ProcessId} for job {self.JobId}", 'ScanDirectoryProcess', 'ScanDirectory')
            
            # Update job status to running
            self.UpdateJobStatus('Running', Progress=0.0, ProcessId=self.ProcessId, StartTime=datetime.now())
            
            # Get or create root folder
            RootFolderId = self.GetOrCreateRootFolder(self.RootFolderPath)
            if not RootFolderId:
                self.UpdateJobStatus('Failed', ErrorMessage='Could not create root folder record')
                return
            
            # Initialize scan results
            ScanResults = FileScanResultModel()
            ScanResults.RootFolderId = RootFolderId
            ScanResults.ProcessId = self.ProcessId
            
            # Scan directory
            LoggingService.LogInfo(f"Scanning directory: {self.RootFolderPath}", 'ScanDirectoryProcess', 'ScanDirectory')
            Files = self.FileManagerService.ScanDirectory(self.RootFolderPath, self.Recursive)
            
            if not Files:
                LoggingService.LogWarning(f"No files found in {self.RootFolderPath}", 'ScanDirectoryProcess', 'ScanDirectory')
                ScanResults.ScanStatus = 'Completed'
                ScanResults.ScanEndTime = datetime.now()
                self.UpdateJobStatus('Completed', Progress=100.0, ScanResults=ScanResults)
                return
            
            ScanResults.TotalFilesFound = len(Files)
            self.UpdateJobStatus('Running', ScanResults=ScanResults)
            
            # Process each file
            for Index, FilePath in enumerate(Files):
                if not self.IsRunning:
                    LoggingService.LogInfo(f"Scan process {self.ProcessId} stopped by signal", 'ScanDirectoryProcess', 'ScanDirectory')
                    
                    # Clean up missing files even when scan is stopped
                    try:
                        self.CleanupMissingFiles(Files, RootFolderId)
                    except Exception as e:
                        LoggingService.LogException("Error during cleanup of missing files (stopped scan)", e, 'ScanDirectoryProcess', 'ScanDirectory')
                    
                    ScanResults.ScanStatus = 'Stopped'
                    ScanResults.ScanEndTime = datetime.now()
                    self.UpdateJobStatus('Stopped', Progress=(Index / len(Files)) * 100, ScanResults=ScanResults)
                    return
                
                try:
                    # Update current directory
                    CurrentDir = os.path.dirname(FilePath)
                    Progress = (Index / len(Files)) * 100
                    
                    self.UpdateJobStatus('Running', Progress=Progress, CurrentDirectory=CurrentDir, ScanResults=ScanResults)
                    
                    # Process the file
                    FileStats = self.ProcessFile(FilePath, RootFolderId)
                    
                    # Update scan results
                    if 'NewFiles' in FileStats:
                        ScanResults.TotalFilesProcessed += 1
                    if 'UpdatedFiles' in FileStats:
                        ScanResults.TotalFilesProcessed += 1
                    if 'EncodingErrors' in FileStats:
                        ScanResults.TotalFilesWithErrors += 1
                    
                    # Update database every 10 files
                    if Index % 10 == 0:
                        self.UpdateJobStatus('Running', Progress=Progress, ScanResults=ScanResults)
                    
                except Exception as e:
                    LoggingService.LogException(f"Error processing file {FilePath}", e, 'ScanDirectoryProcess', 'ProcessFile')
                    ScanResults.TotalFilesWithErrors += 1
            
            # Update root folder size with actual calculated size
            try:
                LoggingService.LogInfo(f"Calculating actual directory size for {self.RootFolderPath}", 'ScanDirectoryProcess', 'ScanDirectory')
                TotalSizeGB = self.FileManagerService.CalculateDirectorySize(self.RootFolderPath)
                UpdateQuery = "UPDATE RootFolders SET TotalSizeGB = ?, LastScannedDate = ? WHERE Id = ?"
                self.DatabaseService.ExecuteNonQuery(UpdateQuery, (TotalSizeGB, datetime.now(), RootFolderId))
                LoggingService.LogInfo(f"Updated root folder size to {TotalSizeGB} GB", 'ScanDirectoryProcess', 'ScanDirectory')
            except Exception as e:
                LoggingService.LogException("Error updating root folder size", e, 'ScanDirectoryProcess', 'ScanDirectory')
            
            # Clean up missing files after processing all found files
            try:
                self.CleanupMissingFiles(Files, RootFolderId)
            except Exception as e:
                LoggingService.LogException("Error during cleanup of missing files", e, 'ScanDirectoryProcess', 'ScanDirectory')
            
            # Mark as completed
            ScanResults.ScanStatus = 'Completed'
            ScanResults.ScanEndTime = datetime.now()
            self.UpdateJobStatus('Completed', Progress=100.0, EndTime=datetime.now(), ScanResults=ScanResults)
            LoggingService.LogInfo(f"Scan process {self.ProcessId} completed successfully", 'ScanDirectoryProcess', 'ScanDirectory')
            
        except Exception as e:
            LoggingService.LogException(f"Error in scan process {self.ProcessId}", e, 'ScanDirectoryProcess', 'ScanDirectory')
            self.UpdateJobStatus('Failed', ErrorMessage=str(e), EndTime=datetime.now())
    
    def Run(self):
        """Main entry point for the scan process."""
        try:
            self.ScanDirectory()
        except Exception as e:
            LoggingService.LogException(f"Fatal error in scan process {self.ProcessId}", e, 'ScanDirectoryProcess', 'Run')
            self.UpdateJobStatus('Failed', ErrorMessage=f"Fatal error: {str(e)}", EndTime=datetime.now())
        finally:
            LoggingService.LogInfo(f"Scan process {self.ProcessId} exiting", 'ScanDirectoryProcess', 'Run')


def main():
    """Main function for the scan process."""
    try:
        print(f"ScanDirectoryProcess starting with args: {sys.argv}")
        
        if len(sys.argv) < 3:
            ErrorMsg = f"Usage: ScanDirectoryProcess.py <JobId> <RootFolderPath> [Recursive]. Got {len(sys.argv)} args: {sys.argv}"
            print(ErrorMsg)
            LoggingService.LogError(ErrorMsg, 'ScanDirectoryProcess', 'main')
            sys.exit(1)
        
        JobId = sys.argv[1]
        RootFolderPath = sys.argv[2]
        Recursive = len(sys.argv) > 3 and sys.argv[3].lower() == 'true'
        
        print(f"Starting scan process - JobId: {JobId}, Path: {RootFolderPath}, Recursive: {Recursive}")
        LoggingService.LogInfo(f"Starting scan process - JobId: {JobId}, Path: {RootFolderPath}, Recursive: {Recursive}", 'ScanDirectoryProcess', 'main')
        
        Scanner = ScanDirectoryProcess(JobId, RootFolderPath, Recursive)
        Scanner.Run()
        
        print(f"ScanDirectoryProcess completed successfully for job {JobId}")
        LoggingService.LogInfo(f"ScanDirectoryProcess completed successfully for job {JobId}", 'ScanDirectoryProcess', 'main')
        
    except Exception as e:
        ErrorMsg = f"Fatal error in scan process: {str(e)}"
        print(ErrorMsg)
        LoggingService.LogException("Fatal error in scan process", e, 'ScanDirectoryProcess', 'main')
        sys.exit(1)


if __name__ == "__main__":
    main()
