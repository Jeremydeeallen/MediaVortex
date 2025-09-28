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
            self.RegisterServiceStatus()
            
            # Start processing threads
            self.StartProcessingThreads()
            
            # Mark as running
            self.IsRunning = True
            
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
    
    def RegisterServiceStatus(self):
        """Register service status in database."""
        try:
            serviceStatus = {
                'ServiceName': 'QualityCompareService',
                'Status': 'Starting',
                'HealthStatus': 'Healthy',
                'StartTime': self.StartTime,
                'LastHealthCheck': datetime.now(),
                'UptimeSeconds': 0,
                'MemoryUsage': psutil.Process().memory_info().rss / 1024 / 1024,  # MB
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': psutil.disk_usage('/').free / 1024 / 1024 / 1024,  # GB
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'ProcessId': self.ProcessId,
                'Version': '1.0.0',
                'ServiceType': 'QualityTesting'
            }
            
            self.DatabaseManager.SaveServiceStatus(serviceStatus)
            LoggingService.LogInfo("Service status registered", "QualityCompareService", "RegisterServiceStatus")
            
        except Exception as e:
            LoggingService.LogException("Exception registering service status", e, 
                                      "QualityCompareService", "RegisterServiceStatus")
    
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
        """Perform regular health checks."""
        try:
            LoggingService.LogInfo("Health check loop started", "QualityCompareService", "HealthCheckLoop")
            
            while not self.ShutdownEvent.is_set():
                try:
                    # Update service status
                    self.UpdateServiceStatus()
                    
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
    
    def UpdateServiceStatus(self):
        """Update service status in database."""
        try:
            uptime = (datetime.now() - self.StartTime).total_seconds()
            
            serviceStatus = {
                'ServiceName': 'QualityCompareService',
                'Status': 'Running' if self.IsRunning else 'Stopped',
                'HealthStatus': 'Healthy',
                'LastHealthCheck': datetime.now(),
                'UptimeSeconds': int(uptime),
                'MemoryUsage': psutil.Process().memory_info().rss / 1024 / 1024,  # MB
                'CPUUsage': psutil.Process().cpu_percent(),
                'DatabaseConnection': self.CheckDatabaseConnection(),
                'DiskSpace': psutil.disk_usage('/').free / 1024 / 1024 / 1024,  # GB
                'IsProcessing': self.IsRunning
            }
            
            self.DatabaseManager.UpdateServiceStatus('QualityCompareService', serviceStatus)
            
        except Exception as e:
            LoggingService.LogException("Exception updating service status", e, 
                                      "QualityCompareService", "UpdateServiceStatus")
    
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
            
            # Update service status
            self.UpdateServiceStatus()
            
            LoggingService.LogInfo("QualityCompareService shutdown initiated", "QualityCompareService", "Shutdown")
            
        except Exception as e:
            LoggingService.LogException("Exception during shutdown", e, 
                                      "QualityCompareService", "Shutdown")
    
    def Cleanup(self):
        """Cleanup resources."""
        try:
            LoggingService.LogInfo("Cleaning up QualityCompareService resources", "QualityCompareService", "Cleanup")
            
            # Update final status
            self.DatabaseManager.UpdateServiceStatus('QualityCompareService', {
                'Status': 'Stopped',
                'HealthStatus': 'Stopped'
            })
            
            LoggingService.LogInfo("QualityCompareService cleanup complete", "QualityCompareService", "Cleanup")
            
        except Exception as e:
            LoggingService.LogException("Exception during cleanup", e, 
                                      "QualityCompareService", "Cleanup")
