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
from typing import Dict, Any

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService
from Services.FileManagerService import FileManagerService
from Services.LoggingService import LoggingService

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
                       ErrorMessage: str = None, **Stats):
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
            
            # Add any additional stats
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
            
            # Initialize stats
            Stats = {
                'TotalFiles': 0,
                'ProcessedFiles': 0,
                'SkippedFiles': 0,
                'EncodingErrors': 0,
                'NewFiles': 0,
                'UpdatedFiles': 0,
                'DeletedFiles': 0
            }
            
            # Scan directory
            LoggingService.LogInfo(f"Scanning directory: {self.RootFolderPath}", 'ScanDirectoryProcess', 'ScanDirectory')
            Files = self.FileManagerService.ScanDirectory(self.RootFolderPath, self.Recursive)
            
            if not Files:
                LoggingService.LogWarning(f"No files found in {self.RootFolderPath}", 'ScanDirectoryProcess', 'ScanDirectory')
                self.UpdateJobStatus('Completed', Progress=100.0, **Stats)
                return
            
            Stats['TotalFiles'] = len(Files)
            self.UpdateJobStatus('Running', **Stats)
            
            # Process each file
            for Index, FilePath in enumerate(Files):
                if not self.IsRunning:
                    LoggingService.LogInfo(f"Scan process {self.ProcessId} stopped by signal", 'ScanDirectoryProcess', 'ScanDirectory')
                    self.UpdateJobStatus('Stopped', Progress=(Index / len(Files)) * 100, **Stats)
                    return
                
                try:
                    # Update current directory
                    CurrentDir = os.path.dirname(FilePath)
                    Progress = (Index / len(Files)) * 100
                    
                    self.UpdateJobStatus('Running', Progress=Progress, CurrentDirectory=CurrentDir, **Stats)
                    
                    # Process the file
                    FileStats = self.ProcessFile(FilePath, RootFolderId)
                    
                    # Update stats
                    for Key, Value in FileStats.items():
                        Stats[Key] += Value
                    Stats['ProcessedFiles'] += 1
                    
                    # Update database every 10 files
                    if Index % 10 == 0:
                        self.UpdateJobStatus('Running', Progress=Progress, **Stats)
                    
                except Exception as e:
                    LoggingService.LogException(f"Error processing file {FilePath}", e, 'ScanDirectoryProcess', 'ProcessFile')
                    Stats['EncodingErrors'] += 1
            
            # Update root folder size
            try:
                TotalSizeGB = sum(Stats[key] for key in ['NewFiles', 'UpdatedFiles']) * 0.001  # Rough estimate
                UpdateQuery = "UPDATE RootFolders SET TotalSizeGB = ?, LastScannedDate = ? WHERE Id = ?"
                self.DatabaseService.ExecuteNonQuery(UpdateQuery, (TotalSizeGB, datetime.now(), RootFolderId))
            except Exception as e:
                LoggingService.LogException("Error updating root folder size", e, 'ScanDirectoryProcess', 'ScanDirectory')
            
            # Mark as completed
            self.UpdateJobStatus('Completed', Progress=100.0, EndTime=datetime.now(), **Stats)
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
