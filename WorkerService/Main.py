#!/usr/bin/env python3
"""
WorkerService Entry Point
Unified worker microservice for MediaVortex.
Replaces separate TranscodeService + QualityTestService processes.
Reads per-worker capabilities (TranscodeEnabled, QualityTestEnabled, ScanEnabled)
and status (Online, Paused) from the Workers table.
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
        self.WorkerName = self._ResolveWorkerName()
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
        self.WorkerStatus = "Paused"

        # Per-capability concurrency (data-driven, updated by capability poller)
        self.CurrentTranscodeConcurrency = 1
        self.CurrentQualityTestConcurrency = 2
        self.CurrentRemuxConcurrency = 2

        # Polling intervals (data-driven from SystemSettings)
        self.CapabilityPollingIntervalSec = self._LoadCapabilityPollingInterval()

        # Threads
        self.HealthCheckThread = None
        self.StatusPollingThread = None
        self.CapabilityPollingThread = None

        # Transcode-specific state
        self.TranscodeCurrentStatus = "Stopped"
        self.TranscodeManuallyStopped = False

        LoggingService.LogInfo(f"WorkerServiceApp __init__ completed. PID: {CurrentPid}", "WorkerService", "__init__")

    def _ResolveWorkerName(self) -> str:
        """Determine this worker's name.

        Priority:
        1. MEDIAVORTEX_WORKER_NAME env var (exact name override)
        2. MEDIAVORTEX_WORKER_PREFIX env var -> claims {prefix}-N via DB
        3. socket.gethostname() (fallback -- container ID or machine hostname)
        """
        ExactName = os.environ.get('MEDIAVORTEX_WORKER_NAME')
        if ExactName:
            return ExactName.strip()

        Prefix = os.environ.get('MEDIAVORTEX_WORKER_PREFIX')
        if Prefix:
            return self._ClaimPrefixedWorkerName(Prefix.strip())

        return socket.gethostname()

    def _ClaimPrefixedWorkerName(self, Prefix: str) -> str:
        """Claim the lowest available {Prefix}-N name using a DB advisory lock.

        A slot is 'available' if no Workers row exists for it, or the existing
        row has a heartbeat older than 2 minutes (stale/dead worker).
        """
        LockId = hash(Prefix) & 0x7FFFFFFF  # positive 32-bit advisory lock key
        try:
            # Use a raw connection to hold the advisory lock across queries
            import psycopg2
            Conn = self.DatabaseManager.DatabaseService._GetConnection()
            Conn.autocommit = False
            Cur = Conn.cursor()
            try:
                # Acquire session-level advisory lock to serialize claiming
                Cur.execute("SELECT pg_advisory_lock(%s)", (LockId,))

                # Find all existing workers with this prefix
                Cur.execute(
                    "SELECT WorkerName, LastHeartbeat FROM Workers "
                    "WHERE WorkerName LIKE %s ORDER BY WorkerName",
                    (Prefix + '-%',)
                )
                Existing = {Row[0]: Row[1] for Row in Cur.fetchall()}

                # Find the lowest available slot
                from datetime import timedelta
                StaleThreshold = datetime.now() - timedelta(minutes=2)
                Slot = 1
                while True:
                    CandidateName = f"{Prefix}-{Slot}"
                    if CandidateName not in Existing:
                        break  # unclaimed slot
                    Heartbeat = Existing[CandidateName]
                    if Heartbeat is None or Heartbeat < StaleThreshold:
                        break  # stale slot, safe to reclaim
                    Slot += 1

                ClaimedName = f"{Prefix}-{Slot}"
                LoggingService.LogInfo(
                    f"Claimed worker name '{ClaimedName}' (prefix={Prefix}, slot={Slot})",
                    "WorkerService", "_ClaimPrefixedWorkerName"
                )
                return ClaimedName
            finally:
                Cur.execute("SELECT pg_advisory_unlock(%s)", (LockId,))
                Conn.commit()
                Cur.close()
        except Exception as E:
            LoggingService.LogException(
                f"Failed to claim prefixed name for '{Prefix}', falling back to hostname",
                E, "WorkerService", "_ClaimPrefixedWorkerName"
            )
            return socket.gethostname()

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

            Version, BuildInfo = self._ResolveWorkerVersion()

            # Register worker (UPSERT - creates or updates)
            self.DatabaseManager.RegisterWorker(
                WorkerName=self.WorkerName,
                Platform=self.WorkerPlatform,
                FFmpegPath=FFmpegPath,
                FFprobePath=FFprobePath,
                MaxCpuThreads=MaxCpuThreads,
                Version=Version,
                BuildInfo=BuildInfo,
            )
            LoggingService.LogInfo(
                f"Worker '{self.WorkerName}' registered (ffmpeg={FFmpegPath}, ffprobe={FFprobePath}, threads={MaxCpuThreads}, version={Version})",
                "WorkerService", "_RegisterAndLoadWorkerConfig"
            )

            # StorageRootResolutions is operator-managed. The worker reads; it never writes.
            # Populate via Scripts/SQLScripts/SetWindowsWorkerUncPaths.py (Windows) or the
            # equivalent Linux deploy step. Missing rows for this worker is a hard error.
            ExistingSrrRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT s.Name FROM StorageRootResolutions r "
                "JOIN StorageRoots s ON r.StorageRootId = s.Id "
                "WHERE r.WorkerName = %s AND r.IsActive = TRUE",
                (self.WorkerName,)
            )
            if not ExistingSrrRows:
                Msg = (
                    f"No StorageRootResolutions rows for worker '{self.WorkerName}'. "
                    f"Populate via Scripts/SQLScripts/SetWindowsWorkerUncPaths.py "
                    f"(or the equivalent Linux deploy step) before starting the worker."
                )
                LoggingService.LogError(Msg, "WorkerService", "_RegisterAndLoadWorkerConfig")
                print(f"\n[FATAL] {Msg}\n", flush=True)
                sys.exit(1)
            ShareNames = sorted({(r.get('Name') or r.get('name')) for r in ExistingSrrRows})
            LoggingService.LogInfo(
                f"Worker '{self.WorkerName}' resolved shares: {', '.join(ShareNames)}",
                "WorkerService", "_RegisterAndLoadWorkerConfig"
            )

            # Load worker config from DB
            Config = self.DatabaseManager.GetWorkerConfig(self.WorkerName)
            if Config:
                LoggingService.LogInfo(
                    f"Worker config loaded: FFmpegPath={Config.get('FFmpegPath') or Config.get('ffmpegpath') or '(default)'}",
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

    def _ResolveWorkerVersion(self):
        """Read worker version from the deploy-stamped artifact. Returns (version, build_info_or_none).

        The VERSION file is written by the deploy script at deploy time -- never
        resolved live. If the file is missing or empty, returns "unknown" rather
        than guessing from a live source (e.g. git HEAD), so the displayed
        version never advances past the running code.

        BuildInfo is the contents of <repo>/BUILD_INFO when present, else None."""
        try:
            ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            VersionFile = os.path.join(ProjectRoot, "VERSION")
            BuildInfoFile = os.path.join(ProjectRoot, "BUILD_INFO")
            if os.path.exists(VersionFile):
                with open(VersionFile, "r", encoding="utf-8") as Fh:
                    Sha = Fh.read().strip()
                if Sha:
                    BuildInfo = None
                    if os.path.exists(BuildInfoFile):
                        with open(BuildInfoFile, "r", encoding="utf-8") as Fh:
                            BuildInfo = Fh.read()
                    return (Sha[:64], BuildInfo)
        except Exception as Ex:
            LoggingService.LogException("VERSION-file read failed", Ex, "WorkerService", "_ResolveWorkerVersion")

        return ("unknown", None)

    def _LoadCapabilitiesFromDB(self):
        """Load capability flags, concurrency settings, and status from Workers table."""
        try:
            Query = """
                SELECT TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled, Status,
                       MaxConcurrentTranscodeJobs, MaxConcurrentQualityTestJobs, MaxConcurrentRemuxJobs
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
                self.WorkerStatus = Row.get('Status', 'Paused') or 'Paused'
                # Per-capability concurrency (floor of 1, no ceiling -- operator sets what fits their hardware)
                RawTranscode = Row.get('MaxConcurrentTranscodeJobs')
                RawQualityTest = Row.get('MaxConcurrentQualityTestJobs')
                RawRemux = Row.get('MaxConcurrentRemuxJobs')
                self.CurrentTranscodeConcurrency = max(1, int(RawTranscode)) if RawTranscode else 1
                self.CurrentQualityTestConcurrency = max(1, int(RawQualityTest)) if RawQualityTest else 2
                self.CurrentRemuxConcurrency = max(1, int(RawRemux)) if RawRemux else 2
            else:
                LoggingService.LogWarning(f"No Workers row found for '{self.WorkerName}', using defaults", "WorkerService", "_LoadCapabilitiesFromDB")
                self.TranscodeEnabled = True
                self.QualityTestEnabled = False
                self.RemuxEnabled = True
                self.ScanEnabled = False
                self.WorkerStatus = "Paused"
                self.CurrentTranscodeConcurrency = 1
                self.CurrentQualityTestConcurrency = 2
                self.CurrentRemuxConcurrency = 2
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
            MaxJobs = self.CurrentTranscodeConcurrency
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
            MaxJobs = self.CurrentQualityTestConcurrency
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
            MaxJobs = self.CurrentRemuxConcurrency
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

    # --- Mount validation ---

    def _ValidateStorageMounts(self):
        """Verify every storage mount this worker depends on is present, readable,
        and contains data. Owns worker-lifecycle.feature.md criteria 20, 21.

        An empty mount point indicates the local filesystem showing through where
        an NFS / SMB share should be mounted -- the failure mode that destroyed
        wakko-worker-1's queue on 2026-05-14. Treat empty as broken.

        Returns list of (AbsolutePath, Reason) failures. Empty list = all mounts good.
        """
        Failures = []
        try:
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT AbsolutePath FROM StorageRootResolutions "
                "WHERE WorkerName = %s AND IsActive = TRUE",
                (self.WorkerName,)
            )
        except Exception as e:
            LoggingService.LogException(
                "Could not read StorageRootResolutions for mount validation",
                e, "WorkerService", "_ValidateStorageMounts"
            )
            return [("<unknown>", f"Could not query StorageRootResolutions: {e}")]

        if not Rows:
            return [("<none>", f"No active StorageRootResolutions rows for worker '{self.WorkerName}'")]

        for Row in Rows:
            Path = Row.get('AbsolutePath') or Row.get('absolutepath')
            if not Path:
                continue
            if not os.path.isdir(Path):
                Failures.append((Path, "mount point does not exist or is not a directory"))
                continue
            try:
                Entries = os.listdir(Path)
            except Exception as e:
                Failures.append((Path, f"mount point not readable: {e}"))
                continue
            if not Entries:
                Failures.append((Path, "mount point is empty (local filesystem showing through instead of mounted share)"))
        return Failures

    def _ApplyMountValidationResult(self, Failures) -> bool:
        """Persist mount-validation outcome to the Workers row and log loudly.
        Returns True if validation passed (Failures empty), False otherwise.
        On failure: forces Workers.Status='Paused' and writes a single-line
        summary into Workers.MountValidationError for UI surfacing.
        """
        if not Failures:
            self.DatabaseManager.SetWorkerMountValidationError(self.WorkerName, None)
            return True

        Reason = "; ".join(f"{P}: {R}" for P, R in Failures)
        for Path, Detail in Failures:
            LoggingService.LogError(
                f"Mount validation FAILED for worker '{self.WorkerName}': {Path} -- {Detail}",
                "WorkerService", "_ValidateStorageMounts"
            )
        self.DatabaseManager.SetWorkerMountValidationError(self.WorkerName, Reason)
        self.DatabaseManager.UpdateWorkerStatus(self.WorkerName, "Paused")
        self.WorkerStatus = "Paused"
        return False

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

            # Gate Online transition on storage-mount validation. A broken or
            # empty mount on a single worker can destroy queue state for every
            # file it claims, so this MUST fire before any capability starts.
            MountsOk = self._ApplyMountValidationResult(self._ValidateStorageMounts())

            # Respect the DB status -- if operator set Paused before restart,
            # stay Paused.  Only default to Online when the DB row has no
            # explicit status (first-ever start).
            if self.WorkerStatus == "Online" and MountsOk:
                self.DatabaseManager.UpdateWorkerStatus(self.WorkerName, "Online")
            elif not MountsOk:
                LoggingService.LogError(
                    f"Worker forced to Paused due to mount validation failure -- no jobs will be claimed until mounts are fixed",
                    "WorkerService", "Run"
                )
            else:
                LoggingService.LogInfo(
                    f"Worker DB status is '{self.WorkerStatus}', respecting it (not forcing Online)",
                    "WorkerService", "Run"
                )

            # Start health monitoring
            self._StartHealthMonitoring()

            # Start status polling (5s interval for status changes)
            self._StartStatusPolling()

            # Start capability polling (configurable interval, default 15s)
            self._StartCapabilityPolling()

            # Start recurring stuck-job detection (default 120s interval).
            # See stuck-job-detection.feature.md criterion 1.
            self._StartStuckJobDetection()

            # Start recurring orphan cleanup sweep (BUG-0001 criteria 16-18).
            # See Features/ServiceControl/orphan-cleanup.flow.md.
            self._StartOrphanCleanup()

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
        """Start or stop capabilities based on current DB flags.

        Master precondition (BUG-0004, capability-control-plane criterion 8):
        a non-Online Workers.Status blocks every capability uniformly. No
        capability may run while Status != 'Online' regardless of the
        per-capability *Enabled flag. Any running capability is signaled to
        stop; nothing is started.
        """
        if self.WorkerStatus != "Online":
            AnyRunning = (
                self.TranscodeService is not None
                or self.RemuxService is not None
                or self.QualityTestService is not None
                or self.ContinuousScanService is not None
            )
            if AnyRunning:
                LoggingService.LogInfo(
                    f"_ApplyCapabilities: Status={self.WorkerStatus} (not Online) -- stopping all capabilities",
                    "WorkerService", "_ApplyCapabilities"
                )
                self._StopAllCapabilities()
            return

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

    def _StartOrphanCleanup(self):
        """Start recurring orphan-cleanup sweep thread.

        Sibling to _StuckJobDetectionLoop, shares its interval setting
        (StuckJobDetectionIntervalSec, default 120). Owns the recurring
        half of BUG-0001 criteria 16, 17, 18.
        """
        try:
            self.OrphanCleanupThread = threading.Thread(
                target=self._OrphanCleanupLoop,
                daemon=True,
                name="OrphanCleanup",
            )
            self.OrphanCleanupThread.start()
            LoggingService.LogInfo("Orphan cleanup loop started", "WorkerService", "_StartOrphanCleanup")
        except Exception as e:
            LoggingService.LogException("Error starting orphan cleanup loop", e, "WorkerService", "_StartOrphanCleanup")

    def _OrphanCleanupLoop(self):
        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
        from Features.ServiceControl.OrphanCleanupService import OrphanCleanupService
        SettingsRepo = SystemSettingsRepository()

        def _ReadInterval():
            try:
                v = SettingsRepo.GetSystemSetting('StuckJobDetectionIntervalSec')
                return max(30, int(v)) if v is not None else 120
            except Exception:
                return 120

        # Initial wait so the first sweep doesn't race startup-time recovery.
        self.ShutdownEvent.wait(_ReadInterval())

        while not self.ShutdownEvent.is_set():
            try:
                Service = OrphanCleanupService(self.DatabaseManager.DatabaseService)
                Service.SweepOrphans()
            except Exception as e:
                LoggingService.LogException("Error in orphan cleanup cycle", e, "WorkerService", "_OrphanCleanupLoop")
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
                    NewStatus = Rows[0].get('Status', 'Paused') or 'Paused'
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
                # Re-validate mounts before resuming. Operator may have fixed
                # the host mount; we still cannot trust it without a check.
                if not self._ApplyMountValidationResult(self._ValidateStorageMounts()):
                    LoggingService.LogError(
                        f"Resume to Online blocked: mount validation failed. Worker remains Paused.",
                        "WorkerService", "_HandleStatusChange"
                    )
                    return
                # Came back online - start enabled capabilities
                LoggingService.LogInfo("Worker is Online, starting enabled capabilities", "WorkerService", "_HandleStatusChange")
                self._ApplyCapabilities()

            elif NewStatus == "Paused":
                LoggingService.LogInfo("Worker is Paused, signaling capabilities to stop claiming new work", "WorkerService", "_HandleStatusChange")
                self._StopAllCapabilities()

        except Exception as e:
            LoggingService.LogException("Error handling status change", e, "WorkerService", "_HandleStatusChange")

    def _StopAllCapabilities(self):
        """Immediately stop all running capabilities.
        Sets StopRequested synchronously on every processing loop BEFORE
        spawning cleanup threads, so no loop can claim a new job in the gap."""
        # Signal loops to stop IMMEDIATELY -- this prevents the race where
        # the background cleanup thread hasn't started yet but the processing
        # loop claims another job in the meantime.
        if self.TranscodeService is not None:
            self.TranscodeService.StopRequested = True
        if self.RemuxService is not None:
            self.RemuxService.StopRequested = True
        if self.QualityTestService is not None:
            try:
                self.QualityTestService.Stop()
            except Exception:
                pass

        # Now spawn background threads for graceful cleanup (thread joins, etc.)
        if self.TranscodeService is not None:
            threading.Thread(target=self._StopTranscodeCapability, daemon=True, name="StopTranscode").start()
        if self.QualityTestService is not None:
            threading.Thread(target=self._StopQualityTestCapability, daemon=True, name="StopQualityTest").start()
        if self.RemuxService is not None:
            threading.Thread(target=self._StopRemuxCapability, daemon=True, name="StopRemux").start()
        if self.ContinuousScanService is not None:
            self._StopScanCapability()

    def _LoadCapabilityPollingInterval(self) -> int:
        """Read CapabilityPollingIntervalSec from SystemSettings. Default 15."""
        try:
            Value = self.DatabaseManager.GetSystemSetting('CapabilityPollingIntervalSec')
            if Value:
                Parsed = int(Value)
                return max(5, min(120, Parsed))
        except Exception:
            pass
        return 15

    def _StartCapabilityPolling(self):
        """Start capability polling thread."""
        try:
            self.CapabilityPollingThread = threading.Thread(
                target=self._CapabilityPollingLoop,
                daemon=True,
                name="CapabilityPoller"
            )
            self.CapabilityPollingThread.start()
            LoggingService.LogInfo(f"Capability polling started ({self.CapabilityPollingIntervalSec}s interval)", "WorkerService", "_StartCapabilityPolling")
        except Exception as e:
            LoggingService.LogException("Error starting capability polling", e, "WorkerService", "_StartCapabilityPolling")

    def _CapabilityPollingLoop(self):
        """Poll Workers table for capability flag and concurrency changes."""
        while not self.ShutdownEvent.is_set():
            try:
                self.ShutdownEvent.wait(self.CapabilityPollingIntervalSec)
                if self.ShutdownEvent.is_set():
                    break

                # Only apply capability changes when Online
                if self.WorkerStatus != "Online":
                    continue

                OldTranscode = self.TranscodeEnabled
                OldQualityTest = self.QualityTestEnabled
                OldScan = self.ScanEnabled
                OldRemux = self.RemuxEnabled
                OldTranscodeConcurrency = self.CurrentTranscodeConcurrency
                OldQualityTestConcurrency = self.CurrentQualityTestConcurrency
                OldRemuxConcurrency = self.CurrentRemuxConcurrency

                self._LoadCapabilitiesFromDB()

                if (OldTranscode != self.TranscodeEnabled or
                        OldQualityTest != self.QualityTestEnabled or
                        OldRemux != self.RemuxEnabled or
                        OldScan != self.ScanEnabled):
                    LoggingService.LogInfo(
                        f"Capabilities changed: Transcode={OldTranscode}->{self.TranscodeEnabled}, "
                        f"QualityTest={OldQualityTest}->{self.QualityTestEnabled}, "
                        f"Remux={OldRemux}->{self.RemuxEnabled}, "
                        f"Scan={OldScan}->{self.ScanEnabled}",
                        "WorkerService", "_CapabilityPollingLoop"
                    )
                    self._ApplyCapabilities()

                # Apply concurrency changes to running services (no restart needed)
                self._ApplyConcurrencyChanges(
                    OldTranscodeConcurrency, OldQualityTestConcurrency, OldRemuxConcurrency
                )

            except Exception as e:
                LoggingService.LogException("Error in capability polling loop", e, "WorkerService", "_CapabilityPollingLoop")
                self.ShutdownEvent.wait(30)

    def _ApplyConcurrencyChanges(self, OldTranscode: int, OldQualityTest: int, OldRemux: int):
        """Update MaxConcurrentJobs on running service instances when DB values change."""
        if self.CurrentTranscodeConcurrency != OldTranscode and self.TranscodeService is not None:
            self.TranscodeService.MaxConcurrentJobs = self.CurrentTranscodeConcurrency
            LoggingService.LogInfo(
                f"Transcode concurrency changed: {OldTranscode} -> {self.CurrentTranscodeConcurrency}",
                "WorkerService", "_ApplyConcurrencyChanges"
            )

        if self.CurrentQualityTestConcurrency != OldQualityTest and self.QualityTestService is not None:
            self.QualityTestService.MaxConcurrentJobs = self.CurrentQualityTestConcurrency
            LoggingService.LogInfo(
                f"Quality test concurrency changed: {OldQualityTest} -> {self.CurrentQualityTestConcurrency}",
                "WorkerService", "_ApplyConcurrencyChanges"
            )

        if self.CurrentRemuxConcurrency != OldRemux and self.RemuxService is not None:
            self.RemuxService.MaxConcurrentJobs = self.CurrentRemuxConcurrency
            LoggingService.LogInfo(
                f"Remux concurrency changed: {OldRemux} -> {self.CurrentRemuxConcurrency}",
                "WorkerService", "_ApplyConcurrencyChanges"
            )

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

            # Do not change Workers.Status on shutdown -- heartbeat staleness
            # tells the UI the process is dead.  Preserving Status lets the
            # operator see "was Online but died" vs "was Paused and stopped".

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


