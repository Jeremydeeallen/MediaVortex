#!/usr/bin/env python3
"""
Quality Testing MicroService
Standalone microservice for quality testing using VMAF analysis
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

from ViewModels.QualityTestingViewModel import QualityTestingViewModel
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.DatabaseCleanupService import DatabaseCleanupService


class QualityTestingService:
    """Quality Testing MicroService - Self-contained with worker management."""
    
    def __init__(self):
        """Initialize the quality testing service."""
        self.IsProcessing = False
        self.StopRequested = False
        self.ShutdownRequested = False
        self.ViewModel = None
        self.ProcessingThread = None
        self.WorkerThreads = []
        self.MaxConcurrentJobs = 1
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.PrivateSignalHandler)
        signal.signal(signal.SIGTERM, self.PrivateSignalHandler)
        
        LoggingService.LogInfo("QualityTestingService initialized", "QualityTestingService", "__init__")
    
    def PrivateSignalHandler(self, signum, frame):
        """Handle shutdown signals."""
        LoggingService.LogInfo(f"Received signal {signum}, initiating shutdown", "QualityTestingService", "PrivateSignalHandler")
        self.ShutdownRequested = True
        self.StopRequested = True
    
    def Initialize(self) -> bool:
        """Initialize the service with dependencies."""
        try:
            # Initialize dependencies
            database_manager = DatabaseManager()
            
            # Enhanced crash recovery using CrashRecoveryService
            from Services.CrashRecoveryService import CrashRecoveryService
            recovery_service = CrashRecoveryService(database_manager)
            recovery_result = recovery_service.RecoverServiceJobs("QualityTestingService")
            LoggingService.LogInfo(f"Crash recovery result: {recovery_result}", "QualityTestingService", "Initialize")
            
            # Also run the existing cleanup for any additional cleanup needed
            cleanup_service = DatabaseCleanupService(database_manager)
            cleanup_result = cleanup_service.CleanupMicroserviceState("QualityTestingService")
            LoggingService.LogInfo(f"Additional cleanup result: {cleanup_result}", "QualityTestingService", "Initialize")
            
            # Initialize ViewModel
            self.ViewModel = QualityTestingViewModel(
                DatabaseManagerInstance=database_manager
            )
            
            # NEW: Check for missed quality tests
            self.RecoverMissedQualityTests()
            
            # Read MaxConcurrentJobs from settings
            self.LoadConfiguration()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error initializing QualityTestingService", e, "QualityTestingService", "Initialize")
            return False
    
    def LoadConfiguration(self):
        """Load configuration from database settings."""
        try:
            if self.ViewModel and self.ViewModel.DatabaseManager:
                # Get MaxConcurrentJobs from SystemSettings
                query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'MaxConcurrentJobs'"
                rows = self.ViewModel.DatabaseManager.DatabaseService.ExecuteQuery(query)
                
                if rows and rows[0]['SettingValue']:
                    self.MaxConcurrentJobs = int(rows[0]['SettingValue'])
                    LoggingService.LogInfo(f"Loaded MaxConcurrentJobs: {self.MaxConcurrentJobs}", "QualityTestingService", "LoadConfiguration")
                else:
                    LoggingService.LogWarning("MaxConcurrentJobs not found in settings, using default: 1", "QualityTestingService", "LoadConfiguration")
                    self.MaxConcurrentJobs = 1
        except Exception as e:
            LoggingService.LogException("Error loading configuration", e, "QualityTestingService", "LoadConfiguration")
            self.MaxConcurrentJobs = 1
    
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
            while not self.ShutdownRequested:
                time.sleep(1)
            
            # Shutdown
            self.Shutdown()
            
            LoggingService.LogInfo("QualityTestingService completed", "QualityTestingService", "Run")
            return True
            
        except Exception as e:
            LoggingService.LogException("Fatal error in QualityTestingService", e, "QualityTestingService", "Run")
            return False
    
    def StartProcessing(self) -> bool:
        """Start the quality testing processing with multiple worker threads."""
        try:
            if not self.ViewModel:
                LoggingService.LogError("ViewModel not initialized", "QualityTestingService", "StartProcessing")
                return False
            
            # Create worker threads based on MaxConcurrentJobs
            for i in range(self.MaxConcurrentJobs):
                worker_thread = threading.Thread(
                    target=self.WorkerLoop, 
                    args=(i,), 
                    daemon=True,
                    name=f"QualityTestWorker-{i}"
                )
                worker_thread.start()
                self.WorkerThreads.append(worker_thread)
                LoggingService.LogInfo(f"Started worker thread {i}", "QualityTestingService", "StartProcessing")
            
            LoggingService.LogInfo(f"Started QualityTestingService with {self.MaxConcurrentJobs} worker threads", "QualityTestingService", "StartProcessing")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting quality testing processing", e, "QualityTestingService", "StartProcessing")
            return False
    
    def WorkerLoop(self, worker_id: int):
        """Individual worker thread loop that claims and processes jobs."""
        try:
            LoggingService.LogInfo(f"Worker {worker_id} started", "QualityTestingService", "WorkerLoop")
            
            while not self.StopRequested:
                try:
                    # Try to claim a job atomically
                    job = self.ViewModel.ClaimJob()
                    
                    if job:
                        LoggingService.LogInfo(f"Worker {worker_id} claimed job {job['Id']}", "QualityTestingService", "WorkerLoop")
                        
                        # Process the claimed job
                        result = self.ViewModel.ProcessJob(job)
                        
                        if result.get('Success'):
                            LoggingService.LogInfo(f"Worker {worker_id} completed job {job['Id']} with VMAF score {result.get('VMAFScore', 'N/A')}", "QualityTestingService", "WorkerLoop")
                        else:
                            LoggingService.LogError(f"Worker {worker_id} failed job {job['Id']}: {result.get('Message', 'Unknown error')}", "QualityTestingService", "WorkerLoop")
                    else:
                        # No jobs available, wait a bit
                        time.sleep(5)
                    
                except Exception as e:
                    LoggingService.LogException(f"Error in worker {worker_id} loop iteration", e, "QualityTestingService", "WorkerLoop")
                    time.sleep(5)  # Wait on error
            
            LoggingService.LogInfo(f"Worker {worker_id} stopped", "QualityTestingService", "WorkerLoop")
            
        except Exception as e:
            LoggingService.LogException(f"Fatal error in worker {worker_id} loop", e, "QualityTestingService", "WorkerLoop")
    
    def Shutdown(self) -> bool:
        """Graceful shutdown of the service."""
        try:
            LoggingService.LogInfo("Initiating QualityTestingService shutdown", "QualityTestingService", "Shutdown")
            
            # Set stop flags
            self.StopRequested = True
            self.ShutdownRequested = True
            
            # Terminate any active FFmpeg processes
            if (self.ViewModel and 
                self.ViewModel.QualityTestingBusinessService):
                self.ViewModel.QualityTestingBusinessService.TerminateActiveFFmpegProcess()
            
            # Wait for all worker threads to finish
            for i, worker_thread in enumerate(self.WorkerThreads):
                if worker_thread.is_alive():
                    LoggingService.LogInfo(f"Waiting for worker thread {i} to finish", "QualityTestingService", "Shutdown")
                    worker_thread.join(timeout=10)
            
            LoggingService.LogInfo("QualityTestingService shutdown completed", "QualityTestingService", "Shutdown")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "QualityTestingService", "Shutdown")
            return False
    
    def RecoverMissedQualityTests(self):
        """Find successful transcodes that need quality testing but aren't in the queue."""
        try:
            LoggingService.LogInfo("Checking for missed quality tests...", 
                                  "QualityTestingService", "RecoverMissedQualityTests")
            
            # Get successful transcode attempts that need quality testing
            # but don't have a successful quality test result record
            MissedTests = self.ViewModel.DatabaseManager.GetMissedQualityTests(100)
            
            if MissedTests:
                LoggingService.LogInfo(f"Found {len(MissedTests)} missed quality tests, queueing them...", 
                                      "QualityTestingService", "RecoverMissedQualityTests")
                
                for Test in MissedTests:
                    # Parse FFmpeg command to get file paths
                    InputFilePath, OutputFilePath = self.ViewModel.DatabaseManager.ParseFFmpegCommand(
                        Test['FfpmpegCommand']
                    )
                    
                    if InputFilePath and OutputFilePath:
                        # Check if files still exist
                        import os
                        if os.path.exists(InputFilePath) and os.path.exists(OutputFilePath):
                            # Create quality test queue entry
                            JobId = self.ViewModel.DatabaseManager.CreateQualityTestQueueEntry(
                                Test['Id'],
                                Test['FilePath'],
                                InputFilePath,
                                OutputFilePath
                            )
                            
                            if JobId:
                                LoggingService.LogInfo(f"Queued missed quality test for attempt {Test['Id']}", 
                                                      "QualityTestingService", "RecoverMissedQualityTests")
                        else:
                            LoggingService.LogWarning(f"Files no longer exist for attempt {Test['Id']}, skipping", 
                                                     "QualityTestingService", "RecoverMissedQualityTests")
            else:
                LoggingService.LogInfo("No missed quality tests found", 
                                      "QualityTestingService", "RecoverMissedQualityTests")
                                      
        except Exception as e:
            LoggingService.LogException("Error recovering missed quality tests", e, 
                                       "QualityTestingService", "RecoverMissedQualityTests")


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
