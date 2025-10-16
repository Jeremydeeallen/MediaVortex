#!/usr/bin/env python3
"""
QualityTestService Entry Point
Standalone quality testing microservice for MediaVortex
"""

import sys
import signal
import os
import setproctitle
import time
import threading
import psutil
from datetime import datetime

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("QualityTestService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Services.ProcessQualityTestQueueService import ProcessQualityTestQueueService

class QualityTestServiceApp:
    """Main application class for QualityTestService."""
    
    def __init__(self):
        """Initialize the QualityTestService application."""
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            LoggingService.LogError("QualityTestService is already running. Preventing duplicate instance.", "QualityTestServiceApp", "__init__")
            sys.exit(1)
        
        self.DatabaseManager = DatabaseManager()
        self.ProcessQualityTestQueue = ProcessQualityTestQueueService(
            DatabaseManagerInstance=self.DatabaseManager
        )
        self.IsRunning = False
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.StatusPollingThread = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        self.CurrentStatus = "Stopped"
        
        LoggingService.LogInfo("QualityTestServiceApp initialized", "QualityTestService", "__init__")
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another QualityTestService instance is already running using ServiceStatusService."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            return status_service.RegisterServiceStartup("QualityTestService", MaxConcurrentJobs=1)
        except Exception as e:
            LoggingService.LogException("Exception checking for existing QualityTestService instances", e, "QualityTestServiceApp", "PrivateIsServiceAlreadyRunning")
            return True  # Prevent startup on error
    
    def EnsureServiceStatusExists(self):
        """Ensure ServiceStatus record exists for QualityTestService, create if missing."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            result = status_service.EnsureServiceStatusExists("QualityTestService", MaxConcurrentJobs=1)
            
            if result:
                LoggingService.LogInfo("ServiceStatus record ensured for QualityTestService", "QualityTestService", "EnsureServiceStatusExists")
            else:
                LoggingService.LogError("Failed to ensure ServiceStatus record for QualityTestService", "QualityTestService", "EnsureServiceStatusExists")
                
        except Exception as e:
            LoggingService.LogException("Error ensuring ServiceStatus exists", e, "QualityTestService", "EnsureServiceStatusExists")
    
    def Run(self):
        """Start the quality test service."""
        try:
            LoggingService.LogInfo("Starting QualityTestService...", "QualityTestService", "run")
            
            # Ensure service status record exists
            self.EnsureServiceStatusExists()
            
            # Update service status in database
            self.UpdateServiceStatus("Starting")
            
            # Start health monitoring
            self.StartHealthMonitoring()
            
            # Start status polling
            self.PrivateStartStatusPolling()
            
            # Start quality test processing
            self.StartQualityTestProcessing()
            
            # Update service status to Running immediately after startup
            self.UpdateServiceStatus("Running", "Healthy", 0, False)
            
            # Main processing loop
            self.MainLoop()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting QualityTestService", e, "QualityTestService", "run")
            return False
    
    def UpdateServiceStatus(self, status, health="Healthy", active_jobs=0, is_processing=False, last_error=None):
        """Update service status in database."""
        try:
            self.DatabaseManager.UpdateServiceStatus("QualityTestService", {
                'Status': status,
                'HealthStatus': health,
                'ActiveJobsCount': active_jobs,
                'IsProcessing': is_processing,
                'LastErrorMessage': last_error
            })
        except Exception as e:
            LoggingService.LogException("Error updating service status", e, "QualityTestService", "UpdateServiceStatus")
    
    def StartHealthMonitoring(self):
        """Start health monitoring thread."""
        try:
            self.HealthCheckThread = threading.Thread(
                target=self.HealthCheckLoop,
                daemon=True,
                name="HealthChecker"
            )
            self.HealthCheckThread.start()
            LoggingService.LogInfo("Health monitoring started", "QualityTestService", "StartHealthMonitoring")
        except Exception as e:
            LoggingService.LogException("Error starting health monitoring", e, "QualityTestService", "StartHealthMonitoring")
    
    def HealthCheckLoop(self):
        """Health monitoring loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Update health status
                self.UpdateServiceStatus("Running", "Healthy", 0, False)
                self.ShutdownEvent.wait(30)  # Check every 30 seconds
            except Exception as e:
                LoggingService.LogException("Error in health check", e, "QualityTestService", "HealthCheckLoop")
                self.ShutdownEvent.wait(60)
    
    def PrivateStartStatusPolling(self):
        """Start status polling thread."""
        try:
            self.StatusPollingThread = threading.Thread(
                target=self.PrivateStatusPollingLoop,
                daemon=True,
                name="StatusPoller"
            )
            self.StatusPollingThread.start()
            LoggingService.LogInfo("Status polling started", "QualityTestService", "PrivateStartStatusPolling")
        except Exception as e:
            LoggingService.LogException("Error starting status polling", e, "QualityTestService", "PrivateStartStatusPolling")
    
    def PrivateStatusPollingLoop(self):
        """Status polling loop - checks ServiceStatus table for quality test commands."""
        while not self.ShutdownEvent.is_set():
            try:
                # Get current quality test status from ServiceStatus table
                service_status = self.DatabaseManager.GetServiceStatus("QualityTestService")
                
                if service_status:
                    new_status = service_status.get('Status', 'Stopped')
                    is_processing = service_status.get('IsProcessing', False)
                    
                    # Check if status has changed
                    if new_status != self.CurrentStatus:
                        LoggingService.LogInfo(f"Quality test status changed from {self.CurrentStatus} to {new_status}", 
                                             "QualityTestService", "PrivateStatusPollingLoop")
                        
                        # Handle status change
                        self.PrivateHandleStatusChange(new_status, is_processing)
                        self.CurrentStatus = new_status
                
                # Wait 5 seconds before next check
                self.ShutdownEvent.wait(5)
                
            except Exception as e:
                LoggingService.LogException("Error in status polling loop", e, "QualityTestService", "PrivateStatusPollingLoop")
                self.ShutdownEvent.wait(10)
    
    def PrivateHandleStatusChange(self, new_status: str, is_processing: bool):
        """Handle quality test status changes."""
        try:
            LoggingService.LogFunctionEntry("PrivateHandleStatusChange", "QualityTestService", new_status)
            
            if new_status == "Starting":
                # Service is starting up - update status to Running
                LoggingService.LogInfo("Service starting up, updating status to Running", "QualityTestService", "PrivateHandleStatusChange")
                self.UpdateServiceStatus("Running", "Healthy", 0, False)
                
            elif new_status == "Running" and not is_processing:
                # Start quality testing
                LoggingService.LogInfo("Starting quality testing based on status change", "QualityTestService", "PrivateHandleStatusChange")
                result = self.ProcessQualityTestQueue.Run(MaxConcurrentJobs=1)
                if result.get("Success", False):
                    LoggingService.LogInfo("Quality testing started successfully", "QualityTestService", "PrivateHandleStatusChange")
                else:
                    LoggingService.LogError(f"Failed to start quality testing: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "QualityTestService", "PrivateHandleStatusChange")
                
            elif new_status == "Stopped" and is_processing:
                # Stop quality testing
                LoggingService.LogInfo("Stopping quality testing based on status change", "QualityTestService", "PrivateHandleStatusChange")
                result = self.ProcessQualityTestQueue.Stop()
                if result.get("Success", False):
                    LoggingService.LogInfo("Quality testing stopped successfully", "QualityTestService", "PrivateHandleStatusChange")
                else:
                    LoggingService.LogError(f"Failed to stop quality testing: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "QualityTestService", "PrivateHandleStatusChange")
                    
        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "QualityTestService", "PrivateHandleStatusChange")
    
    def StartQualityTestProcessing(self):
        """Start quality test processing."""
        try:
            LoggingService.LogInfo("Starting quality test processing", "QualityTestService", "StartQualityTestProcessing")
            # The actual quality testing will be started by status polling
        except Exception as e:
            LoggingService.LogException("Error starting quality test processing", e, "QualityTestService", "StartQualityTestProcessing")
    
    def MainLoop(self):
        """Main processing loop."""
        try:
            LoggingService.LogInfo("QualityTestService main loop started", "QualityTestService", "MainLoop")
            while not self.ShutdownEvent.is_set():
                self.ShutdownEvent.wait(1)  # Check every second
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "QualityTestService", "MainLoop")
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            LoggingService.LogInfo("Shutting down QualityTestService...", "QualityTestService", "Shutdown")
            self.ShutdownEvent.set()
            LoggingService.LogInfo("QualityTestService shutdown complete", "QualityTestService", "Shutdown")
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "QualityTestService", "Shutdown")

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "QualityTestService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for QualityTestService."""
    try:
        LoggingService.LogInfo("Starting QualityTestService...", "QualityTestService", "main")
        
        # Initialize the application
        app = QualityTestServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("QualityTestService is now running. Press Ctrl+C to stop.", "QualityTestService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "QualityTestService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in QualityTestService", e, "QualityTestService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("QualityTestService stopped.", "QualityTestService", "main")

if __name__ == "__main__":
    Main()
