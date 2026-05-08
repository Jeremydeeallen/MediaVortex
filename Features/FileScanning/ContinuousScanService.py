import os
import threading
import time
from typing import Dict, Any, List
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService


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
                'LastScanTime': self.LastScanTime.isoformat() if self.LastScanTime else None,
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
                    Duration = datetime.now(timezone.utc) - ScanResults.ScanStartTime
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

    def _ScanLoop(self):
        """Background thread loop for periodic scanning."""
        try:
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
        """
        # Normalize all paths for comparison
        NormalizedFolders = []
        for Folder in RootFolders:
            NormPath = os.path.normpath(Folder.RootFolder).lower()
            if not NormPath.endswith(os.sep):
                NormPath += os.sep
            NormalizedFolders.append((NormPath, Folder))

        # Sort by path length so parents come before children
        NormalizedFolders.sort(key=lambda x: len(x[0]))

        TopLevel = []
        CoveredPrefixes = []

        for NormPath, Folder in NormalizedFolders:
            # Check if this path is already covered by a previously accepted parent
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

            # Run duplicate cleanup once before the loop instead of per-folder
            try:
                if not self.FileScanningService:
                    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
                    self.FileScanningService = FileScanningBusinessService()
                CleanupResult = self.FileScanningService.Repository.CleanupDuplicateMediaFiles()
                if CleanupResult.get('DuplicatesRemoved', 0) > 0:
                    LoggingService.LogInfo(f"Pre-scan cleanup removed {CleanupResult['DuplicatesRemoved']} duplicate records", 'ContinuousScanService', '_ExecuteScan')
            except Exception as e:
                LoggingService.LogException("Error during pre-scan duplicate cleanup", e, 'ContinuousScanService', '_ExecuteScan')

            # Scan each top-level root folder
            for RootFolder in TopLevelFolders:
                if self.StopEvent.is_set():
                    LoggingService.LogInfo("Stop event received during scan, aborting", 'ContinuousScanService', '_ExecuteScan')
                    break

                try:
                    # Check if root folder exists
                    if not os.path.exists(RootFolder.RootFolder):
                        LoggingService.LogWarning(f"Root folder does not exist, skipping: {RootFolder.RootFolder}", 'ContinuousScanService', '_ExecuteScan')
                        continue

                    # Import FileScanningBusinessService to trigger scan
                    if not self.FileScanningService:
                        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
                        self.FileScanningService = FileScanningBusinessService()

                    # Check if we can start a new scan (respects concurrent scan limits)
                    if not self.FileScanningService.CanStartNewScan():
                        LoggingService.LogWarning("Cannot start new scan (max concurrent scans reached), skipping this interval", 'ContinuousScanService', '_ExecuteScan')
                        break

                    LoggingService.LogInfo(f"Starting scan for root folder: {RootFolder.RootFolder}", 'ContinuousScanService', '_ExecuteScan')

                    # Trigger scan for this root folder (skip duplicate cleanup - already ran once above)
                    ScanResult = self.FileScanningService.StartScanning(RootFolder.RootFolder, Recursive=True, SkipDuplicateCleanup=True)

                    if ScanResult.get('Success'):
                        LoggingService.LogInfo(f"Scan completed successfully for: {RootFolder.RootFolder}", 'ContinuousScanService', '_ExecuteScan')
                    else:
                        LoggingService.LogError(f"Scan failed for {RootFolder.RootFolder}: {ScanResult.get('ErrorMessage')}", 'ContinuousScanService', '_ExecuteScan')

                except Exception as e:
                    LoggingService.LogException(f"Error scanning root folder: {RootFolder.RootFolder}", e, 'ContinuousScanService', '_ExecuteScan')
                    continue

            # Update scan statistics
            self.LastScanTime = datetime.now(timezone.utc)
            self.ScanCount += 1

            LoggingService.LogInfo(f"=== CONTINUOUS SCAN ITERATION COMPLETED === Total scans: {self.ScanCount}", 'ContinuousScanService', '_ExecuteScan')

        except Exception as e:
            LoggingService.LogException("Error executing scan", e, 'ContinuousScanService', '_ExecuteScan')

    def CanStartNewScan(self) -> bool:
        """Check if a new scan can be started (delegates to FileScanningBusinessService)."""
        try:
            if not self.FileScanningService:
                from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
                self.FileScanningService = FileScanningBusinessService()

            return self.FileScanningService.CanStartNewScan()

        except Exception as e:
            LoggingService.LogException("Error checking if new scan can start", e, 'ContinuousScanService', 'CanStartNewScan')
            return False
