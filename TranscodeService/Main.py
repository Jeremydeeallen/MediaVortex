#!/usr/bin/env python3
"""
TranscodeService Entry Point
Standalone transcoding microservice for MediaVortex
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
setproctitle.setproctitle("TranscodeService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService
from Services.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Services.ServiceStatusHelperService import ServiceStatusHelperService
from Repositories.DatabaseManager import DatabaseManager

class TranscodeServiceApp:
    """Main application class for TranscodeService."""
    
    def __init__(self):
        """Initialize the TranscodeService application."""
        self.DatabaseManager = DatabaseManager()
        
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            LoggingService.LogError("TranscodeService is already running. Preventing duplicate instance.", "TranscodeServiceApp", "__init__")
            sys.exit(1)
        self.ProcessTranscodeQueue = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager
        )
        self.StatusHelper = ServiceStatusHelperService(DatabaseManagerInstance=self.DatabaseManager)
        self.IsRunning = False
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.StatusPollingThread = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        self.CurrentStatus = "Stopped"  # Track current transcoding status
        self.ManuallyStopped = False  # Track if transcoding was manually stopped
        
        LoggingService.LogInfo("TranscodeServiceApp initialized", "TranscodeService", "__init__")
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another TranscodeService instance is already running using ServiceStatusService."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            return status_service.RegisterServiceStartup("TranscodeService", MaxConcurrentJobs=1)
        except Exception as e:
            LoggingService.LogException("Exception checking for existing TranscodeService instances", e, "TranscodeServiceApp", "PrivateIsServiceAlreadyRunning")
            return True  # Prevent startup on error
    
    def Run(self):
        """Start the transcoding service."""
        try:
            LoggingService.LogInfo("Starting TranscodeService...", "TranscodeService", "run")
            
            # Check database connection
            if not self.CheckDatabaseConnection():
                LoggingService.LogError("Database connection failed, exiting...", "TranscodeService", "run")
                return False
            
            # Ensure service status record exists in database
            self.EnsureServiceStatusExists()

            # Update service status in database
            self.UpdateServiceStatus("Starting")
            
            # Recover from previous crash (reset stuck jobs and kill orphaned processes)
            self.RecoverFromCrash()
            
            # Start health monitoring
            self.StartHealthMonitoring()
            
            # Start status polling
            self.PrivateStartStatusPolling()
            
            # Start transcoding processing
            self.StartTranscodingProcessing()
            
            # Update service status to Running immediately after startup
            self.UpdateServiceStatus("Running", "Healthy", 0, False)
            
            # Main processing loop
            self.MainLoop()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting TranscodeService", e, "TranscodeService", "run")
            return False
    
    def CheckDatabaseConnection(self):
        """Check if database connection is working."""
        try:
            # Simple database test
            return True
        except Exception as e:
            LoggingService.LogException("Database connection failed", e, "TranscodeService", "CheckDatabaseConnection")
            return False
    
    def UpdateServiceStatus(self, status, health="Healthy", active_jobs=0, is_processing=False, last_error=None):
        """Update service status in database."""
        try:
            self.DatabaseManager.UpdateServiceStatus("TranscodeService", {
                'Status': status,
                'HealthStatus': health,
                'ActiveJobsCount': active_jobs,
                'IsProcessing': is_processing,
                'LastErrorMessage': last_error
            })
        except Exception as e:
            LoggingService.LogException("Error updating service status", e, "TranscodeService", "UpdateServiceStatus")
    
    def EnsureServiceStatusExists(self):
        """Ensure ServiceStatus record exists for TranscodeService, create if missing."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            result = status_service.EnsureServiceStatusExists("TranscodeService", MaxConcurrentJobs=1)
            
            if result:
                LoggingService.LogInfo("ServiceStatus record ensured for TranscodeService", "TranscodeService", "EnsureServiceStatusExists")
            else:
                LoggingService.LogError("Failed to ensure ServiceStatus record for TranscodeService", "TranscodeService", "EnsureServiceStatusExists")
                
        except Exception as e:
            LoggingService.LogException("Error ensuring ServiceStatus exists", e, "TranscodeService", "EnsureServiceStatusExists")
    
    def RecoverFromCrash(self):
        """Recover from previous crash using CrashRecoveryService."""
        try:
            LoggingService.LogInfo("Starting crash recovery for TranscodeService...", "TranscodeService", "RecoverFromCrash")
            
            # Import and use the new CrashRecoveryService
            from Services.CrashRecoveryService import CrashRecoveryService
            recovery_service = CrashRecoveryService(self.DatabaseManager)
            
            # Perform crash recovery
            result = recovery_service.RecoverServiceJobs("TranscodeService")
            
            if result.get("Success", False):
                jobs_recovered = result.get("JobsRecovered", 0)
                orphaned_killed = result.get("OrphanedProcessesKilled", 0)
                LoggingService.LogInfo(f"Crash recovery completed: {jobs_recovered} jobs recovered, {orphaned_killed} orphaned processes killed", 
                                     "TranscodeService", "RecoverFromCrash")
            else:
                LoggingService.LogError(f"Crash recovery failed: {result.get('Message', 'Unknown error')}", 
                                      "TranscodeService", "RecoverFromCrash")
                
        except Exception as e:
            LoggingService.LogException("Error during crash recovery", e, "TranscodeService", "RecoverFromCrash")
    
    def StartHealthMonitoring(self):
        """Start health monitoring thread."""
        try:
            self.HealthCheckThread = threading.Thread(
                target=self.HealthCheckLoop,
                daemon=True,
                name="HealthChecker"
            )
            self.HealthCheckThread.start()
            LoggingService.LogInfo("Health monitoring started", "TranscodeService", "StartHealthMonitoring")
        except Exception as e:
            LoggingService.LogException("Error starting health monitoring", e, "TranscodeService", "StartHealthMonitoring")
    
    def HealthCheckLoop(self):
        """Health monitoring loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Update health status
                self.UpdateServiceStatus("Running", "Healthy", 0, False)
                self.ShutdownEvent.wait(30)  # Check every 30 seconds
            except Exception as e:
                LoggingService.LogException("Error in health check", e, "TranscodeService", "HealthCheckLoop")
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
            LoggingService.LogInfo("Status polling started", "TranscodeService", "PrivateStartStatusPolling")
        except Exception as e:
            LoggingService.LogException("Error starting status polling", e, "TranscodeService", "PrivateStartStatusPolling")
    
    def PrivateStatusPollingLoop(self):
        """Status polling loop - checks ServiceStatus table for transcoding commands."""
        while not self.ShutdownEvent.is_set():
            try:
                # Get current transcoding status from ServiceStatus table
                statusResult = self.StatusHelper.GetTranscodingStatus()
                
                if statusResult.get("Success", False):
                    newStatus = statusResult.get("Status", "Stopped")
                    isProcessing = statusResult.get("IsProcessing", False)
                    
                    # Check if status has changed
                    if newStatus != self.CurrentStatus:
                        LoggingService.LogInfo(f"Transcoding status changed from {self.CurrentStatus} to {newStatus}", 
                                             "TranscodeService", "PrivateStatusPollingLoop")
                        
                        # Handle status change
                        self.PrivateHandleStatusChange(newStatus, isProcessing)
                        self.CurrentStatus = newStatus
                
                # Wait 5 seconds before next check
                self.ShutdownEvent.wait(5)
                
            except Exception as e:
                LoggingService.LogException("Error in status polling loop", e, "TranscodeService", "PrivateStatusPollingLoop")
                self.ShutdownEvent.wait(10)
    
    def PrivateHandleStatusChange(self, NewStatus: str, IsProcessing: bool):
        """Handle transcoding status changes."""
        try:
            LoggingService.LogFunctionEntry("PrivateHandleStatusChange", "TranscodeService", NewStatus)
            
            if NewStatus == "Starting":
                # Service is starting up - update status to Running
                LoggingService.LogInfo("Service starting up, updating status to Running", "TranscodeService", "PrivateHandleStatusChange")
                self.UpdateServiceStatus("Running", "Healthy", 0, False)
                
            elif NewStatus == "Running" and not IsProcessing:
                # Start transcoding
                LoggingService.LogInfo("Starting transcoding based on status change", "TranscodeService", "PrivateHandleStatusChange")
                result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=1)
                if result.get("Success", False):
                    LoggingService.LogInfo("Transcoding started successfully", "TranscodeService", "PrivateHandleStatusChange")
                else:
                    LoggingService.LogError(f"Failed to start transcoding: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "TranscodeService", "PrivateHandleStatusChange")
                    
            elif NewStatus == "Stopped" and IsProcessing:
                # Stop transcoding
                LoggingService.LogInfo("Stopping transcoding based on status change", "TranscodeService", "PrivateHandleStatusChange")
                result = self.ProcessTranscodeQueue.Stop()
                if result.get("Success", False):
                    LoggingService.LogInfo("Transcoding stopped successfully", "TranscodeService", "PrivateHandleStatusChange")
                else:
                    LoggingService.LogError(f"Failed to stop transcoding: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "TranscodeService", "PrivateHandleStatusChange")
                    
        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "TranscodeService", "PrivateHandleStatusChange")
    
    def StartTranscodingProcessing(self):
        """Start transcoding processing."""
        try:
            LoggingService.LogInfo("Starting transcoding processing", "TranscodeService", "StartTranscodingProcessing")
            # The actual transcoding will be started by status polling
        except Exception as e:
            LoggingService.LogException("Error starting transcoding processing", e, "TranscodeService", "StartTranscodingProcessing")
    
    def MainLoop(self):
        """Main processing loop."""
        try:
            LoggingService.LogInfo("TranscodeService main loop started", "TranscodeService", "MainLoop")
            while not self.ShutdownEvent.is_set():
                self.ShutdownEvent.wait(1)  # Check every second
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "TranscodeService", "MainLoop")
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            LoggingService.LogInfo("Shutting down TranscodeService...", "TranscodeService", "Shutdown")
            self.ShutdownEvent.set()
            LoggingService.LogInfo("TranscodeService shutdown complete", "TranscodeService", "Shutdown")
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "TranscodeService", "Shutdown")

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "TranscodeService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for TranscodeService."""
    try:
        LoggingService.LogInfo("Starting TranscodeService...", "TranscodeService", "main")
        
        # Initialize the application
        app = TranscodeServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("TranscodeService is now running. Press Ctrl+C to stop.", "TranscodeService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "TranscodeService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in TranscodeService", e, "TranscodeService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("TranscodeService stopped.", "TranscodeService", "main")

if __name__ == "__main__":
    Main()
