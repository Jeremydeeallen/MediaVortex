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
from Services.ServiceCommandService import ServiceCommandService
from Repositories.DatabaseManager import DatabaseManager

class TranscodeServiceApp:
    """Main application class for TranscodeService."""
    
    def __init__(self):
        """Initialize the TranscodeService application."""
        self.DatabaseManager = DatabaseManager()
        self.ProcessTranscodeQueue = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager
        )
        self.CommandService = ServiceCommandService(DatabaseManagerInstance=self.DatabaseManager)
        self.IsRunning = False
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.CommandProcessingThread = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        
        LoggingService.LogInfo("TranscodeServiceApp initialized", "TranscodeService", "__init__")
    
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
            
            # Start command processing
            self._StartCommandProcessing()
            
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
                    # Start transcoding if not already running
                    if not self.ProcessTranscodeQueue.IsProcessing:
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
                self.ShutdownEvent.wait(1)
                
        except KeyboardInterrupt:
            LoggingService.LogInfo("Received keyboard interrupt", "TranscodeService", "MainLoop")
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "TranscodeService", "MainLoop")
        finally:
            self.IsRunning = False
    
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
    
    def _StartCommandProcessing(self):
        """Start command processing thread."""
        try:
            self.CommandProcessingThread = threading.Thread(
                target=self._CommandProcessingLoop,
                daemon=True,
                name="CommandProcessor"
            )
            self.CommandProcessingThread.start()
            LoggingService.LogInfo("Command processing started", "TranscodeService", "_StartCommandProcessing")
        except Exception as e:
            LoggingService.LogException("Error starting command processing", e, "TranscodeService", "_StartCommandProcessing")
    
    def _CommandProcessingLoop(self):
        """Command processing loop - polls for and executes database commands."""
        while not self.ShutdownEvent.is_set():
            try:
                # Get pending commands for TranscodeService
                PendingCommands = self.CommandService.GetPendingCommands("TranscodeService")
                
                for Command in PendingCommands:
                    try:
                        CommandId = Command["Id"]
                        CommandType = Command["CommandType"]
                        Parameters = Command["Parameters"]
                        
                        LoggingService.LogInfo(f"Processing command {CommandId}: {CommandType}", 
                                             "TranscodeService", "_CommandProcessingLoop")
                        
                        # Mark command as processing
                        self.CommandService.UpdateCommandStatus(CommandId, "Processing")
                        
                        # Execute the command
                        Result = self._ExecuteCommand(CommandType, Parameters)
                        
                        # Update command with result
                        if Result.get("Success", False):
                            self.CommandService.UpdateCommandStatus(
                                CommandId, "Completed", 
                                Result=Result, ErrorMessage=None
                            )
                            LoggingService.LogInfo(f"Command {CommandId} completed successfully", 
                                                 "TranscodeService", "_CommandProcessingLoop")
                        else:
                            self.CommandService.UpdateCommandStatus(
                                CommandId, "Failed", 
                                Result=Result, ErrorMessage=Result.get("ErrorMessage", "Unknown error")
                            )
                            LoggingService.LogError(f"Command {CommandId} failed: {Result.get('ErrorMessage', 'Unknown error')}", 
                                                   "TranscodeService", "_CommandProcessingLoop")
                            
                    except Exception as e:
                        LoggingService.LogException(f"Error processing command {Command.get('Id', 'Unknown')}", 
                                                 e, "TranscodeService", "_CommandProcessingLoop")
                        # Mark command as failed
                        self.CommandService.UpdateCommandStatus(
                            Command.get("Id", 0), "Failed", 
                            ErrorMessage=str(e)
                        )
                
                # Wait 5 seconds before checking for new commands
                self.ShutdownEvent.wait(5)
                
            except Exception as e:
                LoggingService.LogException("Error in command processing loop", e, "TranscodeService", "_CommandProcessingLoop")
                self.ShutdownEvent.wait(10)
    
    def _ExecuteCommand(self, CommandType: str, Parameters: dict) -> dict:
        """Execute a specific command."""
        try:
            if CommandType == "StartTranscoding":
                return self._ExecuteStartTranscoding(Parameters)
            elif CommandType == "StopTranscoding":
                return self._ExecuteStopTranscoding(Parameters)
            elif CommandType == "PauseTranscoding":
                return self._ExecutePauseTranscoding(Parameters)
            elif CommandType == "ResumeTranscoding":
                return self._ExecuteResumeTranscoding(Parameters)
            elif CommandType == "GetStatus":
                return self._ExecuteGetStatus(Parameters)
            elif CommandType == "HealthCheck":
                return self._ExecuteHealthCheck(Parameters)
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Unknown command type: {CommandType}"
                }
        except Exception as e:
            LoggingService.LogException(f"Error executing command {CommandType}", e, "TranscodeService", "_ExecuteCommand")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecuteStartTranscoding(self, Parameters: dict) -> dict:
        """Execute StartTranscoding command."""
        try:
            MaxConcurrentJobs = Parameters.get("MaxConcurrentJobs", 1)
            
            # Start transcoding with ProcessTranscodeQueueService
            Result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=MaxConcurrentJobs)
            
            if Result.get("Success", False):
                LoggingService.LogInfo(f"Started transcoding with {MaxConcurrentJobs} concurrent jobs", 
                                     "TranscodeService", "_ExecuteStartTranscoding")
                return {
                    "Success": True,
                    "Message": f"Transcoding started with {MaxConcurrentJobs} concurrent jobs",
                    "MaxConcurrentJobs": MaxConcurrentJobs
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": Result.get("ErrorMessage", "Failed to start transcoding")
                }
        except Exception as e:
            LoggingService.LogException("Error starting transcoding", e, "TranscodeService", "_ExecuteStartTranscoding")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecuteStopTranscoding(self, Parameters: dict) -> dict:
        """Execute StopTranscoding command."""
        try:
            # Stop transcoding
            self.ProcessTranscodeQueue.Stop()
            
            LoggingService.LogInfo("Stopped transcoding", "TranscodeService", "_ExecuteStopTranscoding")
            return {
                "Success": True,
                "Message": "Transcoding stopped"
            }
        except Exception as e:
            LoggingService.LogException("Error stopping transcoding", e, "TranscodeService", "_ExecuteStopTranscoding")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecutePauseTranscoding(self, Parameters: dict) -> dict:
        """Execute PauseTranscoding command."""
        try:
            # Pause transcoding (if supported by ProcessTranscodeQueueService)
            # For now, we'll stop it as pause functionality may not be implemented
            self.ProcessTranscodeQueue.Stop()
            
            LoggingService.LogInfo("Paused transcoding", "TranscodeService", "_ExecutePauseTranscoding")
            return {
                "Success": True,
                "Message": "Transcoding paused"
            }
        except Exception as e:
            LoggingService.LogException("Error pausing transcoding", e, "TranscodeService", "_ExecutePauseTranscoding")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecuteResumeTranscoding(self, Parameters: dict) -> dict:
        """Execute ResumeTranscoding command."""
        try:
            MaxConcurrentJobs = Parameters.get("MaxConcurrentJobs", 1)
            
            # Resume transcoding
            Result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=MaxConcurrentJobs)
            
            if Result.get("Success", False):
                LoggingService.LogInfo(f"Resumed transcoding with {MaxConcurrentJobs} concurrent jobs", 
                                     "TranscodeService", "_ExecuteResumeTranscoding")
                return {
                    "Success": True,
                    "Message": f"Transcoding resumed with {MaxConcurrentJobs} concurrent jobs"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": Result.get("ErrorMessage", "Failed to resume transcoding")
                }
        except Exception as e:
            LoggingService.LogException("Error resuming transcoding", e, "TranscodeService", "_ExecuteResumeTranscoding")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecuteGetStatus(self, Parameters: dict) -> dict:
        """Execute GetStatus command."""
        try:
            # Get current status
            Status = self.ProcessTranscodeQueue.GetStatus()
            
            return {
                "Success": True,
                "Status": Status,
                "Message": "Status retrieved successfully"
            }
        except Exception as e:
            LoggingService.LogException("Error getting status", e, "TranscodeService", "_ExecuteGetStatus")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def _ExecuteHealthCheck(self, Parameters: dict) -> dict:
        """Execute HealthCheck command."""
        try:
            # Perform health check
            HealthStatus = "Healthy"
            if not self.CheckDatabaseConnection():
                HealthStatus = "Unhealthy"
            elif self.GetMemoryUsage() > 90:
                HealthStatus = "Warning"
            elif self.GetDiskSpace() < 10:
                HealthStatus = "Warning"
            
            return {
                "Success": True,
                "HealthStatus": HealthStatus,
                "MemoryUsage": self.GetMemoryUsage(),
                "CPUUsage": self.GetCPUUsage(),
                "DiskSpace": self.GetDiskSpace(),
                "DatabaseConnection": self.CheckDatabaseConnection(),
                "Message": f"Health check completed: {HealthStatus}"
            }
        except Exception as e:
            LoggingService.LogException("Error performing health check", e, "TranscodeService", "_ExecuteHealthCheck")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
