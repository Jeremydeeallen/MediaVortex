"""
QualityCompareService Application Logic
Handles quality testing queue processing and service orchestration.
"""

import sys
import os
import time
import threading
import psutil
from typing import Dict, Any, Optional
from datetime import datetime

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.QualityTestingOrchestratorService import QualityTestingOrchestratorService
from Services.QualityTestingStrategyService import QualityTestingStrategyService
from Services.LoggingService import LoggingService
from Services.ServiceCommandService import ServiceCommandService
from Repositories.DatabaseManager import DatabaseManager
# Using uniform pattern like TranscodeService - no separate HealthMonitor needed


class QualityCompareServiceApp:
    """Main application class for QualityCompareService."""
    
    def __init__(self):
        """Initialize the QualityCompareService application."""
        self.DatabaseManager = DatabaseManager()
        self.OrchestratorService = QualityTestingOrchestratorService(self.DatabaseManager)
        self.StrategyService = QualityTestingStrategyService(self.DatabaseManager)
        self.CommandService = ServiceCommandService(DatabaseManagerInstance=self.DatabaseManager)
        self.IsRunning = False
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.CommandProcessingThread = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        
        LoggingService.LogInfo("QualityCompareServiceApp initialized", "QualityCompareService", "__init__")
    
    def Run(self):
        """Start the quality comparison service."""
        try:
            LoggingService.LogInfo("Starting QualityCompareService...", "QualityCompareService", "Run")
            
            # Check database connection
            if not self.CheckDatabaseConnection():
                LoggingService.LogError("Database connection failed, exiting...", "QualityCompareService", "Run")
                return False
            
            # Register service status
            self.UpdateServiceStatus("Starting")
            
            # Start processing threads
            self.StartProcessingThreads()
            
            # Start health check thread - same pattern as TranscodeService
            self.HealthCheckThread = threading.Thread(target=self.HealthCheckLoop, daemon=True)
            self.HealthCheckThread.start()
            
            # Mark as running
            self.IsRunning = True
            self.UpdateServiceStatus("Running")
            
            LoggingService.LogInfo("QualityCompareService started successfully", "QualityCompareService", "Run")
            
            # Main processing loop
            self.MainProcessingLoop()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception starting QualityCompareService", e, 
                                      "QualityCompareService", "Run")
            return False
    
    def CheckDatabaseConnection(self) -> bool:
        """Check if database connection is available."""
        try:
            # Test database connection
            testResult = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT 1")
            if testResult:
                LoggingService.LogInfo("Database connection successful", "QualityCompareService", "CheckDatabaseConnection")
                return True
            else:
                LoggingService.LogError("Database connection test failed", "QualityCompareService", "CheckDatabaseConnection")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception checking database connection", e, 
                                      "QualityCompareService", "CheckDatabaseConnection")
            return False
    
    # RegisterServiceStatus method removed - using uniform UpdateServiceStatus pattern
    
    def StartProcessingThreads(self):
        """Start background processing threads."""
        try:
            # Start quality testing processing thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQualityTestingQueue, daemon=True)
            self.ProcessingThread.start()
            
            # Start health check thread
            self.HealthCheckThread = threading.Thread(target=self.HealthCheckLoop, daemon=True)
            self.HealthCheckThread.start()
            
            # Start command processing thread
            self.CommandProcessingThread = threading.Thread(target=self.ProcessCommands, daemon=True)
            self.CommandProcessingThread.start()
            
            LoggingService.LogInfo("Processing threads started", "QualityCompareService", "StartProcessingThreads")
            
        except Exception as e:
            LoggingService.LogException("Exception starting processing threads", e, 
                                      "QualityCompareService", "StartProcessingThreads")
    
    def ProcessQualityTestingQueue(self):
        """Process quality testing queue items."""
        try:
            LoggingService.LogInfo("Quality testing queue processor started", "QualityCompareService", "ProcessQualityTestingQueue")
            
            while not self.ShutdownEvent.is_set():
                try:
                    # Get next pending quality test
                    qualityTest = self.DatabaseManager.GetNextPendingQualityTest()
                    
                    if qualityTest:
                        LoggingService.LogInfo(f"Processing quality test {qualityTest.Id}", 
                                             "QualityCompareService", "ProcessQualityTestingQueue")
                        
                        # Process the quality test
                        result = self.OrchestratorService.ProcessQualityTestingRequest(qualityTest)
                        
                        if result.get("Success", False):
                            LoggingService.LogInfo(f"Quality test {qualityTest.Id} completed successfully", 
                                                 "QualityCompareService", "ProcessQualityTestingQueue")
                        else:
                            LoggingService.LogError(f"Quality test {qualityTest.Id} failed: {result.get('ErrorMessage', 'Unknown error')}", 
                                                  "QualityCompareService", "ProcessQualityTestingQueue")
                    else:
                        # No pending tests, wait a bit
                        time.sleep(5)
                        
                except Exception as e:
                    LoggingService.LogException("Exception processing quality test", e, 
                                              "QualityCompareService", "ProcessQualityTestingQueue")
                    time.sleep(10)  # Wait before retrying
                    
        except Exception as e:
            LoggingService.LogException("Exception in quality testing queue processor", e, 
                                      "QualityCompareService", "ProcessQualityTestingQueue")
    
    def HealthCheckLoop(self):
        """Perform regular health checks - same pattern as TranscodeService."""
        try:
            LoggingService.LogInfo("Health check loop started", "QualityCompareService", "HealthCheckLoop")
            
            while not self.ShutdownEvent.is_set():
                try:
                    # Update service status
                    self.UpdateServiceStatus("Running", "Healthy")
                    
                    # Wait before next health check
                    time.sleep(30)  # Check every 30 seconds
                    
                except Exception as e:
                    LoggingService.LogException("Exception in health check", e, 
                                              "QualityCompareService", "HealthCheckLoop")
                    time.sleep(30)
                    
        except Exception as e:
            LoggingService.LogException("Exception in health check loop", e, 
                                      "QualityCompareService", "HealthCheckLoop")
    
    def ProcessCommands(self):
        """Process service commands from database."""
        try:
            LoggingService.LogInfo("Command processor started", "QualityCompareService", "ProcessCommands")
            
            while not self.ShutdownEvent.is_set():
                try:
                    # Get pending commands for this service
                    commands = self.DatabaseManager.GetPendingCommandsForService('QualityCompareService')
                    
                    for command in commands:
                        try:
                            # Process command
                            result = self.CommandService.ProcessCommand(command)
                            
                            if result.get("Success", False):
                                LoggingService.LogInfo(f"Command {command['Id']} processed successfully", 
                                                     "QualityCompareService", "ProcessCommands")
                            else:
                                LoggingService.LogError(f"Command {command['Id']} failed: {result.get('ErrorMessage', 'Unknown error')}", 
                                                      "QualityCompareService", "ProcessCommands")
                                
                        except Exception as e:
                            LoggingService.LogException(f"Exception processing command {command['Id']}", e, 
                                                      "QualityCompareService", "ProcessCommands")
                    
                    # Wait before checking for more commands
                    time.sleep(5)
                    
                except Exception as e:
                    LoggingService.LogException("Exception in command processor", e, 
                                              "QualityCompareService", "ProcessCommands")
                    time.sleep(10)
                    
        except Exception as e:
            LoggingService.LogException("Exception in command processor loop", e, 
                                      "QualityCompareService", "ProcessCommands")
    
    def UpdateServiceStatus(self, status: str = "Running", health_status: str = "Healthy", 
                              active_jobs: int = 0, is_processing: bool = False, 
                              error_message: str = None):
        """Update service status in ServiceStatus table - same pattern as TranscodeService."""
        try:
            # Calculate uptime
            uptime_seconds = int((datetime.now() - self.StartTime).total_seconds())
            
            # Get system metrics
            memory_usage = self.GetMemoryUsage()
            cpu_usage = self.GetCPUUsage()
            disk_space = self.GetDiskSpace()
            
            # Check database connection
            database_connection = self.CheckDatabaseConnection()
            
            # Insert or update service status - same pattern as TranscodeService
            query = """
            INSERT OR REPLACE INTO ServiceStatus (
                ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
                UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
                ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, LastErrorMessage,
                ProcessId, Version, ServiceType, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            now = datetime.now()
            params = (
                "QualityCompareService",  # ServiceName
                status,                   # Status
                health_status,            # HealthStatus
                self.StartTime,           # StartTime
                now,                      # LastHealthCheck
                uptime_seconds,           # UptimeSeconds
                memory_usage,             # MemoryUsage
                cpu_usage,                # CPUUsage
                database_connection,      # DatabaseConnection
                disk_space,               # DiskSpace
                0,                        # ErrorCount
                10,                       # MaxErrors
                active_jobs,              # ActiveJobsCount
                is_processing,            # IsProcessing
                error_message,            # LastErrorMessage
                self.ProcessId,           # ProcessId
                "1.0.0",                 # Version
                "QualityTesting",        # ServiceType
                now,                     # CreatedAt
                now                      # UpdatedAt
            )
            
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, params)
            LoggingService.LogDebug(f"Service status updated: {status}", "QualityCompareService", "UpdateServiceStatus")
            
        except Exception as e:
            LoggingService.LogException("Error updating service status", e, "QualityCompareService", "UpdateServiceStatus")
    
    def GetMemoryUsage(self) -> float:
        """Get current memory usage in MB."""
        try:
            return psutil.Process().memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def GetCPUUsage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return psutil.Process().cpu_percent()
        except Exception:
            return 0.0
    
    def GetDiskSpace(self) -> float:
        """Get available disk space in GB."""
        try:
            return psutil.disk_usage('/').free / 1024 / 1024 / 1024
        except Exception:
            return 0.0
    
    def MainProcessingLoop(self):
        """Main processing loop."""
        try:
            LoggingService.LogInfo("Entering main processing loop", "QualityCompareService", "MainProcessingLoop")
            
            while not self.ShutdownEvent.is_set():
                time.sleep(1)  # Main loop just waits for shutdown
                
        except Exception as e:
            LoggingService.LogException("Exception in main processing loop", e, 
                                      "QualityCompareService", "MainProcessingLoop")
    
    def Shutdown(self):
        """Shutdown the service gracefully."""
        try:
            LoggingService.LogInfo("Initiating QualityCompareService shutdown", "QualityCompareService", "Shutdown")
            
            self.IsRunning = False
            self.ShutdownEvent.set()
            
            # Stop health check thread
            if self.HealthCheckThread and self.HealthCheckThread.is_alive():
                self.HealthCheckThread.join(timeout=5)
            
            # Update service status
            self.UpdateServiceStatus("Stopping")
            
            LoggingService.LogInfo("QualityCompareService shutdown initiated", "QualityCompareService", "Shutdown")
            
        except Exception as e:
            LoggingService.LogException("Exception during shutdown", e, 
                                      "QualityCompareService", "Shutdown")
    
    def Cleanup(self):
        """Cleanup resources."""
        try:
            LoggingService.LogInfo("Cleaning up QualityCompareService resources", "QualityCompareService", "Cleanup")
            
            # Update final status
            self.UpdateServiceStatus("Stopped", "Stopped")
            
            LoggingService.LogInfo("QualityCompareService cleanup complete", "QualityCompareService", "Cleanup")
            
        except Exception as e:
            LoggingService.LogException("Exception during cleanup", e, 
                                      "QualityCompareService", "Cleanup")
