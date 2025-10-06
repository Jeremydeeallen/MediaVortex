#!/usr/bin/env python3
"""
Quality Test Worker
Standalone worker script for quality testing using MVVM architecture
"""

import sys
import os
import time
import signal
import threading
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.QualityTestingService import QualityTestingService
from Services.LoggingService import LoggingService


class QualityTestWorker:
    """Quality Test Worker using MVVM architecture."""
    
    def __init__(self):
        """Initialize the quality test worker."""
        self.ShutdownRequested = False
        self.QualityTestingService = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.PrivateSignalHandler)
        signal.signal(signal.SIGTERM, self.PrivateSignalHandler)
        
        # LoggingService.LogInfo("QualityTestWorker initialized", "QualityTestWorker", "__init__")
    
    def PrivateSignalHandler(self, signum, frame):
        """Handle shutdown signals."""
        LoggingService.LogInfo(f"Received signal {signum}, initiating shutdown", "QualityTestWorker", "PrivateSignalHandler")
        self.ShutdownRequested = True
        # Set MicroServiceStatus to 0 when process is terminated
        self.SetMicroServiceStatus(0)
    
    def Initialize(self) -> bool:
        """Initialize the worker with dependencies."""
        try:
            # Initialize the QualityTestingService
            self.QualityTestingService = QualityTestingService()
            
            # Initialize the service
            if not self.QualityTestingService.Initialize():
                LoggingService.LogError("Failed to initialize QualityTestingService", "QualityTestWorker", "Initialize")
                return False
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error initializing QualityTestWorker", e, "QualityTestWorker", "Initialize")
            return False
    
    def StartProcessing(self) -> bool:
        """Start the quality testing processing loop."""
        try:
            if not self.QualityTestingService:
                LoggingService.LogError("QualityTestingService not initialized", "QualityTestWorker", "StartProcessing")
                return False
            
            # Start the service
            self.QualityTestingService.StartProcessing()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting quality testing processing", e, "QualityTestWorker", "StartProcessing")
            return False
    
    
    def Shutdown(self) -> bool:
        """Graceful shutdown of the worker."""
        try:
            LoggingService.LogInfo("Initiating QualityTestWorker shutdown", "QualityTestWorker", "Shutdown")
            
            # Step 1: Set shutdown flag
            self.ShutdownRequested = True
            
            # Step 2: Stop the service processing loop
            if self.QualityTestingService:
                self.QualityTestingService.StopRequested = True
            
            # Step 3: Terminate any active FFmpeg processes
            if (self.QualityTestingService and 
                self.QualityTestingService.ViewModel and 
                self.QualityTestingService.ViewModel.QualityTestingBusinessService):
                self.QualityTestingService.ViewModel.QualityTestingBusinessService.TerminateActiveFFmpegProcess()
            
            # Step 4: Wait for processing thread to finish
            if (self.QualityTestingService and 
                self.QualityTestingService.ProcessingThread and 
                self.QualityTestingService.ProcessingThread.is_alive()):
                LoggingService.LogInfo("Waiting for processing thread to finish", "QualityTestWorker", "Shutdown")
                self.QualityTestingService.ProcessingThread.join(timeout=10)
            
            # Step 5: Set MicroServiceStatus to 0 (stopped)
            self.SetMicroServiceStatus(0)
            
            LoggingService.LogInfo("QualityTestWorker shutdown completed", "QualityTestWorker", "Shutdown")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "QualityTestWorker", "Shutdown")
            return False
    
    def SetMicroServiceStatus(self, status: int) -> bool:
        """Set the MicroServiceStatus in the database."""
        try:
            if self.QualityTestingService and self.QualityTestingService.ViewModel:
                # Update MicroServiceStatus in ServiceStatus table
                query = "UPDATE ServiceStatus SET MicroServiceStatus = ? WHERE ServiceName = ?"
                rows_affected = self.QualityTestingService.ViewModel.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    query, (status, 'QualityTestingService')
                )
                return rows_affected > 0
            return False
        except Exception as e:
            LoggingService.LogException("Error setting microservice status", e, "QualityTestWorker", "SetMicroServiceStatus")
            return False
    
    def Run(self) -> bool:
        """Main entry point for the worker."""
        try:
            print("======QualityTestWorker Started======")
            
            # Set MicroServiceStatus to 1 (running)
            self.SetMicroServiceStatus(1)
            
            # Initialize
            if not self.Initialize():
                LoggingService.LogError("Failed to initialize QualityTestWorker", "QualityTestWorker", "Run")
                self.SetMicroServiceStatus(0)  # Set to 0 on failure
                return False
            
            # Start processing
            if not self.StartProcessing():
                LoggingService.LogError("Failed to start quality testing processing", "QualityTestWorker", "Run")
                self.SetMicroServiceStatus(0)  # Set to 0 on failure
                return False
            
            # Keep running until shutdown
            while not self.ShutdownRequested:
                time.sleep(1)
            
            # Shutdown
            self.Shutdown()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Fatal error in QualityTestWorker", e, "QualityTestWorker", "Run")
            self.SetMicroServiceStatus(0)  # Set to 0 on error
            return False


def main():
    """Main entry point."""
    try:
        worker = QualityTestWorker()
        success = worker.Run()
        
        if success:
            print("QualityTestWorker completed successfully")
            sys.exit(0)
        else:
            print("QualityTestWorker failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"Fatal error in QualityTestWorker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()