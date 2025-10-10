import os
import shutil
from typing import Dict, Any
from Services.LoggingService import LoggingService


class TranscodingFileManagerService:
    """Minimal file manager service for transcoding operations only."""
    
    def __init__(self):
        self.ProcessedFiles = 0
        self.SkippedFiles = 0
    
    def SetupTranscodingDirectories(self) -> bool:
        """Create transcoding directories if they don't exist."""
        try:
            LoggingService.LogFunctionEntry("SetupTranscodingDirectories", "TranscodingFileManagerService")
            
            # Create source directory
            SourceDir = "C:\\MediaVortex\\Source"
            if not os.path.exists(SourceDir):
                os.makedirs(SourceDir, exist_ok=True)
                LoggingService.LogInfo(f"Created source directory: {SourceDir}", "TranscodingFileManagerService", "SetupTranscodingDirectories")
            
            # Create output directory
            OutputDir = "C:\\MediaVortex"
            if not os.path.exists(OutputDir):
                os.makedirs(OutputDir, exist_ok=True)
                LoggingService.LogInfo(f"Created output directory: {OutputDir}", "TranscodingFileManagerService", "SetupTranscodingDirectories")
            
            LoggingService.LogInfo("Transcoding directories setup completed", "TranscodingFileManagerService", "SetupTranscodingDirectories")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception setting up transcoding directories", e, "TranscodingFileManagerService", "SetupTranscodingDirectories")
            return False
    
    def CopyFile(self, SourcePath: str, DestinationPath: str) -> bool:
        """Copy a file from source to destination."""
        try:
            LoggingService.LogFunctionEntry("CopyFile", "TranscodingFileManagerService", SourcePath, DestinationPath)
            
            # Check if file already exists at destination
            if os.path.exists(DestinationPath):
                LoggingService.LogInfo(f"File already exists at destination, skipping copy: {DestinationPath}", "TranscodingFileManagerService", "CopyFile")
                return True
            
            # Ensure destination directory exists
            DestinationDir = os.path.dirname(DestinationPath)
            if not os.path.exists(DestinationDir):
                os.makedirs(DestinationDir, exist_ok=True)
            
            # Copy the file
            shutil.copy2(SourcePath, DestinationPath)
            
            self.ProcessedFiles += 1
            LoggingService.LogInfo(f"Successfully copied file: {SourcePath} -> {DestinationPath}", "TranscodingFileManagerService", "CopyFile")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception copying file", e, "TranscodingFileManagerService", "CopyFile")
            return False
