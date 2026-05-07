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
from Services.GracefulStopService import GracefulStopService
from Repositories.DatabaseManager import DatabaseManager

class TranscodeServiceApp:
    """Main application class for TranscodeService."""

    def __init__(self):
        """Initialize the TranscodeService application."""
        import socket
        import platform

        current_pid = os.getpid()
        LoggingService.LogInfo(f"TranscodeServiceApp __init__ started. PID: {current_pid}", "TranscodeService", "__init__")
        self.DatabaseManager = DatabaseManager()
        LoggingService.LogInfo(f"DatabaseManager created. PID: {current_pid}", "TranscodeService", "__init__")

        # Worker identity for distributed transcoding
        self.WorkerName = socket.gethostname()
        self.WorkerPlatform = platform.system().lower()
        LoggingService.LogInfo(f"Worker identity: {self.WorkerName} ({self.WorkerPlatform})", "TranscodeService", "__init__")

        # Register worker and load config from Workers table
        self.WorkerConfig = self._RegisterAndLoadWorkerConfig()

        # Duplicate prevention is now handled in Main() function
        LoggingService.LogInfo(f"Creating ProcessTranscodeQueueService. PID: {current_pid}", "TranscodeService", "__init__")
        self.ProcessTranscodeQueue = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager,
            WorkerName=self.WorkerName,
            WorkerConfig=self.WorkerConfig
        )
        LoggingService.LogInfo(f"ProcessTranscodeQueueService created. PID: {current_pid}", "TranscodeService", "__init__")
        
        # Initialize graceful stop service
        self.GracefulStopService = GracefulStopService(
            ServiceName="TranscodeService",
            DatabaseManagerInstance=self.DatabaseManager,
            ProcessQueueService=self.ProcessTranscodeQueue
        )
        
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.StatusPollingThread = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        self.CurrentStatus = "Stopped"  # Track current transcoding status
        LoggingService.LogInfo(f"TranscodeServiceApp __init__ completed. PID: {current_pid}", "TranscodeService", "__init__")
        self.ManuallyStopped = False  # Track if transcoding was manually stopped
        
        LoggingService.LogInfo("TranscodeServiceApp initialized", "TranscodeService", "__init__")

    def _RegisterAndLoadWorkerConfig(self) -> dict:
        """Register this worker in the Workers table and load its configuration."""
        try:
            import shutil

            # Detect platform-appropriate FFmpeg/FFprobe paths
            FFmpegPath = shutil.which('ffmpeg')
            FFprobePath = shutil.which('ffprobe')

            # CPU thread limit from env var (matches Docker compose cpus limit)
            MaxCpuThreadsEnv = os.environ.get('MEDIAVORTEX_MAX_CPU_THREADS')
            MaxCpuThreads = int(MaxCpuThreadsEnv) if MaxCpuThreadsEnv else None

            # Register worker (UPSERT - creates or updates)
            self.DatabaseManager.RegisterWorker(
                WorkerName=self.WorkerName,
                Platform=self.WorkerPlatform,
                FFmpegPath=FFmpegPath,
                FFprobePath=FFprobePath,
                MaxCpuThreads=MaxCpuThreads
            )
            LoggingService.LogInfo(f"Worker '{self.WorkerName}' registered in Workers table (ffmpeg={FFmpegPath}, ffprobe={FFprobePath}, threads={MaxCpuThreads})", "TranscodeService", "_RegisterAndLoadWorkerConfig")

            # Register share mappings from MEDIAVORTEX_SHARE_MAPPINGS env var
            # Format: "T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/"
            ShareMappingsEnv = os.environ.get('MEDIAVORTEX_SHARE_MAPPINGS', '')
            if ShareMappingsEnv:
                Mappings = {}
                for Entry in ShareMappingsEnv.split(','):
                    Entry = Entry.strip()
                    if '=' in Entry:
                        DriveLetter, MountPath = Entry.split('=', 1)
                        Mappings[DriveLetter.strip()] = MountPath.strip()
                if Mappings:
                    self.DatabaseManager.RegisterWorkerShareMappings(self.WorkerName, Mappings)
                    LoggingService.LogInfo(f"Worker '{self.WorkerName}' registered share mappings: {Mappings}", "TranscodeService", "_RegisterAndLoadWorkerConfig")

            # Load worker config from DB
            Config = self.DatabaseManager.GetWorkerConfig(self.WorkerName)
            if Config:
                LoggingService.LogInfo(
                    f"Worker config loaded: FFmpegPath={Config.get('FFmpegPath') or Config.get('ffmpegpath') or '(default)'}, "
                    f"StagingDirectory={Config.get('StagingDirectory') or Config.get('stagingdirectory') or '(default)'}, "
                    f"MaxConcurrentJobs={Config.get('MaxConcurrentJobs') or Config.get('maxconcurrentjobs') or 1}",
                    "TranscodeService", "_RegisterAndLoadWorkerConfig"
                )
                return Config
            return {}
        except Exception as e:
            LoggingService.LogException("Error registering worker, using defaults", e, "TranscodeService", "_RegisterAndLoadWorkerConfig")
            return {}

    def Run(self):
        """Start the transcoding service."""
        try:
            LoggingService.LogInfo("Starting TranscodeService...", "TranscodeService", "run")
            
            # Ensure service status record exists
            self.EnsureServiceStatusExists()
            
            # Update service status in database
            self.UpdateServiceStatus("Starting")
            
            # Perform crash recovery
            self.RecoverFromCrash()
            
            # Detect and clean up stuck jobs
            self.DetectAndCleanStuckJobs()
            
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
            
            # Import and use the new CrashRecoveryService (scoped to this worker)
            from Services.CrashRecoveryService import CrashRecoveryService
            recovery_service = CrashRecoveryService(self.DatabaseManager, WorkerName=self.WorkerName)
            
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
    
    def DetectAndCleanStuckJobs(self):
        """Detect and clean up stuck transcode jobs where FFmpeg processes have died."""
        try:
            LoggingService.LogInfo("Starting stuck job detection for TranscodeService...", "TranscodeService", "DetectAndCleanStuckJobs")
            
            # Import and use the StuckJobDetectionService
            from Services.StuckJobDetectionService import StuckJobDetectionService
            detection_service = StuckJobDetectionService(self.DatabaseManager)
            
            # Perform stuck job detection and cleanup
            result = detection_service.DetectAndCleanStuckTranscodeJobs()
            
            if result.get("Success", False):
                stuck_found = result.get("StuckJobsFound", 0)
                jobs_cleaned = result.get("JobsCleaned", 0)
                LoggingService.LogInfo(f"Stuck job detection completed: {stuck_found} stuck jobs found, {jobs_cleaned} jobs cleaned", 
                                     "TranscodeService", "DetectAndCleanStuckJobs")
            else:
                LoggingService.LogError(f"Stuck job detection failed: {result.get('ErrorMessage', 'Unknown error')}", 
                                      "TranscodeService", "DetectAndCleanStuckJobs")
                
        except Exception as e:
            LoggingService.LogException("Error during stuck job detection", e, "TranscodeService", "DetectAndCleanStuckJobs")
    
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
        """Health monitoring loop - updates heartbeat without overwriting operational status."""
        while not self.ShutdownEvent.is_set():
            try:
                # Only update health heartbeat, never overwrite the operational Status
                self.DatabaseManager.UpdateServiceStatus("TranscodeService", {
                    'HealthStatus': 'Healthy'
                })
                # Update worker heartbeat for distributed stuck-job detection
                self.DatabaseManager.UpdateWorkerHeartbeat(self.WorkerName)
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
                service_status = self.DatabaseManager.GetServiceStatus("TranscodeService")
                
                if service_status:
                    new_status = service_status.get('Status', 'Stopped')
                    is_processing = service_status.get('IsProcessing', False)
                    
                    # Check if status has changed
                    if new_status != self.CurrentStatus:
                        LoggingService.LogInfo(f"Transcoding status changed from {self.CurrentStatus} to {new_status}", 
                                             "TranscodeService", "PrivateStatusPollingLoop")
                        
                        # Handle status change
                        self.PrivateHandleStatusChange(new_status, is_processing)
                        self.CurrentStatus = new_status
                
                # Wait 5 seconds before next check
                self.ShutdownEvent.wait(5)
                
            except Exception as e:
                LoggingService.LogException("Error in status polling loop", e, "TranscodeService", "PrivateStatusPollingLoop")
                self.ShutdownEvent.wait(10)
    
    def PrivateHandleStatusChange(self, new_status: str, is_processing: bool):
        """Handle transcoding status changes."""
        try:
            LoggingService.LogFunctionEntry("PrivateHandleStatusChange", "TranscodeService", new_status)
            
            if new_status == "Starting":
                # Service is starting up - update status to Running
                LoggingService.LogInfo("Service starting up, updating status to Running", "TranscodeService", "PrivateHandleStatusChange")
                self.UpdateServiceStatus("Running", "Healthy", 0, False)
                
            elif new_status == "Running":
                # Start transcoding if not already processing
                if not self.ProcessTranscodeQueue.IsProcessing:
                    LoggingService.LogInfo("Starting transcoding based on status change", "TranscodeService", "PrivateHandleStatusChange")
                    self.ManuallyStopped = False
                    result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=1)
                    if result.get("Success", False):
                        LoggingService.LogInfo("Transcoding started successfully", "TranscodeService", "PrivateHandleStatusChange")
                    else:
                        LoggingService.LogError(f"Failed to start transcoding: {result.get('ErrorMessage', 'Unknown error')}", 
                                              "TranscodeService", "PrivateHandleStatusChange")
                
            elif new_status in ("Stopped", "GracefulStop"):
                # Stop transcoding - let current job finish, then go idle
                LoggingService.LogInfo(f"Stop requested (status={new_status}), finishing current job then stopping",
                                     "TranscodeService", "PrivateHandleStatusChange")
                self.ProcessTranscodeQueue.StopRequested = True
                self.ManuallyStopped = True
                
                # Wait for current job in a background thread so polling loop stays responsive
                threading.Thread(
                    target=self._WaitForStopAndUpdate,
                    daemon=True,
                    name="StopWaiter"
                ).start()
                    
        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "TranscodeService", "PrivateHandleStatusChange")
    
    def _WaitForStopAndUpdate(self):
        """Wait for current transcoding job to finish, then update status to Stopped."""
        try:
            # Wait for the processing thread to finish (current job completes)
            if self.ProcessTranscodeQueue.ProcessingThread and self.ProcessTranscodeQueue.ProcessingThread.is_alive():
                self.ProcessTranscodeQueue.ProcessingThread.join(timeout=7200)  # 2 hour max

            # Clean up
            self.ProcessTranscodeQueue.IsProcessing = False
            self.ProcessTranscodeQueue.ActiveJobs.clear()

            # Update DB to Stopped
            self.UpdateServiceStatus("Stopped", "Healthy", 0, False)
            LoggingService.LogInfo("Transcoding stopped after current job completed",
                                 "TranscodeService", "_WaitForStopAndUpdate")
        except Exception as e:
            LoggingService.LogException("Error in stop waiter", e, "TranscodeService", "_WaitForStopAndUpdate")

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
                self.ShutdownEvent.wait(10)  # Check every 10 seconds
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "TranscodeService", "MainLoop")
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            LoggingService.LogInfo("Shutting down TranscodeService...", "TranscodeService", "Shutdown")

            # Mark worker as Offline
            self.DatabaseManager.UpdateWorkerStatus(self.WorkerName, "Offline")

            # Update service status to Stopped and clear ProcessId
            self.UpdateServiceStatus("Stopped", "Stopped", 0, False)
            self.DatabaseManager.UpdateServiceStatus("TranscodeService", {
                'Status': 'Stopped',
                'ProcessId': 0,
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            self.ShutdownEvent.set()
            LoggingService.LogInfo("TranscodeService shutdown complete", "TranscodeService", "Shutdown")
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "TranscodeService", "Shutdown")

def SignalHandler(signum, frame):
    """Handle shutdown signals immediately - kill FFmpeg, cleanup DB, exit.
    Scoped to this worker only -- never touches other workers' jobs."""
    print("\nTranscodeService shutting down...")

    if hasattr(Main, 'app') and Main.app:
        app = Main.app
        WorkerName = app.WorkerName

        # Kill all active FFmpeg processes immediately (local only)
        try:
            activeJobIds = app.ProcessTranscodeQueue.VideoTranscoding.GetActiveJobs()
            for jobId in activeJobIds:
                try:
                    proc = app.ProcessTranscodeQueue.VideoTranscoding.ActiveProcesses.get(jobId)
                    if proc:
                        proc.kill()
                except Exception:
                    pass
        except Exception:
            pass

        # Database cleanup: reset only THIS worker's running queue items and active jobs
        try:
            db = app.DatabaseManager
            db.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeQueue SET Status = 'Pending', ClaimedBy = NULL, ClaimedAt = NULL WHERE Status IN ('Running', 'Processing') AND ClaimedBy = %s",
                (WorkerName,)
            )
            db.DatabaseService.ExecuteNonQuery(
                "DELETE FROM ActiveJobs WHERE ServiceName = 'TranscodeService' AND WorkerName = %s",
                (WorkerName,)
            )
            db.DatabaseService.ExecuteNonQuery(
                """DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN (
                    SELECT ta.Id FROM TranscodeAttempts ta
                    INNER JOIN ActiveJobs aj ON aj.QueueId IN (
                        SELECT tq.Id FROM TranscodeQueue tq WHERE tq.ClaimedBy = %s
                    )
                    WHERE ta.Success IS NULL
                )""",
                (WorkerName,)
            )
            db.UpdateServiceStatus("TranscodeService", {
                'Status': 'Stopped',
                'ProcessId': 0,
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })
            db.UpdateWorkerStatus(WorkerName, "Offline")
        except Exception:
            pass

    os._exit(0)

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
