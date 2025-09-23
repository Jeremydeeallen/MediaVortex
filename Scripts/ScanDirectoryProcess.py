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
from Services.FileScanningBusinessService import FileScanningBusinessService
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
        self.FileScanningBusinessService = FileScanningBusinessService()
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
            LoggingService.LogException(f"Error updating job status for {self.JobId}", e, 'UpdateJobStatus', 'ScanDirectoryProcess')
    
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
            LoggingService.LogException(f"Error getting/creating root folder for {RootFolderPath}", e, 'GetOrCreateRootFolder', 'ScanDirectoryProcess')
            return None
    
    
    
    def ScanDirectory(self):
        """Main scanning logic."""
        try:
            LoggingService.LogInfo(f"Starting scan process {self.ProcessId} for job {self.JobId}", 'ScanDirectory', 'ScanDirectoryProcess')
            
            # Update job status to running
            self.UpdateJobStatus('Running', Progress=0.0, ProcessId=self.ProcessId, StartTime=datetime.now())
            
            # Get or create root folder
            self.UpdateJobStatus('Running', Progress=5.0, CurrentDirectory='Setting up root folder...')
            RootFolderId = self.GetOrCreateRootFolder(self.RootFolderPath)
            if not RootFolderId:
                self.UpdateJobStatus('Failed', ErrorMessage='Could not create root folder record')
                return
            
            # Initialize scan results
            ScanResults = FileScanResultModel()
            ScanResults.RootFolderId = RootFolderId
            ScanResults.ProcessId = self.ProcessId
            
            # Scan directory
            self.UpdateJobStatus('Running', Progress=10.0, CurrentDirectory='Scanning directory for media files...')
            LoggingService.LogInfo(f"Scanning directory: {self.RootFolderPath}", 'ScanDirectory', 'ScanDirectoryProcess')
            Files = self.FileManagerService.ScanDirectory(self.RootFolderPath, self.Recursive)
            
            if not Files:
                LoggingService.LogWarning(f"No files found in {self.RootFolderPath}", 'ScanDirectory', 'ScanDirectoryProcess')
                ScanResults.ScanStatus = 'Completed'
                ScanResults.ScanEndTime = datetime.now()
                self.UpdateJobStatus('Completed', Progress=100.0, ScanResults=ScanResults)
                return
            
            ScanResults.TotalFilesFound = len(Files)
            self.UpdateJobStatus('Running', Progress=15.0, CurrentDirectory=f'Found {len(Files)} media files', ScanResults=ScanResults)
            
            # Use business service to process all files with full workflow
            try:
                LoggingService.LogInfo(f"Processing {len(Files)} files using business service workflow", 'ScanDirectory', 'ScanDirectoryProcess')
                
                # Set up business service with scan results
                self.FileScanningBusinessService.ScanResults = ScanResults
                self.FileScanningBusinessService.ScanProgress = 0.0
                
                # Process files with metadata extraction
                self.UpdateJobStatus('Running', Progress=20.0, CurrentDirectory='Processing files with FFprobe...', ScanResults=ScanResults)
                
                # Process files in batches to provide progress updates
                BatchSize = 50  # Process 50 files at a time
                TotalFiles = len(Files)
                
                for BatchStart in range(0, TotalFiles, BatchSize):
                    if not self.IsRunning:
                        LoggingService.LogInfo(f"Scan process {self.ProcessId} stopped by signal during processing", 'ScanDirectory', 'ScanDirectoryProcess')
                        break
                    
                    BatchEnd = min(BatchStart + BatchSize, TotalFiles)
                    BatchFiles = Files[BatchStart:BatchEnd]
                    
                    # Update status with current batch info
                    CurrentBatch = (BatchStart // BatchSize) + 1
                    TotalBatches = (TotalFiles + BatchSize - 1) // BatchSize
                    self.UpdateJobStatus('Running', Progress=25.0 + (65.0 * BatchStart / TotalFiles), 
                                       CurrentDirectory=f'Processing files {BatchStart+1}-{BatchEnd} of {TotalFiles} (Batch {CurrentBatch}/{TotalBatches})', 
                                       ScanResults=ScanResults)
                    
                    # Process this batch
                    self.FileScanningBusinessService.ProcessMediaFilesWithMetadata(BatchFiles, RootFolderId, self.RootFolderPath, ExtractMetadata=True)
                    
                    LoggingService.LogInfo(f"Processed batch {BatchStart+1}-{BatchEnd} of {TotalFiles} files", 'ScanDirectory', 'ScanDirectoryProcess')
                
                # Update scan results from business service
                ScanResults = self.FileScanningBusinessService.ScanResults
                
                LoggingService.LogInfo(f"Business service processing completed. Processed: {ScanResults.TotalFilesProcessed}, Errors: {ScanResults.TotalFilesWithErrors}", 'ScanDirectoryProcess', 'ScanDirectory')
                
            except Exception as e:
                LoggingService.LogException("Error during business service file processing", e, 'ScanDirectory', 'ScanDirectoryProcess')
                ScanResults.TotalFilesWithErrors += len(Files)
            
            # Check if scan was stopped during processing
            if not self.IsRunning:
                LoggingService.LogInfo(f"Scan process {self.ProcessId} stopped by signal", 'ScanDirectory', 'ScanDirectoryProcess')
                ScanResults.ScanStatus = 'Stopped'
                ScanResults.ScanEndTime = datetime.now()
                self.UpdateJobStatus('Stopped', Progress=100.0, ScanResults=ScanResults)
                return
            
            # Update root folder size with actual calculated size
            try:
                self.UpdateJobStatus('Running', Progress=90.0, CurrentDirectory='Calculating directory size...', ScanResults=ScanResults)
                LoggingService.LogInfo(f"Calculating actual directory size for {self.RootFolderPath}", 'ScanDirectory', 'ScanDirectoryProcess')
                TotalSizeGB = self.FileManagerService.CalculateDirectorySize(self.RootFolderPath)
                UpdateQuery = "UPDATE RootFolders SET TotalSizeGB = ?, LastScannedDate = ? WHERE Id = ?"
                self.DatabaseService.ExecuteNonQuery(UpdateQuery, (TotalSizeGB, datetime.now(), RootFolderId))
                LoggingService.LogInfo(f"Updated root folder size to {TotalSizeGB} GB", 'ScanDirectory', 'ScanDirectoryProcess')
            except Exception as e:
                LoggingService.LogException("Error updating root folder size", e, 'ScanDirectory', 'ScanDirectoryProcess')
            
            # Cleanup is now handled by ProcessMediaFilesWithMetadata in the business service
            
            # Mark as completed
            self.UpdateJobStatus('Running', Progress=95.0, CurrentDirectory='Finalizing scan...', ScanResults=ScanResults)
            ScanResults.ScanStatus = 'Completed'
            ScanResults.ScanEndTime = datetime.now()
            self.UpdateJobStatus('Completed', Progress=100.0, EndTime=datetime.now(), ScanResults=ScanResults)
            LoggingService.LogInfo(f"Scan process {self.ProcessId} completed successfully", 'ScanDirectory', 'ScanDirectoryProcess')
            
        except Exception as e:
            LoggingService.LogException(f"Error in scan process {self.ProcessId}", e, 'ScanDirectory', 'ScanDirectoryProcess')
            self.UpdateJobStatus('Failed', ErrorMessage=str(e), EndTime=datetime.now())
    
    def Run(self):
        """Main entry point for the scan process."""
        try:
            self.ScanDirectory()
        except Exception as e:
            LoggingService.LogException(f"Fatal error in scan process {self.ProcessId}", e, 'Run', 'ScanDirectoryProcess')
            self.UpdateJobStatus('Failed', ErrorMessage=f"Fatal error: {str(e)}", EndTime=datetime.now())
        finally:
            LoggingService.LogInfo(f"Scan process {self.ProcessId} exiting", 'Run', 'ScanDirectoryProcess')


def main():
    """Main function for the scan process."""
    try:
        if len(sys.argv) < 2:
            ErrorMsg = f"Usage: ScanDirectoryProcess.py <JobId> [Recursive]. Got {len(sys.argv)} args: {sys.argv}"
            LoggingService.LogError(ErrorMsg, 'main', 'ScanDirectoryProcess')
            sys.exit(1)
        
        JobId = sys.argv[1]
        Recursive = len(sys.argv) > 2 and sys.argv[2].lower() == 'true'
        
        # Get RootFolderPath from environment variable to preserve Unicode characters
        RootFolderPath = os.environ.get('MEDIAVORTEX_ROOT_FOLDER_PATH')
        if not RootFolderPath:
            ErrorMsg = "MEDIAVORTEX_ROOT_FOLDER_PATH environment variable not set"
            LoggingService.LogError(ErrorMsg, 'main', 'ScanDirectoryProcess')
            sys.exit(1)
        
        LoggingService.LogInfo(f"Starting scan process - JobId: {JobId}, Path: {RootFolderPath}, Recursive: {Recursive}", 'ScanDirectoryProcess', 'main')
        
        Scanner = ScanDirectoryProcess(JobId, RootFolderPath, Recursive)
        Scanner.Run()
        
        LoggingService.LogInfo(f"ScanDirectoryProcess completed successfully for job {JobId}", 'main', 'ScanDirectoryProcess')
        
    except Exception as e:
        ErrorMsg = f"Fatal error in scan process: {str(e)}"
        LoggingService.LogException("Fatal error in scan process", e, 'main', 'ScanDirectoryProcess')
        sys.exit(1)


if __name__ == "__main__":
    main()