# Drain budget: long enough for a typical in-flight transcode to finish.
# Bumped 2026-05-30 (P6) from 2s to 1800s so SIGTERM no longer kills mid-
# encode work. Docker's stop_grace_period in the compose templates must be
# >= this value or docker will SIGKILL the worker before drain completes.
_SIGNAL_BUDGET_SECONDS = 1800.0  # 30 minutes
_PER_INTERVAL_CHECK_SEC = 5.0


def SignalHandler(signum, frame):
    """Handle shutdown signals with a GRACEFUL DRAIN -- no SIGKILL on subprocesses.

    Contract (P6, .claude/programs/db-authority-program.md):
      On SIGTERM/SIGINT, signal every long-running operation to stop at its
      next safe boundary (via the existing `_StopAllCapabilities` path used
      by capability flag flips). Wait for the operation threads to drain.
      Then exit cleanly.

    Why this matters: the prior behavior called `Proc.kill()` on every active
    FFmpeg subprocess inline. Docker container restarts (deploy, compose
    recreate) were silently killing in-flight transcodes and VMAFs at any
    progress point, requiring operator recovery work afterward. The graceful
    path lets in-flight work complete (typical encode = 1-5 min wall;
    occasional long-form = 20-30 min).

    Re-entry from a second signal during drain forces immediate exit. So if
    the operator REALLY needs out, second Ctrl+C exits hard.
    """
    if getattr(SignalHandler, '_in_progress', False):
        # Operator sent a second signal while we were draining. Force exit.
        print("\nForcing exit (already draining)...")
        os._exit(1)
    SignalHandler._in_progress = True

    print(f"\nWorkerService received signal {signum}; draining in-flight work "
          f"(budget {_SIGNAL_BUDGET_SECONDS:.0f}s). Send another signal to force exit.")

    if not (hasattr(Main, 'app') and Main.app):
        # No app context yet -- nothing to drain.
        os._exit(0)
    App = Main.app

    # Step 1: signal every capability to stop at its next safe boundary.
    # _StopAllCapabilities sets StopRequested synchronously on each service
    # AND spawns daemon threads that do the actual join+cleanup (which can
    # take minutes if an encode is in flight). We don't block here on those
    # threads -- we wait below by polling for the services to clear.
    try:
        App._StopAllCapabilities()
        print("  drain signal sent to all capabilities")
    except Exception as e:
        try:
            LoggingService.LogException(
                "Error signalling capabilities to stop during SignalHandler",
                e, "SignalHandler", "WorkerService",
            )
        except Exception:
            print(f"  EXCEPTION signalling drain (logger unavailable): {e}")

    # Step 2: wait for capabilities to actually drain. Each long-running
    # operation checks its StopRequested flag at safe boundaries and exits;
    # the corresponding cleanup thread joins on the processing thread.
    # We poll the App-level service handles -- they go None when their
    # cleanup thread completes.
    import time as _time
    Start = _time.time()
    while _time.time() - Start < _SIGNAL_BUDGET_SECONDS:
        Active = []
        if getattr(App, 'TranscodeService', None) is not None: Active.append('transcode')
        if getattr(App, 'RemuxService', None) is not None: Active.append('remux')
        if getattr(App, 'QualityTestService', None) is not None: Active.append('quality-test')
        if getattr(App, 'ContinuousScanService', None) is not None: Active.append('scan')
        if not Active:
            print(f"  drain complete in {_time.time() - Start:.0f}s")
            break
        Elapsed = int(_time.time() - Start)
        print(f"  draining: {','.join(Active)} still active ({Elapsed}s elapsed)")
        _time.sleep(_PER_INTERVAL_CHECK_SEC)
    else:
        print(f"  drain budget exceeded; forcing exit with capabilities still active")

    # Step 2: do potentially-slow DB cleanup in a background thread with a hard
    # budget. Status is left untouched -- heartbeat staleness tells the UI
    # the process died; preserving the last operational state is intentional.
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
                except Exception as e:
                    try:
                        LoggingService.LogException(
                            f"Error updating ServiceStatus during SignalHandler",
                            e, "SignalHandler", "WorkerService"
                        )
                    except Exception:
                        print(f"EXCEPTION (logger unavailable): updating ServiceStatus: {e}")
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

    # DB cleanup is fast (single UPDATE + pool close); give it a short budget
    # independent of the (much longer) drain budget above.
    _CLEANUP_BUDGET_SECONDS = 5.0
    CleanupThread = threading.Thread(target=_DeferredCleanup, name="ShutdownCleanup", daemon=True)
    CleanupThread.start()
    CleanupThread.join(timeout=_CLEANUP_BUDGET_SECONDS)

    # Step 3: exit -- whether cleanup finished, timed out, or threw, the
    # process must terminate now so the operator's Ctrl+C is honored.
    os._exit(0)


