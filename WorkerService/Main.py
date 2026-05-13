#!/usr/bin/env python3
"""
WorkerService Entry Point
Unified worker microservice for MediaVortex.
Replaces separate TranscodeService + QualityTestService processes.
Reads per-worker capabilities (TranscodeEnabled, QualityTestEnabled, ScanEnabled)
and status (Online, Draining, Offline) from the Workers table.
"""

import sys
import signal
import os
import setproctitle
import time
import threading
import socket
import platform as platform_mod
import shutil
from datetime import datetime, timezone

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("WorkerService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class WorkerServiceApp:
    """Unified worker application that runs transcode, quality test, and scan capabilities."""

    def __init__(self):
        """Initialize the WorkerService application."""
        CurrentPid = os.getpid()
        LoggingService.LogInfo(f"WorkerServiceApp __init__ started. PID: {CurrentPid}", "WorkerService", "__init__")

        self.DatabaseManager = DatabaseManager()

        # Worker identity
        self.WorkerName = socket.gethostname()
        self.WorkerPlatform = platform_mod.system().lower()
        LoggingService.LogInfo(f"Worker identity: {self.WorkerName} ({self.WorkerPlatform})", "WorkerService", "__init__")

        # Register worker and load config from Workers table
        self.WorkerConfig = self._RegisterAndLoadWorkerConfig()

        # Initialize WorkerContext singleton
        from Core.WorkerContext import WorkerContext
        WorkerContext.Initialize(
            WorkerName=self.WorkerName,
            Platform=self.WorkerPlatform,
            FFmpegPath=self.WorkerConfig.get('FFmpegPath') or self.WorkerConfig.get('ffmpegpath'),
            FFprobePath=self.WorkerConfig.get('FFprobePath') or self.WorkerConfig.get('ffprobepath'),
            StagingDirectory=self.WorkerConfig.get('StagingDirectory') or self.WorkerConfig.get('stagingdirectory'),
            ShareMappings=self.WorkerConfig.get('ShareMappings') or {}
        )
        LoggingService.LogInfo(f"WorkerContext initialized for {self.WorkerName}", "WorkerService", "__init__")

        # Threading state
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now(timezone.utc)
        self.ProcessId = CurrentPid

        # Capability instances (created lazily based on DB config)
        self.TranscodeService = None
        self.QualityTestService = None
        self.RemuxService = None
        self.ContinuousScanService = None

        # Current capabilities and status from DB
        self.TranscodeEnabled = False
        self.QualityTestEnabled = False
        self.RemuxEnabled = False
        self.ScanEnabled = False
        self.WorkerStatus = "Offline"

        # Threads
        self.HealthCheckThread = None
        self.StatusPollingThread = None
        self.CapabilityPollingThread = None

        # Transcode-specific state
        self.TranscodeCurrentStatus = "Stopped"
        self.TranscodeManuallyStopped = False

        LoggingService.LogInfo(f"WorkerServiceApp __init__ completed. PID: {CurrentPid}", "WorkerService", "__init__")

    def _RegisterAndLoadWorkerConfig(self) -> dict:
        """Register this worker in the Workers table and load its configuration."""
        try:
            # Detect platform-appropriate FFmpeg/FFprobe paths.
            # Prefer the project's bundled binaries over PATH so Windows hosts (where
            # FFmpeg typically isn't on PATH) still get a real value into Workers.
            # FAIL LOUDLY if neither resolves -- a worker with no FFmpeg cannot do
            # any work, and silently registering NULL produces the broken-by-default
            # state we hit today on I9-2024.
            FFmpegPath = self._ResolveBundledOrPathBinary('ffmpeg')
            FFprobePath = self._ResolveBundledOrPathBinary('ffprobe')
            if not FFmpegPath or not FFprobePath:
                raise RuntimeError(
                    f"Worker {self.WorkerName} cannot start: FFmpeg/FFprobe binaries not found. "
                    f"FFmpeg={FFmpegPath!r}, FFprobe={FFprobePath!r}. "
                    f"Bundle them under FFmpegMaster/bin/ or put them on PATH."
                )

            # CPU thread limit from env var
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
            LoggingService.LogInfo(
                f"Worker '{self.WorkerName}' registered (ffmpeg={FFmpegPath}, ffprobe={FFprobePath}, threads={MaxCpuThreads})",
                "WorkerService", "_RegisterAndLoadWorkerConfig"
            )

            # Register share mappings from env var
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
                    self.DatabaseManager.RegisterStorageRootResolutions(self.WorkerName, self.WorkerPlatform, Mappings)
                    LoggingService.LogInfo(f"Worker '{self.WorkerName}' registered share mappings: {Mappings}", "WorkerService", "_RegisterAndLoadWorkerConfig")
            else:
                # Windows workers: no share mappings env var, register StorageRootResolutions
                # using canonical prefixes as the local paths (drive letters ARE the paths)
                self.DatabaseManager.RegisterStorageRootResolutionsFromCanonical(self.WorkerName, self.WorkerPlatform)

            # Load worker config from DB
            Config = self.DatabaseManager.GetWorkerConfig(self.WorkerName)
            if Config:
                LoggingService.LogInfo(
                    f"Worker config loaded: FFmpegPath={Config.get('FFmpegPath') or Config.get('ffmpegpath') or '(default)'}, "
                    f"StagingDirectory={Config.get('StagingDirectory') or Config.get('stagingdirectory') or '(default)'}",
                    "WorkerService", "_RegisterAndLoadWorkerConfig"
                )
                return Config
            return {}
        except Exception as e:
            LoggingService.LogException("Error registering worker, using defaults", e, "WorkerService", "_RegisterAndLoadWorkerConfig")
            return {}

    def _ResolveBundledOrPathBinary(self, BinaryName: str) -> str:
        """Resolve ffmpeg or ffprobe binary path. Project bundle first, PATH second.
        Returns absolute path or empty string. Never logs silently -- caller decides."""
        ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        Suffix = ".exe" if platform_mod.system().lower() == "windows" else ""
        Bundled = os.path.join(ProjectRoot, "FFmpegMaster", "bin", f"{BinaryName}{Suffix}")
        if os.path.exists(Bundled):
            return Bundled
        FromPath = shutil.which(BinaryName)
        if FromPath:
            return FromPath
        return ""

    def _LoadCapabilitiesFromDB(self):
        """Load capability flags and status from Workers table."""
        try:
            Query = """
                SELECT TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled, Status
                FROM Workers
                WHERE WorkerName = %s
            """
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (self.WorkerName,))
            if Rows:
                Row = Rows[0]
                self.TranscodeEnabled = bool(Row.get('TranscodeEnabled', True))
                self.QualityTestEnabled = bool(Row.get('QualityTestEnabled', False))
                self.RemuxEnabled = bool(Row.get('RemuxEnabled', True))
                self.ScanEnabled = bool(Row.get('ScanEnabled', False))
                self.WorkerStatus = Row.get('Status', 'Online') or 'Online'
            else:
                LoggingService.LogWarning(f"No Workers row found for '{self.WorkerName}', using defaults", "WorkerService", "_LoadCapabilitiesFromDB")
                self.TranscodeEnabled = True
                self.QualityTestEnabled = False
                self.RemuxEnabled = True
                self.ScanEnabled = False
                self.WorkerStatus = "Online"
        except Exception as e:
            LoggingService.LogException("Error loading capabilities from DB", e, "WorkerService", "_LoadCapabilitiesFromDB")

    # --- Capability lifecycle ---

    def _GetPerCapabilityConcurrency(self, CapabilityKey: str, Default: int = 1) -> int:
        """Read per-capability MaxConcurrentJobs from WorkerConfig.
        Falls back to legacy MaxConcurrentJobs, then to provided default."""
        Value = self.WorkerConfig.get(CapabilityKey) or self.WorkerConfig.get(CapabilityKey.lower())
        if Value:
            return max(1, min(5, int(Value)))
        # Fallback to legacy single column
        Legacy = self.WorkerConfig.get('MaxConcurrentJobs') or self.WorkerConfig.get('maxconcurrentjobs')
        if Legacy:
            return max(1, min(5, int(Legacy)))
        return Default

    def _StartTranscodeCapability(self):
        """Initialize and start the transcode processing capability."""
        if self.TranscodeService is not None:
            return
        try:
            from Services.ProcessTranscodeQueueService import ProcessTranscodeQueueService
            self.TranscodeService = ProcessTranscodeQueueService(
                DatabaseManagerInstance=self.DatabaseManager,
                WorkerName=self.WorkerName,
                WorkerConfig=self.WorkerConfig
            )
            self.TranscodeCurrentStatus = "Running"
            self.TranscodeManuallyStopped = False
            MaxJobs = self._GetPerCapabilityConcurrency('MaxConcurrentTranscodeJobs', Default=1)
            Result = self.TranscodeService.Run(MaxConcurrentJobs=MaxJobs)
            if Result.get("Success", False):
                LoggingService.LogInfo(f"Transcode capability started ({MaxJobs} concurrent jobs)", "WorkerService", "_StartTranscodeCapability")
            else:
                LoggingService.LogError(f"Failed to start transcode: {Result.get('ErrorMessage', 'Unknown')}", "WorkerService", "_StartTranscodeCapability")
        except Exception as e:
            LoggingService.LogException("Error starting transcode capability", e, "WorkerService", "_StartTranscodeCapability")

    def _StopTranscodeCapability(self):
        """Stop the transcode processing capability gracefully."""
        if self.TranscodeService is None:
            return
        try:
            LoggingService.LogInfo("Stopping transcode capability...", "WorkerService", "_StopTranscodeCapability")
            self.TranscodeService.StopRequested = True
            self.TranscodeManuallyStopped = True

            # Wait for current job to finish
            if self.TranscodeService.ProcessingThread and self.TranscodeService.ProcessingThread.is_alive():
                self.TranscodeService.ProcessingThread.join(timeout=7200)

            self.TranscodeService.IsProcessing = False
            self.TranscodeService.ActiveJobs.clear()
            self.TranscodeService = None
            self.TranscodeCurrentStatus = "Stopped"
            LoggingService.LogInfo("Transcode capability stopped", "WorkerService", "_StopTranscodeCapability")
        except Exception as e:
            LoggingService.LogException("Error stopping transcode capability", e, "WorkerService", "_StopTranscodeCapability")

    def _StartQualityTestCapability(self):
        """Initialize and start the quality test processing capability."""
        if self.QualityTestService is not None:
            return
        try:
            from Services.ProcessQualityTestQueueService import ProcessQualityTestQueueService
            self.QualityTestService = ProcessQualityTestQueueService(
                DatabaseManagerInstance=self.DatabaseManager
            )
            MaxJobs = self._GetPerCapabilityConcurrency('MaxConcurrentQualityTestJobs', Default=2)
            Result = self.QualityTestService.Run(MaxConcurrentJobs=MaxJobs)
            if Result.get("Success", False):
                LoggingService.LogInfo(f"Quality test capability started ({MaxJobs} concurrent jobs)", "WorkerService", "_StartQualityTestCapability")
            else:
                LoggingService.LogError(f"Failed to start quality test: {Result.get('ErrorMessage', 'Unknown')}", "WorkerService", "_StartQualityTestCapability")
        except Exception as e:
            LoggingService.LogException("Error starting quality test capability", e, "WorkerService", "_StartQualityTestCapability")

    def _StopQualityTestCapability(self):
        """Stop the quality test processing capability gracefully."""
        if self.QualityTestService is None:
            return
        try:
            LoggingService.LogInfo("Stopping quality test capability...", "WorkerService", "_StopQualityTestCapability")
            Result = self.QualityTestService.Stop()
            if Result.get("Success", False):
                LoggingService.LogInfo("Quality test capability stopped", "WorkerService", "_StopQualityTestCapability")
            self.QualityTestService = None
        except Exception as e:
            LoggingService.LogException("Error stopping quality test capability", e, "WorkerService", "_StopQualityTestCapability")

    def _StartRemuxCapability(self):
        """Initialize and start the remux processing capability."""
        if self.RemuxService is not None:
            return
        try:
            from Features.TranscodeJob.ProcessRemuxQueueService import ProcessRemuxQueueService
            self.RemuxService = ProcessRemuxQueueService(
                DatabaseManagerInstance=self.DatabaseManager,
                WorkerName=self.WorkerName,
                WorkerConfig=self.WorkerConfig
            )
            MaxJobs = self._GetPerCapabilityConcurrency('MaxConcurrentRemuxJobs', Default=2)
            Result = self.RemuxService.Run(MaxConcurrentJobs=MaxJobs)
            if Result.get("Success", False):
                LoggingService.LogInfo(f"Remux capability started ({MaxJobs} concurrent jobs)", "WorkerService", "_StartRemuxCapability")
            else:
                LoggingService.LogError(f"Failed to start remux: {Result.get('ErrorMessage', 'Unknown')}", "WorkerService", "_StartRemuxCapability")
        except Exception as e:
            LoggingService.LogException("Error starting remux capability", e, "WorkerService", "_StartRemuxCapability")

    def _StopRemuxCapability(self):
        """Stop the remux processing capability gracefully."""
        if self.RemuxService is None:
            return
        try:
            LoggingService.LogInfo("Stopping remux capability...", "WorkerService", "_StopRemuxCapability")
            self.RemuxService.StopRequested = True
            if self.RemuxService.ProcessingThread and self.RemuxService.ProcessingThread.is_alive():
                self.RemuxService.ProcessingThread.join(timeout=300)
            self.RemuxService.IsProcessing = False
            self.RemuxService.ActiveJobs.clear()
            self.RemuxService = None
            LoggingService.LogInfo("Remux capability stopped", "WorkerService", "_StopRemuxCapability")
        except Exception as e:
            LoggingService.LogException("Error stopping remux capability", e, "WorkerService", "_StopRemuxCapability")

    def _StartScanCapability(self):
        """Initialize and start the continuous scanning capability."""
        if self.ContinuousScanService is not None:
            return
        try:
            from Features.FileScanning.ContinuousScanService import ContinuousScanService
            self.ContinuousScanService = ContinuousScanService()

            # Read scan interval from SystemSettings
            IntervalMinutes = 60
            try:
                IntervalSetting = self.DatabaseManager.GetSystemSetting('ContinuousScanIntervalMinutes')
                if IntervalSetting:
                    IntervalMinutes = int(IntervalSetting)
            except Exception:
                pass

            Result = self.ContinuousScanService.StartContinuousScanning(IntervalMinutes)
            if Result.get('Success'):
                LoggingService.LogInfo(f"Scan capability started with {IntervalMinutes} minute interval", "WorkerService", "_StartScanCapability")
            else:
                LoggingService.LogError(f"Failed to start scanning: {Result.get('ErrorMessage', 'Unknown')}", "WorkerService", "_StartScanCapability")
        except Exception as e:
            LoggingService.LogException("Error starting scan capability", e, "WorkerService", "_StartScanCapability")

    def _StopScanCapability(self):
        """Stop the continuous scanning capability."""
        if self.ContinuousScanService is None:
            return
        try:
            LoggingService.LogInfo("Stopping scan capability...", "WorkerService", "_StopScanCapability")
            self.ContinuousScanService.StopContinuousScanning()
            self.ContinuousScanService = None
            LoggingService.LogInfo("Scan capability stopped", "WorkerService", "_StopScanCapability")
        except Exception as e:
            LoggingService.LogException("Error stopping scan capability", e, "WorkerService", "_StopScanCapability")

    # --- Service lifecycle ---

    def Run(self):
        """Start the worker service."""
        try:
            LoggingService.LogInfo("Starting WorkerService...", "WorkerService", "Run")

            # Ensure service status record exists
            self._EnsureServiceStatusExists()

            # Perform crash recovery for transcode
            self._RecoverFromCrash()

            # Detect and clean stuck jobs
            self._DetectAndCleanStuckJobs()

            # Load capabilities from DB
            self._LoadCapabilitiesFromDB()

            LoggingService.LogInfo(
                f"Capabilities: Transcode={self.TranscodeEnabled}, QualityTest={self.QualityTestEnabled}, Scan={self.ScanEnabled}, Status={self.WorkerStatus}",
                "WorkerService", "Run"
            )

            # Mark worker as Online
            self.DatabaseManager.UpdateWorkerStatus(self.WorkerName, "Online")

            # Start health monitoring
            self._StartHealthMonitoring()

            # Start status polling (5s interval for status changes)
            self._StartStatusPolling()

            # Start capability polling (60s interval for capability changes)
            self._StartCapabilityPolling()

            # Start recurring stuck-job detection (default 120s interval).
            # See stuck-job-detection.feature.md criterion 1.
            self._StartStuckJobDetection()

            # Start enabled capabilities if worker is Online
            if self.WorkerStatus == "Online":
                self._ApplyCapabilities()

            # Update service status
            self._UpdateServiceStatus("Running")

            LoggingService.LogInfo("WorkerService is now running", "WorkerService", "Run")

            # Main loop
            self._MainLoop()

            return True

        except Exception as e:
            LoggingService.LogException("Error starting WorkerService", e, "WorkerService", "Run")
            return False

    def _EnsureServiceStatusExists(self):
        """Ensure ServiceStatus record exists for WorkerService."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            StatusService = ServiceStatusService()
            StatusService.EnsureServiceStatusExists("WorkerService", MaxConcurrentJobs=1)
            LoggingService.LogInfo("ServiceStatus record ensured for WorkerService", "WorkerService", "_EnsureServiceStatusExists")
        except Exception as e:
            LoggingService.LogException("Error ensuring ServiceStatus exists", e, "WorkerService", "_EnsureServiceStatusExists")

    def _RecoverFromCrash(self):
        """Recover from previous crash."""
        try:
            LoggingService.LogInfo("Starting crash recovery...", "WorkerService", "_RecoverFromCrash")
            from Services.CrashRecoveryService import CrashRecoveryService
            RecoveryService = CrashRecoveryService(self.DatabaseManager, WorkerName=self.WorkerName)
            Result = RecoveryService.RecoverServiceJobs("TranscodeService")
            if Result.get("Success", False):
                LoggingService.LogInfo(
                    f"Crash recovery completed: {Result.get('JobsRecovered', 0)} jobs recovered, {Result.get('OrphanedProcessesKilled', 0)} orphaned processes killed",
                    "WorkerService", "_RecoverFromCrash"
                )
            else:
                LoggingService.LogError(f"Crash recovery failed: {Result.get('Message', 'Unknown error')}", "WorkerService", "_RecoverFromCrash")
        except Exception as e:
            LoggingService.LogException("Error during crash recovery", e, "WorkerService", "_RecoverFromCrash")

    def _DetectAndCleanStuckJobs(self):
        """Detect and clean up stuck jobs."""
        try:
            LoggingService.LogInfo("Starting stuck job detection...", "WorkerService", "_DetectAndCleanStuckJobs")
            from Services.StuckJobDetectionService import StuckJobDetectionService
            DetectionService = StuckJobDetectionService(self.DatabaseManager)

            # Clean stuck transcode jobs
            Result = DetectionService.DetectAndCleanStuckTranscodeJobs()
            if Result.get("Success", False):
                LoggingService.LogInfo(
                    f"Stuck transcode job detection: {Result.get('StuckJobsFound', 0)} found, {Result.get('JobsCleaned', 0)} cleaned",
                    "WorkerService", "_DetectAndCleanStuckJobs"
                )

            # Clean stuck quality test jobs
            Result = DetectionService.DetectAndCleanStuckQualityTestJobs()
            if Result.get("Success", False):
                LoggingService.LogInfo(
                    f"Stuck quality test job detection: {Result.get('StuckJobsFound', 0)} found, {Result.get('JobsCleaned', 0)} cleaned",
                    "WorkerService", "_DetectAndCleanStuckJobs"
                )

            # Clean stuck scan jobs (FileScanning.feature.md criterion 18 stuck-scan side)
            Result = DetectionService.DetectAndCleanStuckScanJobs()
            if Result.get("Success", False):
                LoggingService.LogInfo(
                    f"Stuck scan job detection: {Result.get('StuckScansFound', 0)} found, {Result.get('ScansCleaned', 0)} cleaned",
                    "WorkerService", "_DetectAndCleanStuckJobs"
                )
        except Exception as e:
            LoggingService.LogException("Error during stuck job detection", e, "WorkerService", "_DetectAndCleanStuckJobs")

    def _UpdateServiceStatus(self, Status, Health="Healthy", ActiveJobs=0, IsProcessing=False):
        """Update service status in database."""
        try:
            self.DatabaseManager.UpdateServiceStatus("WorkerService", {
                'Status': Status,
                'HealthStatus': Health,
                'ActiveJobsCount': ActiveJobs,
                'IsProcessing': IsProcessing
            })
        except Exception as e:
            LoggingService.LogException("Error updating service status", e, "WorkerService", "_UpdateServiceStatus")

    def _ApplyCapabilities(self):
        """Start or stop capabilities based on current DB flags."""
        # Transcode
        if self.TranscodeEnabled and self.TranscodeService is None:
            self._StartTranscodeCapability()
        elif not self.TranscodeEnabled and self.TranscodeService is not None:
            threading.Thread(target=self._StopTranscodeCapability, daemon=True, name="StopTranscode").start()

        # Quality test
        if self.QualityTestEnabled and self.QualityTestService is None:
            self._StartQualityTestCapability()
        elif not self.QualityTestEnabled and self.QualityTestService is not None:
            threading.Thread(target=self._StopQualityTestCapability, daemon=True, name="StopQualityTest").start()

        # Remux
        if self.RemuxEnabled and self.RemuxService is None:
            self._StartRemuxCapability()
        elif not self.RemuxEnabled and self.RemuxService is not None:
            threading.Thread(target=self._StopRemuxCapability, daemon=True, name="StopRemux").start()

        # Scan
        if self.ScanEnabled and self.ContinuousScanService is None:
            self._StartScanCapability()
        elif not self.ScanEnabled and self.ContinuousScanService is not None:
            self._StopScanCapability()

    # --- Polling threads ---

    def _StartStuckJobDetection(self):
        """Start recurring stuck-job detection thread.

        Reads SystemSettings.StuckJobDetectionIntervalSec each cycle (default
        120). Owns stuck-job-detection.feature.md criterion 1.
        """
        try:
            self.StuckDetectionThread = threading.Thread(
                target=self._StuckJobDetectionLoop,
                daemon=True,
                name="StuckJobDetector"
            )
            self.StuckDetectionThread.start()
            LoggingService.LogInfo("Stuck job detection loop started", "WorkerService", "_StartStuckJobDetection")
        except Exception as e:
            LoggingService.LogException("Error starting stuck job detection loop", e, "WorkerService", "_StartStuckJobDetection")

    def _StuckJobDetectionLoop(self):
        """Run stuck-job detection on a configurable interval until shutdown."""
        # Avoid double-firing immediately after the startup-time call in
        # _DetectAndCleanStuckJobs by sleeping the interval first.
        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
        SettingsRepo = SystemSettingsRepository()

        def _ReadInterval():
            try:
                v = SettingsRepo.GetSystemSetting('StuckJobDetectionIntervalSec')
                return max(30, int(v)) if v is not None else 120
            except Exception:
                return 120

        # Initial wait so startup-time detection isn't duplicated.
        self.ShutdownEvent.wait(_ReadInterval())

        while not self.ShutdownEvent.is_set():
            try:
                from Services.StuckJobDetectionService import StuckJobDetectionService
                DetectionService = StuckJobDetectionService(self.DatabaseManager)
                # Transcode side
                if self.TranscodeEnabled:
                    DetectionService.DetectAndCleanStuckTranscodeJobs()
                # Quality test side (cheap, runs even with QualityTest disabled
                # since the detector returns no-op when no QT jobs exist)
                try:
                    DetectionService.DetectAndCleanStuckQualityTestJobs()
                except Exception as qtEx:
                    LoggingService.LogException("Error in stuck quality-test detection cycle", qtEx, "WorkerService", "_StuckJobDetectionLoop")

                # Scan side (cheap, runs unconditionally -- the detector returns
                # no-op when no Running scans exist, and any ScanEnabled worker
                # in the cluster can clean stale rows so other workers' crashes
                # don't leak into this worker's continuous-scan ticks)
                try:
                    DetectionService.DetectAndCleanStuckScanJobs()
                except Exception as scanEx:
                    LoggingService.LogException("Error in stuck scan detection cycle", scanEx, "WorkerService", "_StuckJobDetectionLoop")
            except Exception as e:
                LoggingService.LogException("Error in stuck job detection cycle", e, "WorkerService", "_StuckJobDetectionLoop")
            self.ShutdownEvent.wait(_ReadInterval())

    def _StartHealthMonitoring(self):
        """Start health monitoring thread."""
        try:
            self.HealthCheckThread = threading.Thread(
                target=self._HealthCheckLoop,
                daemon=True,
                name="HealthChecker"
            )
            self.HealthCheckThread.start()
            LoggingService.LogInfo("Health monitoring started", "WorkerService", "_StartHealthMonitoring")
        except Exception as e:
            LoggingService.LogException("Error starting health monitoring", e, "WorkerService", "_StartHealthMonitoring")

    def _HealthCheckLoop(self):
        """Health monitoring loop - updates heartbeat."""
        while not self.ShutdownEvent.is_set():
            try:
                self.DatabaseManager.UpdateServiceStatus("WorkerService", {
                    'HealthStatus': 'Healthy'
                })
                self.DatabaseManager.UpdateWorkerHeartbeat(self.WorkerName)
                self.ShutdownEvent.wait(30)
            except Exception as e:
                LoggingService.LogException("Error in health check", e, "WorkerService", "_HealthCheckLoop")
                self.ShutdownEvent.wait(60)

    def _StartStatusPolling(self):
        """Start status polling thread (5s interval)."""
        try:
            self.StatusPollingThread = threading.Thread(
                target=self._StatusPollingLoop,
                daemon=True,
                name="StatusPoller"
            )
            self.StatusPollingThread.start()
            LoggingService.LogInfo("Status polling started (5s interval)", "WorkerService", "_StartStatusPolling")
        except Exception as e:
            LoggingService.LogException("Error starting status polling", e, "WorkerService", "_StartStatusPolling")

    def _StatusPollingLoop(self):
        """Poll Workers.Status for this worker every 5 seconds."""
        while not self.ShutdownEvent.is_set():
            try:
                Query = "SELECT Status FROM Workers WHERE WorkerName = %s"
                Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (self.WorkerName,))
                if Rows:
                    NewStatus = Rows[0].get('Status', 'Online') or 'Online'
                    if NewStatus != self.WorkerStatus:
                        LoggingService.LogInfo(f"Worker status changed: {self.WorkerStatus} -> {NewStatus}", "WorkerService", "_StatusPollingLoop")
                        OldStatus = self.WorkerStatus
                        self.WorkerStatus = NewStatus
                        self._HandleStatusChange(OldStatus, NewStatus)

                self.ShutdownEvent.wait(5)
            except Exception as e:
                LoggingService.LogException("Error in status polling loop", e, "WorkerService", "_StatusPollingLoop")
                self.ShutdownEvent.wait(10)

    def _HandleStatusChange(self, OldStatus, NewStatus):
        """Handle worker status transitions."""
        try:
            if NewStatus == "Online":
                # Came back online - start enabled capabilities
                LoggingService.LogInfo("Worker is Online, starting enabled capabilities", "WorkerService", "_HandleStatusChange")
                self._ApplyCapabilities()

            elif NewStatus == "Draining":
                # Finish current jobs, do not pick up new ones
                LoggingService.LogInfo("Worker is Draining, finishing current jobs then stopping", "WorkerService", "_HandleStatusChange")
                if self.TranscodeService is not None:
                    self.TranscodeService.StopRequested = True
                if self.QualityTestService is not None:
                    try:
                        self.QualityTestService.Stop()
                    except Exception:
                        pass
                if self.ContinuousScanService is not None:
                    self._StopScanCapability()

                # Wait for transcode to finish current job in background
                threading.Thread(target=self._DrainAndStop, daemon=True, name="DrainWaiter").start()

            elif NewStatus == "Offline":
                # Stop everything
                LoggingService.LogInfo("Worker is Offline, stopping all capabilities", "WorkerService", "_HandleStatusChange")
                self._StopAllCapabilities()

        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "WorkerService", "_HandleStatusChange")

    def _DrainAndStop(self):
        """Wait for current transcode job to finish, then clean up."""
        try:
            if self.TranscodeService is not None:
                if self.TranscodeService.ProcessingThread and self.TranscodeService.ProcessingThread.is_alive():
                    self.TranscodeService.ProcessingThread.join(timeout=7200)
                self.TranscodeService.IsProcessing = False
                self.TranscodeService.ActiveJobs.clear()
                self.TranscodeService = None
            self.QualityTestService = None
            LoggingService.LogInfo("Drain complete, all capabilities stopped", "WorkerService", "_DrainAndStop")
        except Exception as e:
            LoggingService.LogException("Error during drain", e, "WorkerService", "_DrainAndStop")

    def _StopAllCapabilities(self):
        """Immediately stop all running capabilities."""
        if self.TranscodeService is not None:
            threading.Thread(target=self._StopTranscodeCapability, daemon=True, name="StopTranscode").start()
        if self.QualityTestService is not None:
            threading.Thread(target=self._StopQualityTestCapability, daemon=True, name="StopQualityTest").start()
        if self.ContinuousScanService is not None:
            self._StopScanCapability()

    def _StartCapabilityPolling(self):
        """Start capability polling thread (60s interval)."""
        try:
            self.CapabilityPollingThread = threading.Thread(
                target=self._CapabilityPollingLoop,
                daemon=True,
                name="CapabilityPoller"
            )
            self.CapabilityPollingThread.start()
            LoggingService.LogInfo("Capability polling started (60s interval)", "WorkerService", "_StartCapabilityPolling")
        except Exception as e:
            LoggingService.LogException("Error starting capability polling", e, "WorkerService", "_StartCapabilityPolling")

    def _CapabilityPollingLoop(self):
        """Poll Workers table every 60 seconds for capability flag changes."""
        while not self.ShutdownEvent.is_set():
            try:
                self.ShutdownEvent.wait(60)
                if self.ShutdownEvent.is_set():
                    break

                # Only apply capability changes when Online
                if self.WorkerStatus != "Online":
                    continue

                OldTranscode = self.TranscodeEnabled
                OldQualityTest = self.QualityTestEnabled
                OldScan = self.ScanEnabled

                self._LoadCapabilitiesFromDB()

                if (OldTranscode != self.TranscodeEnabled or
                        OldQualityTest != self.QualityTestEnabled or
                        OldScan != self.ScanEnabled):
                    LoggingService.LogInfo(
                        f"Capabilities changed: Transcode={OldTranscode}->{self.TranscodeEnabled}, "
                        f"QualityTest={OldQualityTest}->{self.QualityTestEnabled}, "
                        f"Scan={OldScan}->{self.ScanEnabled}",
                        "WorkerService", "_CapabilityPollingLoop"
                    )
                    self._ApplyCapabilities()

            except Exception as e:
                LoggingService.LogException("Error in capability polling loop", e, "WorkerService", "_CapabilityPollingLoop")
                self.ShutdownEvent.wait(30)

    # --- Main loop and shutdown ---

    def _MainLoop(self):
        """Main processing loop."""
        try:
            LoggingService.LogInfo("WorkerService main loop started", "WorkerService", "_MainLoop")
            while not self.ShutdownEvent.is_set():
                self.ShutdownEvent.wait(10)
        except Exception as e:
            LoggingService.LogException("Error in main loop", e, "WorkerService", "_MainLoop")

    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            LoggingService.LogInfo("Shutting down WorkerService...", "WorkerService", "Shutdown")

            # Mark worker as Offline
            self.DatabaseManager.UpdateWorkerStatus(self.WorkerName, "Offline")

            # Update service status
            self.DatabaseManager.UpdateServiceStatus("WorkerService", {
                'Status': 'Stopped',
                'ProcessId': 0,
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            self.ShutdownEvent.set()
            LoggingService.LogInfo("WorkerService shutdown complete", "WorkerService", "Shutdown")
        except Exception as e:
            LoggingService.LogException("Error during shutdown", e, "WorkerService", "Shutdown")


_SIGNAL_BUDGET_SECONDS = 2.0


def SignalHandler(signum, frame):
    """Handle shutdown signals so a single Ctrl+C exits cleanly.

    The handler must NOT block on potentially-slow operations (DB queries can
    stall when the pool is contended or postgres is unresponsive). Any work
    that touches the network or DB runs in a daemon thread with a 2s budget;
    after the budget the process exits via os._exit regardless. Re-entry from
    a second signal during cleanup is a no-op so spamming Ctrl+C does not
    confuse the handler.
    """
    if getattr(SignalHandler, '_in_progress', False):
        # Operator hit Ctrl+C again while we were cleaning up. Force exit.
        print("\nForcing exit (already shutting down)...")
        os._exit(1)
    SignalHandler._in_progress = True

    print("\nWorkerService shutting down...")

    # Step 1: kill FFmpeg subprocesses inline. proc.kill() does not block --
    # it just delivers a terminate signal -- so this is safe in the handler.
    if hasattr(Main, 'app') and Main.app:
        App = Main.app
        try:
            if App.TranscodeService is not None:
                ActiveJobIds = App.TranscodeService.VideoTranscoding.GetActiveJobs()
                for JobId in ActiveJobIds:
                    try:
                        Proc = App.TranscodeService.VideoTranscoding.ActiveProcesses.get(JobId)
                        if Proc:
                            Proc.kill()
                    except Exception:
                        pass
        except Exception as e:
            try:
                LoggingService.LogException(
                    "Error killing FFmpeg processes during SignalHandler", e, "SignalHandler", "WorkerService"
                )
            except Exception:
                print(f"EXCEPTION (logger unavailable): killing FFmpeg processes: {e}")

    # Step 2: do potentially-slow DB cleanup in a background thread with a hard
    # budget. Worker-Offline / pool-close are best-effort; if the DB hangs the
    # heartbeat-staleness check will eventually flip the row to Offline anyway.
    def _DeferredCleanup():
        try:
            if hasattr(Main, 'app') and Main.app:
                App = Main.app
                try:
                    Db = App.DatabaseManager
                    Db.UpdateServiceStatus("WorkerService", {
                        'Status': 'Stopped',
                        'ProcessId': 0,
                        'IsProcessing': False,
                        'ActiveJobsCount': 0
                    })
                    Db.UpdateWorkerStatus(App.WorkerName, "Offline")
                except Exception as e:
                    try:
                        LoggingService.LogException(
                            f"Error marking worker {App.WorkerName!r} Offline during SignalHandler",
                            e, "SignalHandler", "WorkerService"
                        )
                    except Exception:
                        print(f"EXCEPTION (logger unavailable): marking worker offline: {e}")
        finally:
            try:
                from Core.Database.DatabaseService import DatabaseService
                if DatabaseService._pool is not None and not DatabaseService._pool.closed:
                    DatabaseService._pool.closeall()
            except Exception as e:
                try:
                    LoggingService.LogException(
                        "Error closing DB pool during SignalHandler", e, "SignalHandler", "WorkerService"
                    )
                except Exception:
                    print(f"EXCEPTION (logger unavailable): closing DB pool: {e}")

    CleanupThread = threading.Thread(target=_DeferredCleanup, name="ShutdownCleanup", daemon=True)
    CleanupThread.start()
    CleanupThread.join(timeout=_SIGNAL_BUDGET_SECONDS)

    # Step 3: exit -- whether cleanup finished, timed out, or threw, the
    # process must terminate now so the operator's Ctrl+C is honored.
    os._exit(0)


def _VerifyRequiredPaths():
    """Hard-fail at startup if media share paths the queue references are not accessible.
    On Windows, scans MediaFiles for distinct drive-letter prefixes and checks each via
    os.path.exists. Mirrors the StartMediaVortex.py mount logic so a worker launched
    standalone (without StartMediaVortex.py) does not silently claim and fail every job
    when net use mounts are missing. On non-Windows platforms, bind mounts are the
    responsibility of the container orchestration layer and this check is skipped."""
    if platform_mod.system().lower() != 'windows':
        return

    try:
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT DISTINCT UPPER(LEFT(FilePath, 2)) AS DriveLetter "
            "FROM MediaFiles WHERE FilePath ~ '^[A-Za-z]:'"
        )
    except Exception as Ex:
        print(f"[FATAL] Could not read MediaFiles to verify required drives: {Ex}", flush=True)
        sys.exit(1)

    Missing = []
    for Row in Rows:
        Drive = Row.get('DriveLetter') or Row.get('driveletter')
        if not Drive:
            continue
        if not os.path.exists(Drive + '\\'):
            Missing.append(Drive)

    if Missing:
        Msg = (f"Required network drives not accessible: {', '.join(sorted(Missing))}. "
               f"Mount with 'net use' or relaunch via StartMediaVortex.py before starting WorkerService.")
        print(f"\n[FATAL] {Msg}\n", flush=True)
        try:
            LoggingService.LogError(Msg, "WorkerService", "_VerifyRequiredPaths")
        except Exception:
            pass
        sys.exit(1)


def Main():
    """Main entry point for WorkerService."""
    try:
        LoggingService.LogInfo("Starting WorkerService...", "WorkerService", "Main")

        # Hard-fail before any DB writes if required media drives aren't mounted.
        # Prevents the worker from registering, claiming jobs, and burning queue items
        # with FFprobe "no such file" failures when StartMediaVortex.py's net use step
        # was skipped.
        _VerifyRequiredPaths()

        # Initialize the application
        App = WorkerServiceApp()
        Main.app = App  # Store reference for signal handler

        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)

        # Start the service (runs indefinitely)
        LoggingService.LogInfo("WorkerService is now running. Press Ctrl+C to stop.", "WorkerService", "Main")
        App.Run()

    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "WorkerService", "Main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in WorkerService", e, "WorkerService", "Main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("WorkerService stopped.", "WorkerService", "Main")


if __name__ == "__main__":
    Main()
