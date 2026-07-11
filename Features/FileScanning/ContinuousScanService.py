import os
import threading
import time
from typing import Dict, Any, List
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.DateTimeHelpers import AsAwareUtc, ToUtcIsoZ
from Core.Path.LocalPath import LocalIsDir


class ContinuousScanService:
    """Background service for continuous/periodic file scanning."""

    def __init__(self, FileScanningBusinessService=None):
        """Initialize the continuous scan service."""
        self.IsRunning = False
        self.ScanThread = None
        self.ScanIntervalMinutes = 60  # Default: scan every hour
        self.StopEvent = threading.Event()
        self.FileScanningService = FileScanningBusinessService
        self.LastScanTime = None
        self.ScanCount = 0

        LoggingService.LogInfo("ContinuousScanService initialized", 'ContinuousScanService', '__init__')

    def StartContinuousScanning(self, IntervalMinutes: int = 60) -> Dict[str, Any]:
        """Start continuous scanning with specified interval."""
        try:
            LoggingService.LogInfo(f"Starting continuous scanning with {IntervalMinutes} minute interval", 'ContinuousScanService', 'StartContinuousScanning')

            if self.IsRunning:
                LoggingService.LogWarning("Continuous scanning is already running", 'ContinuousScanService', 'StartContinuousScanning')
                return {
                    'Success': False,
                    'ErrorMessage': 'Continuous scanning is already running'
                }

            # Validate interval
            if IntervalMinutes < 1:
                LoggingService.LogError(f"Invalid interval: {IntervalMinutes} minutes", 'ContinuousScanService', 'StartContinuousScanning')
                return {
                    'Success': False,
                    'ErrorMessage': 'Interval must be at least 1 minute'
                }

            self.ScanIntervalMinutes = IntervalMinutes
            self.IsRunning = True
            self.StopEvent.clear()

            # Start background thread
            self.ScanThread = threading.Thread(target=self._ScanLoop, daemon=True, name="ContinuousScanThread")
            self.ScanThread.start()

            LoggingService.LogInfo(f"Continuous scanning started successfully with {IntervalMinutes} minute interval", 'ContinuousScanService', 'StartContinuousScanning')

            return {
                'Success': True,
                'Message': f'Continuous scanning started with {IntervalMinutes} minute interval',
                'IntervalMinutes': IntervalMinutes
            }

        except Exception as e:
            LoggingService.LogException("Error starting continuous scanning", e, 'ContinuousScanService', 'StartContinuousScanning')
            self.IsRunning = False
            return {
                'Success': False,
                'ErrorMessage': str(e)
            }

    def StopContinuousScanning(self, StopCurrentScan: bool = True) -> Dict[str, Any]:
        """Stop continuous scanning gracefully and optionally stop any current running scan."""
        try:
            LoggingService.LogInfo("Stopping continuous scanning", 'ContinuousScanService', 'StopContinuousScanning')

            if not self.IsRunning:
                LoggingService.LogWarning("Continuous scanning is not running", 'ContinuousScanService', 'StopContinuousScanning')
                return {
                    'Success': False,
                    'ErrorMessage': 'Continuous scanning is not running'
                }

            # Stop any currently running scan if requested
            if StopCurrentScan and self.FileScanningService:
                try:
                    LoggingService.LogInfo("Stopping current running scan", 'ContinuousScanService', 'StopContinuousScanning')
                    StopResult = self.FileScanningService.StopScanning()
                    if StopResult.get('Success'):
                        LoggingService.LogInfo("Current scan stopped successfully", 'ContinuousScanService', 'StopContinuousScanning')
                    else:
                        LoggingService.LogWarning(f"Could not stop current scan: {StopResult.get('Message')}", 'ContinuousScanService', 'StopContinuousScanning')
                except Exception as e:
                    LoggingService.LogWarning(f"Error stopping current scan: {e}", 'ContinuousScanService', 'StopContinuousScanning')

            # Signal the thread to stop
            self.StopEvent.set()
            self.IsRunning = False

            # Wait for thread to finish (with timeout)
            if self.ScanThread and self.ScanThread.is_alive():
                self.ScanThread.join(timeout=10)

            LoggingService.LogInfo("Continuous scanning stopped successfully", 'ContinuousScanService', 'StopContinuousScanning')

            return {
                'Success': True,
                'Message': 'Continuous scanning stopped successfully',
                'TotalScansPerformed': self.ScanCount
            }

        except Exception as e:
            LoggingService.LogException("Error stopping continuous scanning", e, 'ContinuousScanService', 'StopContinuousScanning')
            return {
                'Success': False,
                'ErrorMessage': str(e)
            }

    def GetStatus(self) -> Dict[str, Any]:
        """Get the current status of continuous scanning with real-time scan statistics."""
        try:
            # Base status
            Status = {
                'Success': True,
                'IsRunning': self.IsRunning,
                'IntervalMinutes': self.ScanIntervalMinutes,
                'LastScanTime': ToUtcIsoZ(self.LastScanTime),
                'TotalScansPerformed': self.ScanCount,
                'ThreadAlive': self.ScanThread.is_alive() if self.ScanThread else False
            }

            # Add real-time scan statistics if FileScanningService is available
            if self.FileScanningService:
                ScanResults = self.FileScanningService.ScanResults
                IsScanning = self.FileScanningService.IsScanning

                Status['IsScanning'] = IsScanning
                Status['TotalFilesFound'] = ScanResults.TotalFilesFound
                Status['TotalFilesProcessed'] = ScanResults.TotalFilesProcessed
                Status['TotalFilesSkipped'] = ScanResults.TotalFilesSkipped
                Status['TotalFilesWithErrors'] = ScanResults.TotalFilesWithErrors

                # Calculate scan duration
                if IsScanning and ScanResults.ScanStartTime:
                    Duration = datetime.now(timezone.utc) - AsAwareUtc(ScanResults.ScanStartTime)
                    Status['CurrentScanDuration'] = str(Duration).split('.')[0]  # Remove microseconds
                else:
                    Status['CurrentScanDuration'] = None

                # Calculate "changed" files (processed - skipped = files that were actually changed/new)
                FilesChanged = ScanResults.TotalFilesProcessed
                Status['FilesChanged'] = FilesChanged
            else:
                # No scan service available yet
                Status['IsScanning'] = False
                Status['TotalFilesFound'] = 0
                Status['TotalFilesProcessed'] = 0
                Status['TotalFilesSkipped'] = 0
                Status['TotalFilesWithErrors'] = 0
                Status['CurrentScanDuration'] = None
                Status['FilesChanged'] = 0

            return Status

        except Exception as e:
            LoggingService.LogException("Error getting continuous scan status", e, 'ContinuousScanService', 'GetStatus')
            return {
                'Success': False,
                'ErrorMessage': str(e)
            }

    # directive: transcode-flow-canonical
    def _ScanLoop(self):
        """Background thread loop for periodic scanning."""
        try:
            from Core.WorkerContext import WorkerContext
            WorkerContext.Bind()
            LoggingService.LogInfo("Continuous scan loop started", 'ContinuousScanService', '_ScanLoop')

            # Execute first scan immediately upon starting
            if not self.StopEvent.is_set():
                LoggingService.LogInfo("Executing initial scan immediately", 'ContinuousScanService', '_ScanLoop')
                self._ExecuteScan()

            # Then wait and scan periodically
            while not self.StopEvent.is_set():
                try:
                    # Wait for the interval before next scan (interruptible by StopEvent)
                    WaitSeconds = self.ScanIntervalMinutes * 60
                    LoggingService.LogInfo(f"Waiting {self.ScanIntervalMinutes} minutes before next scan", 'ContinuousScanService', '_ScanLoop')

                    # Use StopEvent.wait() instead of time.sleep() for interruptible waiting
                    if self.StopEvent.wait(timeout=WaitSeconds):
                        # StopEvent was set, exit loop
                        LoggingService.LogInfo("Stop event received, exiting scan loop", 'ContinuousScanService', '_ScanLoop')
                        break

                    # Execute scan if not stopped
                    if not self.StopEvent.is_set():
                        self._ExecuteScan()

                except Exception as e:
                    LoggingService.LogException("Error in scan loop iteration", e, 'ContinuousScanService', '_ScanLoop')
                    # Continue loop even if individual scan fails
                    continue

            LoggingService.LogInfo("Continuous scan loop terminated", 'ContinuousScanService', '_ScanLoop')

        except Exception as e:
            LoggingService.LogException("Critical error in scan loop", e, 'ContinuousScanService', '_ScanLoop')
            self.IsRunning = False

    def _GetTopLevelFolders(self, RootFolders) -> list:
        """Filter root folders to only top-level paths, removing children covered by a parent's recursive scan.

        If both T:\\ and T:\\Ted Lasso are root folders, scanning T:\\ recursively
        already covers T:\\Ted Lasso, so we skip the child to avoid redundant work.

        Directive 2026-05-27 (scan -- largest files first) criterion 6: the dedup
        must work on Windows-style canonical paths regardless of host OS. The prior
        implementation used `os.path.normpath` + `os.sep`, which on Linux workers
        treats `T:\\30 Rock` as a single filename and never collapses it under `T:\\`
        -- result: three Linux workers all pile on T:\\ subfolders, M:\\ and Z:\\
        never get scanned. Fix: dedup directly on the canonical backslash form.
        """
        # directive: path-class-perfection | # see path.C23
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPM_NF
        _PmNF = _GPM_NF()
        NormalizedFolders = []
        for Folder in RootFolders:
            _FolderP = Folder.Path
            NormPath = (_FolderP.CanonicalDisplay(_PmNF) if _FolderP is not None else '').strip()
            while '\\\\' in NormPath:
                NormPath = NormPath.replace('\\\\', '\\')
            NormPath = NormPath.lower()
            if not NormPath.endswith('\\'):
                NormPath += '\\'
            NormalizedFolders.append((NormPath, Folder))

        # Sort by path length so parents come before children. Stable on ties.
        NormalizedFolders.sort(key=lambda x: len(x[0]))

        TopLevel = []
        CoveredPrefixes = []

        for NormPath, Folder in NormalizedFolders:
            IsCovered = any(NormPath.startswith(Prefix) for Prefix in CoveredPrefixes)
            if not IsCovered:
                TopLevel.append(Folder)
                CoveredPrefixes.append(NormPath)

        return TopLevel

    def _ExecuteScan(self):
        """Execute a single scan iteration."""
        try:
            LoggingService.LogInfo("=== CONTINUOUS SCAN ITERATION STARTED ===", 'ContinuousScanService', '_ExecuteScan')

            # Import here to avoid circular dependencies
            from Features.FileScanning.FileScanningRepository import FileScanningRepository

            Repository_Instance = FileScanningRepository()

            # Get all root folders from database
            RootFolders = Repository_Instance.GetAllRootFolders()

            if not RootFolders:
                LoggingService.LogWarning("No root folders found in database, skipping scan", 'ContinuousScanService', '_ExecuteScan')
                return

            # Deduplicate: if a parent folder is in the list, skip children it covers
            TopLevelFolders = self._GetTopLevelFolders(RootFolders)
            SkippedCount = len(RootFolders) - len(TopLevelFolders)

            LoggingService.LogInfo(
                f"Found {len(RootFolders)} root folders, scanning {len(TopLevelFolders)} top-level paths (skipping {SkippedCount} already covered by parent folders)",
                'ContinuousScanService', '_ExecuteScan'
            )

            # directive: transcode-flow-canonical
            from Core.WorkerContext import WorkerContext
            ThisWorkerName = WorkerContext.Current().WorkerName

            # Apply per-rootfolder host affinity. RootFolders.PreferredWorkerName=NULL means
            # any ScanEnabled worker may pick it up; a non-null value pins the rootfolder to
            # the named worker (e.g. larry-worker-1 has the fast backplane to porky).
            EligibleFolders = []
            SkippedAffinity = 0
            for Folder in TopLevelFolders:
                Preferred = getattr(Folder, 'PreferredWorkerName', None)
                if Preferred and Preferred != ThisWorkerName:
                    SkippedAffinity += 1
                    continue
                EligibleFolders.append(Folder)
            if SkippedAffinity > 0:
                LoggingService.LogInfo(
                    f"Worker {ThisWorkerName} skipping {SkippedAffinity} root folder(s) pinned to other workers; will scan {len(EligibleFolders)}",
                    'ContinuousScanService', '_ExecuteScan'
                )

            # Run duplicate cleanup once before the loop instead of per-folder
            try:
                if not self.FileScanningService:
                    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
                    self.FileScanningService = FileScanningBusinessService()
                # directive: path-schema-migration | # see path.S8 -- CleanupDuplicateMediaFiles lives on MediaFilesRepository
                from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
                CleanupResult = MediaFilesRepository(self.FileScanningService.Repository.DatabaseService).CleanupDuplicateMediaFiles()
                if CleanupResult.get('DuplicatesRemoved', 0) > 0:
                    LoggingService.LogInfo(f"Pre-scan cleanup removed {CleanupResult['DuplicatesRemoved']} duplicate records", 'ContinuousScanService', '_ExecuteScan')
            except Exception as e:
                LoggingService.LogException("Error during pre-scan duplicate cleanup", e, 'ContinuousScanService', '_ExecuteScan')

            # directive: path-class-perfection | # see path.C18
            from Core.Path.Path import Path as _PathCS, PathError as _PECS
            from Core.Path.PathStorageRoots import GetStorageRoots as _GSRCS, GetPrefixMap as _GPMCS
            from Core.Path.Worker import Worker as _WCS
            _SrsCS = _GSRCS()
            _PmCS = _GPMCS()
            _WkCS = _WCS.Current()

            for RootFolder in EligibleFolders:
                if self.StopEvent.is_set():
                    LoggingService.LogInfo("Stop event received during scan, aborting", 'ContinuousScanService', '_ExecuteScan')
                    break

                # directive: path-class-perfection | # see path.C23
                _RfP = RootFolder.Path
                if _RfP is None:
                    continue
                _RfDisplay = _RfP.CanonicalDisplay(_PmCS)
                try:
                    try:
                        LocalRootPath = _PathCS.FromLegacyString(_RfDisplay, _SrsCS).Resolve(_WkCS)
                    except _PECS:
                        LocalRootPath = _RfDisplay
                    ValidationError = None
                    if not LocalIsDir(LocalRootPath):
                        ValidationError = "not a directory"
                    else:
                        try:
                            if not any(True for _ in os.scandir(LocalRootPath)):
                                ValidationError = "empty (mount point but no contents -- broken share?)"
                        except OSError as ListErr:
                            ValidationError = f"unreadable: {ListErr}"
                    if ValidationError:
                        ErrorMsg = f"Path not accessible: {_RfDisplay} -> {LocalRootPath} ({ValidationError})"
                        LoggingService.LogWarning(f"Pre-scan validation failed, recording ScanJobs failure: {ErrorMsg}", 'ContinuousScanService', '_ExecuteScan')
                        self._RecordPathValidationFailure(_RfDisplay, ThisWorkerName, ErrorMsg)
                        continue

                    if not self.FileScanningService:
                        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
                        self.FileScanningService = FileScanningBusinessService()

                    LoggingService.LogInfo(f"Starting scan for root folder: {_RfDisplay}", 'ContinuousScanService', '_ExecuteScan')

                    ScanResult = self.FileScanningService.StartScanning(
                        _RfDisplay,
                        Recursive=True,
                        SkipDuplicateCleanup=True,
                        WorkerName=ThisWorkerName,
                    )

                    if ScanResult.get('Success'):
                        LoggingService.LogInfo(f"Scan completed successfully for: {_RfDisplay}", 'ContinuousScanService', '_ExecuteScan')
                    elif ScanResult.get('Error') == 'ScanAlreadyRunning':
                        LoggingService.LogInfo(f"Skipping {_RfDisplay}: scan already running on another worker", 'ContinuousScanService', '_ExecuteScan')
                    else:
                        LoggingService.LogError(f"Scan failed for {_RfDisplay}: {ScanResult.get('Message') or ScanResult.get('ErrorMessage')}", 'ContinuousScanService', '_ExecuteScan')

                except Exception as e:
                    LoggingService.LogException(f"Error scanning root folder: {_RfDisplay}", e, 'ContinuousScanService', '_ExecuteScan')
                    continue

            # Update scan statistics
            self.LastScanTime = datetime.now(timezone.utc)
            self.ScanCount += 1

            LoggingService.LogInfo(f"=== CONTINUOUS SCAN ITERATION COMPLETED === Total scans: {self.ScanCount}", 'ContinuousScanService', '_ExecuteScan')

        except Exception as e:
            LoggingService.LogException("Error executing scan", e, 'ContinuousScanService', '_ExecuteScan')

    def _RecordPathValidationFailure(self, RootFolderPath: str, WorkerName: str, ErrorMessage: str):
        """Write a ScanJobs row with Status='Failed' for a path that failed pre-scan validation.

        Criterion 20: makes path-resolution failures visible in the /Scanning page's
        scan history and the /Activity page's recent-scans panel.
        """
        try:
            import uuid
            from Core.Database.DatabaseService import DatabaseService
            from Core.Path.Path import Path, PathError
            from Core.Path.PathStorageRoots import GetStorageRoots
            Db = DatabaseService()
            Now = datetime.now(timezone.utc)
            JobId = str(uuid.uuid4())
            try:
                Parsed = Path.FromLegacyString(RootFolderPath, GetStorageRoots())
                Sid, Rel = Parsed.StorageRootId, Parsed.RelativePath
            except PathError:
                Sid, Rel = None, None
            # directive: path-perfect-implementation | # see filescanning.S1
            Query = (
                "INSERT INTO ScanJobs (JobId, StorageRootId, RelativePath, Recursive, Status, StartTime, EndTime, "
                "LastUpdated, ScanType, WorkerName, ErrorMessage) "
                "VALUES (%s, %s, %s, TRUE, 'Failed', %s, %s, %s, 'File', %s, %s)"
            )
            Db.ExecuteNonQuery(Query, (JobId, Sid, Rel, Now, Now, Now, WorkerName, ErrorMessage))
        except Exception as e:
            LoggingService.LogException("Error recording path validation failure", e, 'ContinuousScanService', '_RecordPathValidationFailure')