def _VerifyRequiredPaths():
    """Hard-fail at startup if media share paths the queue references are not accessible.

    On Windows, prefers this worker's StorageRootResolutions rows (the per-worker
    AbsolutePath for each share) over the drive-letter prefix from MediaFiles.FilePath.
    When AbsolutePath is a UNC string (`\\\\host\\share\\...`), the check is reachability
    via os.path.exists on the UNC root -- the share is accessible regardless of whether
    any drive letter happens to be bound in this session. This decouples the worker from
    drive-letter session-binding flakiness on the Microsoft NFS client (BUG-0008).

    Legacy fallback: if no StorageRootResolutions rows exist for this worker (pre-fix
    state), falls back to the original drive-letter prefix scan of MediaFiles.

    On non-Windows platforms, bind mounts are the responsibility of the container
    orchestration layer and this check is skipped."""
    if platform_mod.system().lower() != 'windows':
        return

    WorkerName = (os.environ.get('MEDIAVORTEX_WORKER_NAME') or socket.gethostname()).strip()

    try:
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
    except Exception as Ex:
        print(f"[FATAL] Could not connect to DB to verify required paths: {Ex}", flush=True)
        sys.exit(1)

    try:
        ResolutionRows = Db.ExecuteQuery(
            "SELECT s.Name AS ShareName, r.AbsolutePath FROM StorageRootResolutions r "
            "JOIN StorageRoots s ON r.StorageRootId = s.Id "
            "WHERE r.WorkerName = %s AND r.IsActive = TRUE",
            (WorkerName,)
        )
    except Exception as Ex:
        print(f"[FATAL] Could not read StorageRootResolutions for {WorkerName}: {Ex}", flush=True)
        sys.exit(1)

    if ResolutionRows:
        Missing = []
        for Row in ResolutionRows:
            Path = Row.get('AbsolutePath') or Row.get('absolutepath')
            Name = Row.get('ShareName') or Row.get('sharename')
            if not Path:
                continue
            if not os.path.exists(Path):
                Missing.append(f"{Name} ({Path})")

        if Missing:
            Msg = (f"Required shares not accessible for {WorkerName}: {', '.join(sorted(Missing))}. "
                   f"Check NFS server reachability and the StorageRootResolutions rows.")
            print(f"\n[FATAL] {Msg}\n", flush=True)
            try:
                LoggingService.LogError(Msg, "WorkerService", "_VerifyRequiredPaths")
            except Exception:
                pass
            sys.exit(1)
        return

    # Legacy fallback: no StorageRootResolutions rows for this worker. Use the
    # original drive-letter prefix scan of MediaFiles. Keeps a pre-BUG-0008-fix
    # I9 startup working until the data migration is applied.
    try:
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
