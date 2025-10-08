"""
TranscodeService Application Logic
Handles transcoding queue processing and service orchestration
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

from Services.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Services.LoggingService import LoggingService
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
        """Check if another TranscodeService instance is already running."""
        try:
            current_pid = os.getpid()
            transcode_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == 'TranscodeService' and proc.info['pid'] != current_pid:
                        transcode_processes.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if transcode_processes:
                LoggingService.LogError(f"Found {len(transcode_processes)} existing TranscodeService processes: {transcode_processes}", "TranscodeServiceApp", "PrivateIsServiceAlreadyRunning")
                return True
            
            return False
            
        except Exception as e:
            LoggingService.LogException("Exception checking for existing TranscodeService instances", e, "TranscodeServiceApp", "PrivateIsServiceAlreadyRunning")
            return False
    
    def Run(self):
        """Start the transcoding service."""
        try:
            LoggingService.LogInfo("Starting TranscodeService...", "TranscodeService", "run")
            
            # Check database connection
            if not self.CheckDatabaseConnection():
                LoggingService.LogError("Database connection failed, exiting...", "TranscodeService", "run")
                return False
            
            # Update service status in database
            self.UpdateServiceStatus("Starting")
            
            # Reset any stuck "Running" jobs from previous sessions
            self.ResetStuckJobs()
            
            # Start health monitoring
            self.StartHealthMonitoring()
            
            # Start status polling
            self.PrivateStartStatusPolling()
            
            # Start transcoding processing
            self.StartTranscodingProcessing()
            
            # Main processing loop
            self.MainLoop()
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error starting TranscodeService", e, "TranscodeService", "run")
            return False
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            LoggingService.LogInfo("Shutting down TranscodeService...", "TranscodeService", "shutdown")
            
            # Update service status
            self.UpdateServiceStatus("Stopping")
            
            # Signal shutdown
            self.ShutdownEvent.set()
            
            # Stop transcoding processing
            if self.ProcessTranscodeQueue:
                self.ProcessTranscodeQueue.Stop()
            
            # Wait for threads to finish
            if self.ProcessingThread and self.ProcessingThread.is_alive():
                self.ProcessingThread.join(timeout=10)
            
            if self.HealthCheckThread and self.HealthCheckThread.is_alive():
                self.HealthCheckThread.join(timeout=5)
            
            # Update service status
            self.UpdateServiceStatus("Stopped")
            
            LoggingService.LogInfo("TranscodeService shutdown complete", "TranscodeService", "shutdown")
            
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "TranscodeService", "shutdown")
    
    def CheckDatabaseConnection(self) -> bool:
        """Check if database connection is available."""
        try:
            # Try to get a simple query to test connection
            result = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT 1")
            LoggingService.LogDebug("Database connection successful", "TranscodeService", "CheckDatabaseConnection")
            return True
        except Exception as e:
            LoggingService.LogError(f"Database connection failed: {str(e)}", "TranscodeService", "CheckDatabaseConnection")
            return False
    
    def UpdateServiceStatus(self, status: str, health_status: str = "Unknown", 
                              active_jobs: int = 0, is_processing: bool = False, 
                              error_message: str = None):
        """Update service status in ServiceStatus table."""
        try:
            # Calculate uptime
            uptime_seconds = int((datetime.now() - self.StartTime).total_seconds())
            
            # Get system metrics
            memory_usage = self.GetMemoryUsage()
            cpu_usage = self.GetCPUUsage()
            disk_space = self.GetDiskSpace()
            
            # Check database connection
            database_connection = self.CheckDatabaseConnection()
            
            # Insert or update service status
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
                "TranscodeService",  # ServiceName
                status,              # Status
                health_status,       # HealthStatus
                self.StartTime,      # StartTime
                now,                 # LastHealthCheck
                uptime_seconds,      # UptimeSeconds
                memory_usage,        # MemoryUsage
                cpu_usage,           # CPUUsage
                database_connection, # DatabaseConnection
                disk_space,          # DiskSpace
                0,                   # ErrorCount
                5,                   # MaxErrors
                active_jobs,         # ActiveJobsCount
                is_processing,       # IsProcessing
                error_message,       # LastErrorMessage
                self.ProcessId,      # ProcessId
                "1.0.0",            # Version
                "Microservice",     # ServiceType
                now,                # CreatedAt
                now                 # UpdatedAt
            )
            
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, params)
            LoggingService.LogDebug(f"Service status updated: {status}", "TranscodeService", "UpdateServiceStatus")
            
        except Exception as e:
            LoggingService.LogException("Error updating service status", e, "TranscodeService", "UpdateServiceStatus")
    
    def GetMemoryUsage(self) -> float:
        """Get current memory usage percentage."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()
            memory_percent = (memory_info.rss / system_memory.total) * 100
            return round(memory_percent, 2)
        except Exception:
            return 0.0
    
    def GetCPUUsage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return round(psutil.cpu_percent(interval=1), 2)
        except Exception:
            return 0.0
    
    def GetDiskSpace(self) -> float:
        """Get available disk space percentage."""
        try:
            disk_usage = psutil.disk_usage('/')
            if disk_usage.total > 0:
                free_percent = (disk_usage.free / disk_usage.total) * 100
                return round(free_percent, 2)
            return 0.0
        except Exception:
            return 0.0
    
    def StartHealthMonitoring(self):
        """Start health monitoring thread."""
        try:
            self.HealthCheckThread = threading.Thread(
                target=self.HealthMonitoringLoop,
                daemon=True,
                name="HealthMonitor"
            )
            self.HealthCheckThread.start()
            LoggingService.LogInfo("Health monitoring started", "TranscodeService", "StartHealthMonitoring")
        except Exception as e:
            LoggingService.LogException("Error starting health monitoring", e, "TranscodeService", "StartHealthMonitoring")
    
    def StartTranscodingProcessing(self):
        """Start transcoding processing thread."""
        try:
            self.ProcessingThread = threading.Thread(
                target=self.TranscodingProcessingLoop,
                daemon=True,
                name="TranscodingProcessor"
            )
            self.ProcessingThread.start()
            LoggingService.LogInfo("Transcoding processing started", "TranscodeService", "StartTranscodingProcessing")
        except Exception as e:
            LoggingService.LogException("Error starting transcoding processing", e, "TranscodeService", "StartTranscodingProcessing")
    
    def HealthMonitoringLoop(self):
        """Health monitoring loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Check if transcoding is active
                status = self.ProcessTranscodeQueue.GetStatus()
                is_transcoding = False
                active_jobs = 0
                
                if status.get("Success", False):
                    is_transcoding = status.get("IsTranscoding", False)
                    active_jobs = status.get("ActiveJobsCount", 0)
                
                # Determine health status
                health_status = "Healthy"
                if not self.CheckDatabaseConnection():
                    health_status = "Unhealthy"
                elif self.GetMemoryUsage() > 90:
                    health_status = "Warning"
                elif self.GetDiskSpace() < 10:
                    health_status = "Warning"
                
                # Update service status with current metrics
                self.UpdateServiceStatus(
                    status="Running",
                    health_status=health_status,
                    active_jobs=active_jobs,
                    is_processing=is_transcoding
                )
                
                # Sleep for 30 seconds
                self.ShutdownEvent.wait(30)
                
            except Exception as e:
                LoggingService.LogException("Error in health monitoring", e, "TranscodeService", "HealthMonitoringLoop")
                self.UpdateServiceStatus(
                    status="Error",
                    health_status="Unhealthy",
                    error_message=str(e)
                )
                self.ShutdownEvent.wait(30)
    
    def TranscodingProcessingLoop(self):
        """Main transcoding processing loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Check if there are pending jobs
                pending_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Pending")
                
                if pending_jobs and len(pending_jobs) > 0:
                    # Start transcoding if not already running and not manually stopped
                    if not self.ProcessTranscodeQueue.IsProcessing and not self.ManuallyStopped:
                        LoggingService.LogInfo(f"Found {len(pending_jobs)} pending jobs, starting transcoding...", "TranscodeService", "TranscodingProcessingLoop")
                        result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=1)
                        if not result.get("Success", False):
                            LoggingService.LogError(f"Failed to start transcoding: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeService", "TranscodingProcessingLoop")
                else:
                    # No pending jobs, check if we should stop
                    if self.ProcessTranscodeQueue.IsProcessing:
                        # Check if there are any running jobs
                        running_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
                        if not running_jobs or len(running_jobs) == 0:
                            LoggingService.LogInfo("No pending or running jobs, stopping transcoding...", "TranscodeService", "TranscodingProcessingLoop")
                            self.ProcessTranscodeQueue.Stop()
                
                # Sleep for 10 seconds before next check
                self.ShutdownEvent.wait(10)
                
            except Exception as e:
                LoggingService.LogException("Error in transcoding processing loop", e, "TranscodeService", "TranscodingProcessingLoop")
                self.ShutdownEvent.wait(10)
    
    def MainLoop(self):
        """Main application loop."""
        try:
            self.IsRunning = True
            LoggingService.LogInfo("TranscodeService is running...", "TranscodeService", "MainLoop")
            
            # Keep the main thread alive
            while self.IsRunning and not self.ShutdownEvent.is_set():
                # Check for graceful shutdown request
                if self.PrivateCheckForGracefulShutdown():
                    LoggingService.LogInfo("Graceful shutdown requested, stopping service...", "TranscodeService", "MainLoop")
                    break
                
                self.ShutdownEvent.wait(5)  # Check for graceful shutdown every 5 seconds instead of every second
                
        except KeyboardInterrupt:
            LoggingService.LogInfo("Received keyboard interrupt", "TranscodeService", "MainLoop")
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "TranscodeService", "MainLoop")
        finally:
            self.IsRunning = False
            # If shutdown was requested, exit the process
            if self.ShutdownEvent.is_set():
                LoggingService.LogInfo("Shutdown event set, exiting TranscodeService process", "TranscodeService", "MainLoop")
                sys.exit(0)
    
    def PrivateCheckForGracefulShutdown(self) -> bool:
        """Check if graceful shutdown has been requested via database status."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            
            db_manager = DatabaseManager()
            service_status = db_manager.GetServiceStatus("TranscodeService")
            
            if service_status and service_status.get('Status') == 'GracefulStop':
                LoggingService.LogInfo("Graceful shutdown detected in database", "TranscodeService", "PrivateCheckForGracefulShutdown")
                return True
            
            return False
            
        except Exception as e:
            LoggingService.LogException("Error checking graceful shutdown status", e, "TranscodeService", "PrivateCheckForGracefulShutdown")
            return False
    
    def ResetStuckJobs(self):
        """Reset any stuck 'Running' jobs from previous sessions."""
        try:
            LoggingService.LogInfo("Checking for stuck jobs from previous sessions...", "TranscodeService", "ResetStuckJobs")
            
            # Find stuck "Running" jobs
            query = "SELECT Id, FileName FROM TranscodeQueue WHERE Status = 'Running'"
            stuck_jobs = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            
            if stuck_jobs:
                LoggingService.LogInfo(f"Found {len(stuck_jobs)} stuck jobs from previous session", "TranscodeService", "ResetStuckJobs")
                
                # Reset them to Pending
                reset_query = "UPDATE TranscodeQueue SET Status = 'Pending', DateStarted = NULL WHERE Status = 'Running'"
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(reset_query)
                
                # Clear associated progress records
                progress_query = "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE FilePath IN (SELECT FilePath FROM TranscodeQueue WHERE Status = 'Pending' AND DateStarted IS NULL))"
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(progress_query)
                
                LoggingService.LogInfo(f"Reset {len(stuck_jobs)} stuck jobs to Pending status", "TranscodeService", "ResetStuckJobs")
                
                for job in stuck_jobs:
                    LoggingService.LogInfo(f"  - Reset job {job[0]}: {job[1]}", "TranscodeService", "ResetStuckJobs")
            else:
                LoggingService.LogInfo("No stuck jobs found", "TranscodeService", "ResetStuckJobs")
                
        except Exception as e:
            LoggingService.LogException("Error resetting stuck jobs", e, "TranscodeService", "ResetStuckJobs")
    
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
                    
            elif NewStatus == "GracefulStop":
                # Handle graceful stop request - allow current job to complete, then stop
                LoggingService.LogInfo("Graceful stop requested - will complete current job before stopping", 
                                     "TranscodeService", "PrivateHandleStatusChange")
                
                # Set a flag to stop accepting new jobs but allow current job to complete
                self.ProcessTranscodeQueue.StopRequested = True
                
                # Update service status to indicate graceful stop is in progress
                self.UpdateServiceStatus("GracefulStop", "Stopping", 0, True, "Completing current job before stopping")
                
                # Start a monitoring thread to check when current job completes
                threading.Thread(
                    target=self.PrivateMonitorGracefulStop,
                    daemon=True,
                    name="GracefulStopMonitor"
                ).start()
                    
            elif NewStatus == "Paused" and IsProcessing:
                # Pause transcoding (same as stop for now)
                LoggingService.LogInfo("Pausing transcoding based on status change", "TranscodeService", "PrivateHandleStatusChange")
                result = self.ProcessTranscodeQueue.Stop()
                if result.get("Success", False):
                    LoggingService.LogInfo("Transcoding paused successfully", "TranscodeService", "PrivateHandleStatusChange")
                else:
                    LoggingService.LogError(f"Failed to pause transcoding: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "TranscodeService", "PrivateHandleStatusChange")
                    
        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "TranscodeService", "PrivateHandleStatusChange")
    
    def PrivateMonitorGracefulStop(self):
        """Monitor graceful stop progress and complete shutdown when current job finishes."""
        try:
            LoggingService.LogInfo("Starting graceful stop monitoring", "TranscodeService", "PrivateMonitorGracefulStop")
            
            # Wait for current transcoding to complete
            while self.ProcessTranscodeQueue.IsProcessing and not self.ShutdownEvent.is_set():
                LoggingService.LogInfo("Waiting for current transcoding job to complete...", "TranscodeService", "PrivateMonitorGracefulStop")
                time.sleep(5)  # Check every 5 seconds
            
            # Current job has completed, now stop transcoding processing
            LoggingService.LogInfo("Current job completed, stopping transcoding processing", "TranscodeService", "PrivateMonitorGracefulStop")
            result = self.ProcessTranscodeQueue.Stop()
            
            if result.get("Success", False):
                LoggingService.LogInfo("Transcoding stopped successfully for graceful shutdown", "TranscodeService", "PrivateMonitorGracefulStop")
            else:
                LoggingService.LogError(f"Failed to stop transcoding for graceful shutdown: {result.get('ErrorMessage', 'Unknown error')}", 
                                      "TranscodeService", "PrivateMonitorGracefulStop")
            
            # Update service status to Stopped
            self.UpdateServiceStatus("Stopped", "Stopped", 0, False, "Graceful stop completed")
            
            # Signal shutdown event to trigger service termination
            LoggingService.LogInfo("Graceful stop completed, signaling shutdown", "TranscodeService", "PrivateMonitorGracefulStop")
            self.ShutdownEvent.set()
            
        except Exception as e:
            LoggingService.LogException("Error in graceful stop monitoring", e, "TranscodeService", "PrivateMonitorGracefulStop")
            # Force shutdown on error
            self.ShutdownEvent.set()
    
