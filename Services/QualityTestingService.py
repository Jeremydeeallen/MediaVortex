#!/usr/bin/env python3
"""
Quality Testing Service
MicroService entry point for quality testing using MVVM architecture
"""

import sys
import os
import time
import threading
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ViewModels.QualityTestingViewModel import QualityTestingViewModel
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.DatabaseCleanupService import DatabaseCleanupService


class QualityTestingService:
    """Quality Testing MicroService - Database-driven MVVM architecture."""
    
    def __init__(self):
        """Initialize the quality testing service."""
        self.IsProcessing = False
        self.StopRequested = False
        self.ViewModel = None
        self.ProcessingThread = None
        
        # LoggingService.LogInfo("QualityTestingService initialized", "QualityTestingService", "__init__")
    
    def Initialize(self) -> bool:
        """Initialize the service with dependencies."""
        try:
            # Initialize dependencies
            database_manager = DatabaseManager()
            
            # Clean up any orphaned state from previous runs
            cleanup_service = DatabaseCleanupService(database_manager)
            cleanup_result = cleanup_service.CleanupMicroserviceState("QualityTestingService")
            LoggingService.LogInfo(f"Startup cleanup result: {cleanup_result}", "QualityTestingService", "Initialize")
            
            # Initialize ViewModel
            self.ViewModel = QualityTestingViewModel(
                DatabaseManagerInstance=database_manager
            )
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error initializing QualityTestingService", e, "QualityTestingService", "Initialize")
            return False
    
    def Run(self) -> bool:
        """Main entry point for the microservice."""
        try:
            LoggingService.LogInfo("Starting QualityTestingService", "QualityTestingService", "Run")
            
            # Initialize
            if not self.Initialize():
                LoggingService.LogError("Failed to initialize QualityTestingService", "QualityTestingService", "Run")
                return False
            
            # Start processing
            if not self.StartProcessing():
                LoggingService.LogError("Failed to start quality testing processing", "QualityTestingService", "Run")
                return False
            
            # Keep running until shutdown
            while not self.StopRequested:
                time.sleep(1)
            
            # Shutdown
            self.Shutdown()
            
            LoggingService.LogInfo("QualityTestingService completed", "QualityTestingService", "Run")
            return True
            
        except Exception as e:
            LoggingService.LogException("Fatal error in QualityTestingService", e, "QualityTestingService", "Run")
            return False
    
    def StartProcessing(self) -> bool:
        """Start the quality testing processing loop."""
        try:
            if not self.ViewModel:
                LoggingService.LogError("ViewModel not initialized", "QualityTestingService", "StartProcessing")
                return False
            
            # Start processing thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting quality testing processing", e, "QualityTestingService", "StartProcessing")
            return False
    
    def ProcessQueueLoop(self):
        """Main processing loop that checks ServiceStatus and processes queue."""
        try:
            while not self.StopRequested:
                try:
                    # Check ServiceStatus to see if we should run
                    service_status = self.ViewModel.CheckServiceStatus()
                    
                    if service_status and service_status.get('Status') == 'Running':
                        # Process the queue
                        result = self.ViewModel.ProcessQueue()
                    else:
                        status = service_status.get('Status') if service_status else 'Unknown'
                        print(f"QualityTestingService Status = {status} Waiting for it to start")
                    
                    # Wait before next iteration
                    time.sleep(10)
                    
                except Exception as e:
                    LoggingService.LogException("Error in processing loop iteration", e, "QualityTestingService", "ProcessQueueLoop")
                    time.sleep(30)  # Wait longer on error
            
        except Exception as e:
            LoggingService.LogException("Fatal error in processing loop", e, "QualityTestingService", "ProcessQueueLoop")
    
    def Shutdown(self) -> bool:
        """Graceful shutdown of the service."""
        try:
            LoggingService.LogInfo("Initiating QualityTestingService shutdown", "QualityTestingService", "Shutdown")
            
            # Just set the stop flag - the worker will handle the rest
            self.StopRequested = True
            
            LoggingService.LogInfo("QualityTestingService shutdown completed", "QualityTestingService", "Shutdown")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "QualityTestingService", "Shutdown")
            return False


def main():
    """Main entry point for standalone execution."""
    try:
        service = QualityTestingService()
        success = service.Run()
        
        if success:
            print("QualityTestingService completed successfully")
            sys.exit(0)
        else:
            print("QualityTestingService failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"Fatal error in QualityTestingService: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
