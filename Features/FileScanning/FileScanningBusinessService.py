import os
import ntpath
import uuid
import re
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path as PyPath
from concurrent.futures import ThreadPoolExecutor, as_completed
from Features.FileScanning.Models.RootFolderModel import RootFolderModel
from Core.Models.MediaFileModel import MediaFileModel
from Features.FileScanning.Models.SeasonModel import SeasonModel
from Features.FileScanning.Models.FileScanResultModel import FileScanResultModel
from Services.FileManagerService import FileManagerService
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError
from Core.Path.LocalPath import (
    LocalBasename, LocalDirname, LocalSplitExt, LocalJoin,
    LocalExists, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime,
)


# directive: path-class-perfection | # see path.C21
_FS_WORKER_HOLDER: dict = {"_Worker": None}


def _GetWorker() -> Worker:
    """Module-level lazy Worker. Worker holds only Name + Platform from the process-singleton WorkerContext; no DB read at construction; per-call resolves go through Worker.ResolveStorageRoot which is DB-fresh."""
    if _FS_WORKER_HOLDER["_Worker"] is None:
        _FS_WORKER_HOLDER["_Worker"] = Worker.FromWorkerContext()
    return _FS_WORKER_HOLDER["_Worker"]


# directive: path-class-perfection | # see path.C18
def _GetStorageRoots() -> List[dict]:
    """Fresh-per-call StorageRoots prefix list; delegates to Core.Path.PathStorageRoots (no module cache; db-is-authority)."""
    from Core.Path.PathStorageRoots import GetStorageRoots
    return GetStorageRoots()


# directive: filescanning-uses-path | # see path.S5
def _CanonicalToPath(CanonicalValue: str) -> Optional[Path]:
    """Build a v2 Path from a canonical-style legacy string; returns None on parse failure."""
    if not CanonicalValue:
        return None
    try:
        return Path.FromLegacyString(CanonicalValue, _GetStorageRoots())
    except PathError:
        return None


# directive: path-class-perfection | # see path.C21
def _CanonicalExists(CanonicalValue: str) -> bool:
    from Core.Path.PathFs import Exists as _FsExists
    P = _CanonicalToPath(CanonicalValue)
    return False if P is None else _FsExists(P, _GetWorker())


# directive: path-class-perfection | # see path.C21
def _CanonicalGetSize(CanonicalValue: str) -> int:
    from Core.Path.PathFs import GetSize as _FsGetSize
    P = _CanonicalToPath(CanonicalValue)
    if P is None:
        raise PathError(f"_CanonicalGetSize: cannot parse canonical {CanonicalValue!r}")
    return _FsGetSize(P, _GetWorker())


# directive: paths-canonical-completion
def _CurrentWorkerName():
    # see filescanning.ST1
    """Resolve the active WorkerName from WorkerContext (None if not set)."""
    try:
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        return Ctx.WorkerName if Ctx and Ctx.WorkerName else None
    except Exception:
        return None


# directive: paths-canonical-completion
class FileScanningBusinessService:
    """Orchestrates the file scanning process and coordinates between services."""
    # see filescanning.ST1

    # directive: paths-canonical-completion
    def __init__(self, RepositoryInstance=None, FileManagerInstance=None):
        # see filescanning.ST1
        self.Repository = RepositoryInstance or FileScanningRepository()
        self.FileManager = FileManagerInstance or FileManagerService()
        self.MediaProbeService = MediaProbeBusinessService()
        self.CurrentJobId = None
        self.ScanProgress = 0.0
        self.ScanResults = FileScanResultModel()
        self.ScanErrors = []
        self.IsScanning = False
        self.CurrentScanDirectory = ""
        # Directive 2026-05-27: phase visibility + soft-stop on Activity page.
        # _CurrentPhase mirrors ScanJobs.Phase so the heartbeat re-asserts it.
        # _StopRequested is flipped by the heartbeat when it observes
        # ScanJobs.Status='Stopping' (set by POST /api/FileScanning/Scan/<JobId>/Stop)
        # so the per-file/per-probe loops can exit cleanly to 'Stopped'.
        self._CurrentPhase = None
        self._FilesNeedingProbe = None
        self._ProbedFiles = None
        self._StopRequested = False

        # Pick up CurrentJobId if a scan is already running (so StopScanning
        # can target it). Single repository call -- the eight is-running
        # wrappers were retired with criterion 18b.
        try:
            running = self.Repository.GetRunningScans()
            if running:
                self.CurrentJobId = running[-1].get('JobId')
                LoggingService.LogInfo(f"Found existing running scan: JobId={self.CurrentJobId}", 'FileScanningBusinessService', '__init__')
        except Exception as Ex:
            LoggingService.LogException("Error checking existing scans on init", Ex, 'FileScanningBusinessService', '__init__')

    # directive: path-perfect-implementation | # see path.S11
    def _ToLocalPath(self, CanonicalPath: str) -> str:
        try:
            from Core.Path.Path import Path as _Path, PathError as _PE
            from Core.Path.PathStorageRoots import GetStorageRoots as _GSR
            from Core.Path.Worker import Worker as _W
            return _Path.FromLegacyString(CanonicalPath, _GSR()).Resolve(_W.FromWorkerContext(Db=self.Repository.DatabaseService))
        except Exception:
            return CanonicalPath

    # directive: path-perfect-implementation | # see path.S11
    def _ToCanonicalPath(self, LocalPath: str) -> str:
        try:
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPM
            from Core.Path.Worker import Worker as _W
            P = _W.FromWorkerContext(Db=self.Repository.DatabaseService).LocalToPath(LocalPath)
            if P is None:
                return LocalPath
            return P.CanonicalDisplay(_GPM())
        except Exception:
            return LocalPath

    # directive: paths-canonical-completion
    def StartScanning(self, RootFolderPath: str, Recursive: bool = True, SkipDuplicateCleanup: bool = False, WorkerName: Optional[str] = None) -> Dict[str, Any]:
        # see filescanning.ST1
        """Start scanning a root folder; see filescanning.ST1 for stage detail."""
        try:
            LoggingService.LogFunctionEntry("StartScanning", 'FileScanningBusinessService', RootFolderPath, Recursive=Recursive)

            if WorkerName is None:
                try:
                    from Core.WorkerContext import WorkerContext
                    Ctx = WorkerContext.Current()
                    if Ctx is not None:
                        WorkerName = Ctx.WorkerName
                except Exception:
                    pass

            # Per-rootfolder claim guard (criterion 11): refuse a duplicate scan
            # when another worker (or this one) already has a Pending/Running
            # ScanJobs row for this path. Prevents two ScanEnabled workers from
            # racing when their continuous-scan ticks land in the same window.
            # Global concurrency cap removed with criterion 18c -- it
            # contradicted the per-rootfolder claim semantics.
            if self.Repository.GetRunningScans(RootFolderPath):
                return {
                    'Success': False,
                    'Message': f'Scan already running for {RootFolderPath}',
                    'Error': 'ScanAlreadyRunning'
                }

            # Validate the root folder path with detailed debugging
            LoggingService.LogInfo(f"Starting path validation for: '{RootFolderPath}'", 'FileScanningBusinessService', 'StartScanning')

            # Check if path is provided
            if not RootFolderPath:
                LoggingService.LogError("RootFolderPath is empty or None", 'FileScanningBusinessService', 'StartScanning')
                return {
                    'Success': False,
                    'Message': 'Root folder path is required',
                    'Error': 'EmptyPath'
                }

            # directive: path-perfect-implementation | # see path.S11
            LocalPath = self._ToLocalPath(RootFolderPath)
            LoggingService.LogInfo(f"Worker-local path: '{LocalPath}' (canonical: '{RootFolderPath}')", 'FileScanningBusinessService', 'StartScanning')

            if not LocalExists(LocalPath):
                LoggingService.LogError(f"Path does not exist: local='{LocalPath}', canonical='{RootFolderPath}'", 'FileScanningBusinessService', 'StartScanning')
                return {
                    'Success': False,
                    'Message': f'Root folder does not exist: {RootFolderPath} (local: {LocalPath})',
                    'Error': 'InvalidPath'
                }

            if not LocalIsDir(LocalPath):
                return {
                    'Success': False,
                    'Message': f'Path is not a directory: {RootFolderPath}',
                    'Error': 'NotDirectory'
                }

            # Generate unique job ID
            JobId = str(uuid.uuid4())
            self.CurrentJobId = JobId

            # Create scan job record
            self.CreateScanJob(JobId, RootFolderPath, Recursive, WorkerName=WorkerName)

            # Set scanning state
            self.IsScanning = True
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = RootFolderPath
            # Reset directive-2026-05-27 phase state for this scan; PerformScan
            # transitions it through Walking -> Reconciling -> Probing -> Completing.
            self._CurrentPhase = 'Walking'
            self._FilesNeedingProbe = None
            self._ProbedFiles = None
            self._StopRequested = False

            LoggingService.LogInfo(f"Starting direct scan for {RootFolderPath}", 'FileScanningBusinessService', 'StartScanning')

            # Criterion 17 (progress writer): heartbeat the ScanJobs row every
            # 5s while the walk runs so operators (and StuckJobDetectionService)
            # can distinguish a live scan from a hung one. Stop the heartbeat
            # BEFORE writing the terminal status so an in-flight beat cannot
            # overwrite Completed/Failed back to Running.
            self._StartProgressHeartbeat(JobId)
            try:
                result = self.PerformScan(RootFolderPath, Recursive, SkipDuplicateCleanup=SkipDuplicateCleanup)
            finally:
                self._StopProgressHeartbeat()

            # Soft-stop transition: if the heartbeat saw Status='Stopping', the
            # per-file loop exited early -- record Status='Stopped' rather than
            # Completed/Failed so the operator sees the actual outcome.
            if self._StopRequested:
                self.UpdateJobStatus(JobId, 'Stopped', EndTime=datetime.now(timezone.utc),
                                     ScanResults=self.ScanResults, ClearPhase=True)
            elif result.get('Success', False):
                self.UpdateJobStatus(JobId, 'Completed', Progress=100.0, EndTime=datetime.now(timezone.utc),
                                     ScanResults=self.ScanResults, ClearPhase=True)
            else:
                self.UpdateJobStatus(JobId, 'Failed', ErrorMessage=result.get('Message', 'Unknown error'),
                                     EndTime=datetime.now(timezone.utc), ScanResults=self.ScanResults, ClearPhase=True)

            return result

        except Exception as e:
            LoggingService.LogException("Error starting scan", e, 'FileScanningBusinessService', 'StartScanning')
            return {
                'Success': False,
                'Message': f'Error starting scan: {str(e)}',
                'Error': 'ScanError'
            }

    # directive: path-perfect-implementation | # see filescanning.S1
    def CreateScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool, WorkerName: Optional[str] = None):
        try:
            from Core.Path.Path import Path, PathError
            from Core.Path.PathStorageRoots import GetStorageRoots
            try:
                Parsed = Path.FromLegacyString(RootFolderPath, GetStorageRoots())
                Sid, Rel = Parsed.StorageRootId, Parsed.RelativePath
            except PathError:
                Sid, Rel = None, None
            Query = (
                "INSERT INTO ScanJobs (JobId, StorageRootId, RelativePath, Recursive, Status, StartTime, LastUpdated, ScanType, WorkerName) "
                "VALUES (%s, %s, %s, %s, 'Running', %s, %s, 'File', %s)"
            )
            Now = datetime.now(timezone.utc)
            self.Repository.DatabaseService.ExecuteNonQuery(Query, (JobId, Sid, Rel, Recursive, Now, Now, WorkerName))

        except Exception as e:
            LoggingService.LogException(f"Error creating scan job {JobId}", e, 'FileScanningBusinessService', 'CreateScanJob')
            raise

    def UpdateJobStatus(self, JobId: str, Status: str, Progress: float = None, CurrentDirectory: str = None,
                       ProcessId: str = None, StartTime: datetime = None, EndTime: datetime = None,
                       ErrorMessage: str = None, ScanResults: FileScanResultModel = None,
                       Phase: Optional[str] = None, FilesNeedingProbe: Optional[int] = None,
                       ProbedFiles: Optional[int] = None, ClearPhase: bool = False):
        """Update the status of a scan job.

        Phase / FilesNeedingProbe / ProbedFiles support directive 2026-05-27 (Activity-page
        scan visibility). ClearPhase=True writes Phase=NULL (used on terminal transitions
        so a completed/failed row does not retain a stale phase value).
        """
        try:
            UpdateFields = []
            UpdateValues = []

            if Status:
                UpdateFields.append("Status = %s")
                UpdateValues.append(Status)

            if Progress is not None:
                UpdateFields.append("Progress = %s")
                UpdateValues.append(Progress)

            if CurrentDirectory is not None:
                UpdateFields.append("CurrentDirectory = %s")
                UpdateValues.append(CurrentDirectory)

            if ProcessId is not None:
                UpdateFields.append("ProcessId = %s")
                UpdateValues.append(ProcessId)

            if StartTime is not None:
                UpdateFields.append("StartTime = %s")
                UpdateValues.append(StartTime)

            if EndTime is not None:
                UpdateFields.append("EndTime = %s")
                UpdateValues.append(EndTime)

            if ErrorMessage is not None:
                UpdateFields.append("ErrorMessage = %s")
                UpdateValues.append(ErrorMessage)

            if ClearPhase:
                UpdateFields.append("Phase = NULL")
                UpdateFields.append("FilesNeedingProbe = NULL")
                UpdateFields.append("ProbedFiles = NULL")
            else:
                if Phase is not None:
                    UpdateFields.append("Phase = %s")
                    UpdateValues.append(Phase)
                if FilesNeedingProbe is not None:
                    UpdateFields.append("FilesNeedingProbe = %s")
                    UpdateValues.append(FilesNeedingProbe)
                if ProbedFiles is not None:
                    UpdateFields.append("ProbedFiles = %s")
                    UpdateValues.append(ProbedFiles)

            if ScanResults is not None:
                UpdateFields.extend([
                    "TotalFiles = %s",
                    "ProcessedFiles = %s",
                    "SkippedFiles = %s",
                    "EncodingErrors = %s",
                    "NewFiles = %s",
                    "UpdatedFiles = %s",
                    "DeletedFiles = %s"
                ])
                UpdateValues.extend([
                    ScanResults.TotalFilesFound,
                    ScanResults.TotalFilesProcessed,
                    ScanResults.TotalFilesSkipped,
                    ScanResults.TotalFilesWithErrors,
                    ScanResults.NewFilesCount,
                    ScanResults.UpdatedFilesCount,
                    ScanResults.DeletedFilesCount
                ])

            # Always update LastUpdated
            UpdateFields.append("LastUpdated = %s")
            UpdateValues.append(datetime.now(timezone.utc))

            # Add JobId for WHERE clause
            UpdateValues.append(JobId)

            Query = f"UPDATE ScanJobs SET {', '.join(UpdateFields)} WHERE JobId = %s"
            self.Repository.DatabaseService.ExecuteNonQuery(Query, UpdateValues)

        except Exception as e:
            LoggingService.LogException(f"Error updating job status for {JobId}", e, 'UpdateJobStatus', 'FileScanningBusinessService')


    def StopScanning(self) -> Dict[str, Any]:
        """Stop the current scanning process.

        Soft-stop discipline: flip `self._StopRequested = True` FIRST so the
        in-flight per-file and per-probe loops observe the signal at their
        next safe boundary and exit cleanly. Without this, only the DB status
        flips and the loop keeps walking until natural completion -- the
        heartbeat path that ALSO flips _StopRequested only triggers when it
        observes `ScanJobs.Status='Stopping'`, and this method jumps straight
        to 'Stopped'. Result was: capability flag flips OFF, DB says scan is
        stopped, but the operator still sees per-directory progress updates
        for several more minutes. Fixed 2026-05-30.
        """
        try:
            if not self.CurrentJobId:
                return {
                    'Success': False,
                    'Message': 'No scan is currently in progress',
                    'Error': 'NoScanInProgress'
                }

            # Soft-stop signal -- must precede any other state changes below.
            self._StopRequested = True

            # Update job status to stopped
            self.UpdateJobStatus(self.CurrentJobId, 'Stopped', EndTime=datetime.now(timezone.utc))

            # Clear current job and update scanning state
            self.CurrentJobId = None
            self.IsScanning = False
            self.ScanProgress = 0.0
            self.CurrentScanDirectory = ""

            LoggingService.LogInfo("Scan stopped by user request")

            return {
                'Success': True,
                'Message': 'Scan stopped successfully'
            }

        except Exception as e:
            LoggingService.LogException("Error stopping scan", e)
            return {
                'Success': False,
                'Message': f'Error stopping scan: {str(e)}',
                'Error': 'StopError'
            }

    def _StartProgressHeartbeat(self, JobId: str, IntervalSec: int = 5):
        """Owns FileScanning.feature.md criterion 17 (producer side).
        Without this loop, ScanJobs only sees writes at start and end -- a
        healthy walking scan and a hung scan are indistinguishable until
        StuckJobDetectionService fires at the 15-minute threshold.

        Also owns directive 2026-05-27 soft-stop polling: on each beat, reads
        ScanJobs.Status; if 'Stopping', sets self._StopRequested so the per-file
        and per-probe loops can exit cleanly to 'Stopped'.
        """
        self._HeartbeatStopEvent = threading.Event()

        def _Beat():
            while not self._HeartbeatStopEvent.wait(timeout=IntervalSec):
                try:
                    self.UpdateJobStatus(
                        JobId,
                        Status='Running',
                        Progress=float(self.ScanProgress) if self.ScanProgress is not None else None,
                        CurrentDirectory=self.CurrentScanDirectory or None,
                        ScanResults=self.ScanResults,
                        Phase=self._CurrentPhase,
                        FilesNeedingProbe=self._FilesNeedingProbe,
                        ProbedFiles=self._ProbedFiles,
                    )
                    # Soft-stop poll: cheap one-column read; the per-file loops
                    # observe self._StopRequested and exit before issuing more
                    # filesystem / DB work.
                    try:
                        Rows = self.Repository.DatabaseService.ExecuteQuery(
                            "SELECT Status FROM ScanJobs WHERE JobId = %s", (JobId,)
                        )
                        if Rows and str(Rows[0].get('Status', '')).lower() == 'stopping':
                            self._StopRequested = True
                    except Exception as PollEx:
                        LoggingService.LogException("Soft-stop poll failed", PollEx, 'FileScanningBusinessService', '_StartProgressHeartbeat')
                except Exception as Ex:
                    LoggingService.LogException("Heartbeat write failed", Ex, 'FileScanningBusinessService', '_StartProgressHeartbeat')

        self._HeartbeatThread = threading.Thread(
            target=_Beat, daemon=True, name=f"ScanHeartbeat-{JobId[:8]}"
        )
        self._HeartbeatThread.start()

    def _SetPhase(self, JobId: Optional[str], Phase: str,
                  FilesNeedingProbe: Optional[int] = None,
                  ProbedFiles: Optional[int] = None):
        """Write a Phase transition to ScanJobs immediately and update the
        in-memory mirror so the next heartbeat re-asserts the value.

        Directive 2026-05-27 criterion 13: phase visible in real time, not
        only on the 5s heartbeat tick.
        """
        self._CurrentPhase = Phase
        if FilesNeedingProbe is not None:
            self._FilesNeedingProbe = FilesNeedingProbe
        if ProbedFiles is not None:
            self._ProbedFiles = ProbedFiles
        Target = JobId or self.CurrentJobId
        if not Target:
            return
        try:
            self.UpdateJobStatus(
                Target,
                Status='Running',
                Phase=Phase,
                FilesNeedingProbe=FilesNeedingProbe,
                ProbedFiles=ProbedFiles,
            )
        except Exception as Ex:
            LoggingService.LogException(f"Failed to write Phase={Phase}", Ex, 'FileScanningBusinessService', '_SetPhase')

    def _StopProgressHeartbeat(self):
        Ev = getattr(self, '_HeartbeatStopEvent', None)
        if Ev is not None:
            Ev.set()
        Th = getattr(self, '_HeartbeatThread', None)
        if Th is not None and Th.is_alive():
            Th.join(timeout=2)
        self._HeartbeatStopEvent = None
        self._HeartbeatThread = None

    # directive: path-schema-migration | # see path.S8
    def _RunSizeSurvey(self, LocalRootPath: str, CanonicalRootPath: str, RootFolder: RootFolderModel):
        # see filescanning.ST2
        """Directive 2026-05-27 (scan -- largest files first), criteria 1-5.

        Stat-only recursive enumeration of media files under LocalRootPath.
        Sorts by size descending, takes top-N (SystemSettings SizeSurveyTopN,
        default 100, soft-cap 500), UPSERTs those MediaFiles rows so the rest
        of the pipeline can act on them immediately, and writes a JSON array
        of {path, sizeMB, modifiedAt} to ScanJobs.TopFiles so /Activity can
        surface them inline under the scan row.

        No FFprobe, no metadata reads -- stat-only. Budget: ~30s on Larry NFS
        for a 40k-file share.
        """
        import json
        from datetime import datetime, timezone

        SurveyStart = datetime.now(timezone.utc)

        # Read TopN fresh from settings every scan (no worker restart for changes).
        TopN = 100
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Raw = SystemSettingsRepository().GetSystemSetting('SizeSurveyTopN')
            if Raw:
                TopN = max(1, min(500, int(Raw)))
        except Exception as Ex:
            LoggingService.LogException("Failed to read SizeSurveyTopN, using default 100", Ex, 'FileScanningBusinessService', '_RunSizeSurvey')

        MediaExts = self.FileManager.MediaExtensions
        Excluded = {p.lower() for p in (self.FileManager.ExcludedDirectories or [])}

        # Heap-based top-N via os.scandir recursion. Avoids holding all 40k
        # entries in memory and avoids a full sort -- O(N log K) instead of
        # O(N log N) where K << N.
        import heapq
        Heap = []  # min-heap of (sizeBytes, mtimeFloat, localPath)
        FilesSeen = 0

        def _WalkSurvey(Path: str):
            nonlocal FilesSeen
            try:
                with os.scandir(Path) as It:
                    for Entry in It:
                        try:
                            if Entry.is_dir(follow_symlinks=False):
                                if Entry.name.lower() in Excluded:
                                    continue
                                _WalkSurvey(Entry.path)
                            elif Entry.is_file(follow_symlinks=False):
                                Ext = LocalSplitExt(Entry.name)[1].lower()
                                if Ext not in MediaExts:
                                    continue
                                St = Entry.stat(follow_symlinks=False)
                                FilesSeen += 1
                                Item = (St.st_size, St.st_mtime, Entry.path)
                                if len(Heap) < TopN:
                                    heapq.heappush(Heap, Item)
                                elif St.st_size > Heap[0][0]:
                                    heapq.heapreplace(Heap, Item)
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError) as DirEx:
                LoggingService.LogWarning(f"SizeSurvey could not enter {Path}: {DirEx}", 'FileScanningBusinessService', '_RunSizeSurvey')

        _WalkSurvey(LocalRootPath)

        # Drain the heap, largest first.
        TopList = sorted(Heap, key=lambda x: -x[0])
        ElapsedSec = (datetime.now(timezone.utc) - SurveyStart).total_seconds()
        LoggingService.LogInfo(
            f"SizeSurvey: enumerated {FilesSeen} media files under {LocalRootPath} in {ElapsedSec:.1f}s; top-{len(TopList)} surfaced",
            'FileScanningBusinessService', '_RunSizeSurvey'
        )

        # Pass 1 UPSERT top-N into MediaFiles + capture Id; each Record carries Id/localPath/path/fileName/sizeMB/modifiedAt.
        Roots = _GetStorageRoots()
        Records = []
        for SizeBytes, Mtime, LocalPath in TopList:
            try:
                CanonicalPath = self._ToCanonicalPath(LocalPath)
                FileName = LocalBasename(LocalPath)
                SizeMB = round(SizeBytes / (1024 * 1024), 2)
                MtimeDt = datetime.fromtimestamp(Mtime, tz=timezone.utc).replace(tzinfo=None)
                try:
                    _PPair = Path.FromLegacyString(CanonicalPath, Roots)
                    StorageRootId, RelativePath = _PPair.StorageRootId, _PPair.RelativePath
                except PathError:
                    StorageRootId, RelativePath = None, None

                ExistingId = None
                if StorageRootId is not None and RelativePath is not None:
                    Found = self.Repository.DatabaseService.ExecuteQuery(
                        "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND LOWER(RelativePath) = LOWER(%s) LIMIT 1",
                        (StorageRootId, RelativePath),
                    )
                    if Found:
                        ExistingId = Found[0].get('Id') or Found[0].get('id')

                if ExistingId is not None:
                    # directive: path-schema-migration | # see path.S8 -- update typed pair, FileName, and core metadata; FilePath is computed display
                    self.Repository.DatabaseService.ExecuteNonQuery(
                        "UPDATE MediaFiles "
                        "SET SizeMB = %s, "
                        "    FileSize = %s, "
                        "    FileModificationTime = %s, "
                        "    LastModifiedDate = %s, "
                        "    LastScannedDate = %s, "
                        "    StorageRootId = %s, "
                        "    RelativePath = %s, "
                        "    FileName = %s "
                        "WHERE Id = %s",
                        (SizeMB, SizeBytes, MtimeDt, MtimeDt, datetime.now(timezone.utc), StorageRootId, RelativePath, FileName, ExistingId),
                    )
                    RowId = ExistingId
                else:
                    NewFile = MediaFileModel(
                        SeasonId=None,
                        StorageRootId=StorageRootId,
                        RelativePath=RelativePath or '',
                        FileName=FileName,
                        SizeMB=SizeMB,
                        FileModificationTime=MtimeDt,
                        LastModifiedDate=MtimeDt,
                        FileSize=SizeBytes,
                        LastScannedDate=datetime.now(timezone.utc),
                    )
                    RowId = self.Repository.SaveMediaFile(NewFile)

                if RowId is not None:
                    Records.append({
                        'Id': RowId,
                        'path': CanonicalPath,
                        'fileName': FileName,
                        'sizeMB': SizeMB,
                        'modifiedAt': MtimeDt.isoformat() + 'Z',
                    })
            except Exception as Ex:
                LoggingService.LogException(f"SizeSurvey UPSERT failed for {LocalPath}", Ex, 'FileScanningBusinessService', '_RunSizeSurvey')

        # Initial TopFiles snapshot (all enumerated entries) + counter init for
        # the heartbeat. The probe pass below drops each entry as it completes,
        # so /Activity shows the list drain in real time.
        def _WriteTopFiles(EntriesList):
            try:
                Payload = [{k: r[k] for k in ('path', 'fileName', 'sizeMB', 'modifiedAt')} for r in EntriesList]
                self.Repository.DatabaseService.ExecuteNonQuery(
                    "UPDATE ScanJobs SET TopFiles = %s::jsonb, LastUpdated = NOW() WHERE JobId = %s",
                    (json.dumps(Payload), self.CurrentJobId),
                )
            except Exception as WriteEx:
                LoggingService.LogException("Failed to persist ScanJobs.TopFiles", WriteEx, 'FileScanningBusinessService', '_RunSizeSurvey')

        _WriteTopFiles(Records)
        EnumSec = (datetime.now(timezone.utc) - SurveyStart).total_seconds()
        LoggingService.LogInfo(
            f"SizeSurvey enumeration: {len(Records)} top files staged in {EnumSec:.1f}s ({FilesSeen} surveyed); now probing largest-first",
            'FileScanningBusinessService', '_RunSizeSurvey'
        )

        # Pass 2: probe each top-N file in size-descending order. Roll each one
        # off the TopFiles list as it completes so the operator watches the
        # largest items drain. Soft-stop honored.
        self._FilesNeedingProbe = len(Records)
        self._ProbedFiles = 0
        ProbeStart = datetime.now(timezone.utc)
        Remaining = list(Records)
        ProbedCount = 0
        for Rec in Records:
            if self._StopRequested:
                LoggingService.LogInfo("SizeSurvey probe loop interrupted by soft-stop", 'FileScanningBusinessService', '_RunSizeSurvey')
                break
            try:
                MediaFile = self.Repository.GetMediaFileById(Rec['Id'])
                if MediaFile is not None:
                    # Skip the probe if the file already has full metadata. The
                    # operator still sees this entry roll off TopFiles, but we
                    # don't waste minutes re-probing a 4K Bluray whose metadata
                    # is already current. ShouldExtractMetadata also gates on
                    # the FFprobe failure limit.
                    if self.ShouldExtractMetadata(MediaFile):
                        Result = self.MediaProbeService._ExecuteProbe(MediaFile)
                        if not Result.get('Success', False):
                            LoggingService.LogWarning(
                                f"SizeSurvey probe failed for {Rec['path']}: {Result.get('Message') or Result.get('Error')}",
                                'FileScanningBusinessService', '_RunSizeSurvey'
                            )
                    else:
                        LoggingService.LogDebug(
                            f"SizeSurvey skip-probe (metadata current): {Rec['path']}",
                            'FileScanningBusinessService', '_RunSizeSurvey'
                        )
            except Exception as ProbeEx:
                LoggingService.LogException(f"SizeSurvey probe exception for {Rec['path']}", ProbeEx, 'FileScanningBusinessService', '_RunSizeSurvey')

            # Roll this entry off the list regardless of probe outcome -- the
            # MediaFiles row carries any failure state (FFprobeFailureCount).
            try:
                Remaining.remove(Rec)
            except ValueError:
                pass
            ProbedCount += 1
            self._ProbedFiles = ProbedCount
            _WriteTopFiles(Remaining)

        TotalSec = (datetime.now(timezone.utc) - SurveyStart).total_seconds()
        ProbeSec = (datetime.now(timezone.utc) - ProbeStart).total_seconds()
        LoggingService.LogInfo(
            f"SizeSurvey complete: enumerated {FilesSeen}, staged {len(Records)}, probed {ProbedCount} in {ProbeSec:.1f}s (total {TotalSec:.1f}s)",
            'FileScanningBusinessService', '_RunSizeSurvey'
        )

    def CleanupCompletedJobs(self):
        """Clean up old completed scan jobs."""
        try:
            # Delete jobs older than 7 days
            Query = """
            DELETE FROM ScanJobs
            WHERE Status IN ('Completed', 'Failed', 'Stopped')
            AND LastUpdated < NOW() - INTERVAL '7 days'
            """
            self.Repository.DatabaseService.ExecuteNonQuery(Query)
            LoggingService.LogInfo("Cleaned up old scan jobs")
        except Exception as e:
            LoggingService.LogException("Error cleaning up scan jobs", e)

    def PerformScan(self, RootFolderPath: str, Recursive: bool, SkipDuplicateCleanup: bool = False) -> Dict[str, Any]:
        """Perform the actual scanning process.

        RootFolderPath is the canonical (Windows-style) path stored in the DB.
        On Linux containers we translate to a local mount for filesystem ops
        and translate the walked file paths back to canonical for DB writes.
        """
        try:
            LoggingService.LogInfo("Starting scan of directory: {}", RootFolderPath)

            # Reset per-scan counters (was carrying over between consecutive scans on
            # the same FileScanningBusinessService instance, polluting heartbeats with
            # stale numbers from the previous rootfolder).
            self.ScanResults = FileScanResultModel()

            LocalRootPath = self._ToLocalPath(RootFolderPath)

            # Step 0: Clean up any existing duplicate records before scanning
            # Skipped during continuous scans where cleanup runs once before the loop
            if not SkipDuplicateCleanup:
                # directive: path-schema-migration | # see path.S8 -- CleanupDuplicateMediaFiles lives on MediaFilesRepository
                from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
                CleanupResult = MediaFilesRepository(self.Repository.DatabaseService).CleanupDuplicateMediaFiles()
                if CleanupResult.get('DuplicatesRemoved', 0) > 0:
                    LoggingService.LogInfo(f"Pre-scan cleanup removed {CleanupResult['DuplicatesRemoved']} duplicate records", 'PerformScan', 'FileScanningBusinessService')

            # Step 1: Calculate directory size (uses local path)
            self.ScanProgress = 10.0
            TotalSizeGB = self.FileManager.CalculateDirectorySize(LocalRootPath)

            # Step 2: Get or create root folder record (canonical path stored in DB)
            self.ScanProgress = 20.0
            RootFolder = self.GetOrCreateRootFolder(RootFolderPath, TotalSizeGB)

            if not RootFolder or not RootFolder.Id:
                LoggingService.LogError(f"Failed to create or get root folder for: {RootFolderPath}", 'PerformScan', 'FileScanningBusinessService')
                return {
                    'Success': False,
                    'Message': f'Failed to create root folder record for: {RootFolderPath}',
                    'Error': 'RootFolderCreationFailed'
                }

            # Step 2.5: SizeSurvey -- directive 2026-05-27 (scan -- largest files first).
            # Stat-only enumeration that front-loads the top-N largest files into
            # MediaFiles so the operator gets the biggest savings opportunities on
            # /Activity within ~30s, before the long walk. Reads SizeSurveyTopN
            # fresh from SystemSettings each scan; default 100, soft cap 500.
            self._SetPhase(self.CurrentJobId, 'SizeSurvey')
            try:
                self._RunSizeSurvey(LocalRootPath, RootFolderPath, RootFolder)
            except Exception as SurveyEx:
                LoggingService.LogException("SizeSurvey failed -- continuing to full scan", SurveyEx, 'PerformScan', 'FileScanningBusinessService')

            # Step 3: Walk the LOCAL path; convert results back to canonical
            # for DB storage so MediaFiles.FilePath stays portable across hosts.
            self.ScanProgress = 30.0
            self._SetPhase(self.CurrentJobId, 'Walking')
            LocalMediaFiles = self.FileManager.ScanDirectory(LocalRootPath, Recursive)
            MediaFiles = [self._ToCanonicalPath(p) for p in LocalMediaFiles]
            self.ScanResults.TotalFilesFound = len(MediaFiles)
            self.ScanResults.RootFolderId = RootFolder.Id

            # Build per-scan show/episode index ONCE (criterion 25). Without
            # this, FindFuzzyFileMatch reloads + regex-parses all RootFolder
            # rows for every new file -- O(N x M) wall clock.
            self._ShowEpisodeIndex = self._BuildShowEpisodeIndex(RootFolder.Id)
            try:
                # Step 4: Process each media file (without metadata extraction for speed)
                self.ProcessMediaFiles(MediaFiles, RootFolder.Id, RootFolderPath, ExtractMetadata=False)
            finally:
                self._ShowEpisodeIndex = None

            # Step 5: Update scan results
            self.ScanProgress = 90.0
            self.UpdateScanResults()

            # Step 6: Complete scan
            self.ScanProgress = 100.0
            self.IsScanning = False

            LoggingService.LogInfo(f"Scan completed: {len(MediaFiles)} files found")

            # Step 7: Automatically trigger metadata extraction for the scanned files
            try:
                if RootFolder and RootFolder.Id:
                    LoggingService.LogInfo(f"Starting automatic metadata extraction for RootFolderId: {RootFolder.Id}", 'PerformScan', 'FileScanningBusinessService')
                    # Directive 2026-05-27 criteria 13-14: enter Probing phase. Count the
                    # files we are about to probe so the Activity page can render a real
                    # bar instead of a spinner; the callback advances ProbedFiles per file.
                    FilesQueued = self.MediaProbeService.Repository.GetFilesNeedingProbeCount(RootFolder.Id, self.MediaProbeService.MaxFFprobeFailures)
                    self._SetPhase(self.CurrentJobId, 'Probing', FilesNeedingProbe=FilesQueued, ProbedFiles=0)

                    def _OnProbed(Index: int):
                        # Per-probe counter for the Activity page's progress bar.
                        # Also the soft-stop signal arrives via self._StopRequested;
                        # the probe loop reads it and exits cleanly.
                        self._ProbedFiles = Index
                        return self._StopRequested

                    metadataResult = self.MediaProbeService.ProbeFilesNeedingMetadata(
                        RootFolder.Id, ProgressCallback=_OnProbed
                    )
                else:
                    LoggingService.LogWarning("No RootFolderId available - skipping automatic metadata extraction", 'PerformScan', 'FileScanningBusinessService')
                    metadataResult = {'Success': True, 'Message': 'No RootFolderId - metadata extraction skipped', 'Processed': 0}
                if metadataResult.get('Success', False):
                    processedFiles = metadataResult.get('Processed', 0)
                    LoggingService.LogInfo(f"Metadata extraction completed: {processedFiles} files processed")
                else:
                    LoggingService.LogWarning(f"Metadata extraction failed: {metadataResult.get('Message', 'Unknown error')}")
            except Exception as e:
                LoggingService.LogException("Error during automatic metadata extraction", e, 'PerformScan', 'FileScanningBusinessService')

            # Step 8: Completing -- final stats / RootFolder.LastScannedDate update.
            self._SetPhase(self.CurrentJobId, 'Completing')

            return {
                'Success': True,
                'Message': 'Scan completed successfully',
                'Results': self.ScanResults,
                'RootFolderId': RootFolder.Id,
                'TotalSizeGB': TotalSizeGB
            }

        except Exception as e:
            LoggingService.LogException("Error during scan", e)
            self.IsScanning = False
            self.ScanErrors.append(f"Scan error: {str(e)}")
            return {
                'Success': False,
                'Message': f'Error during scan: {str(e)}',
                'Error': 'ScanError',
                'Results': self.ScanResults
            }


    # directive: paths-canonical-completion
    def GetOrCreateRootFolder(self, RootFolderPath: str, TotalSizeGB: float) -> RootFolderModel:
        # see filescanning.ST6
        """Get existing root folder or create a new one.

        RootFolderPath is canonical (Windows-style). On Windows we walk the
        filesystem to recover correct case; on Linux containers the raw path
        does not exist on the fs (it's an SMB drive letter), so we trust the
        canonical input as authoritative and skip fs canonicalization.
        """
        try:
            from Core.WorkerContext import WorkerContext
            # directive: path-perfect-implementation | # see path.S11
            Ctx = WorkerContext.Current()
            UseFsCanonicalization = not (Ctx and (Ctx.Platform or '').lower() == 'linux')

            CanonicalPath = (self.GetCanonicalPathFromFilesystem(RootFolderPath)
                             if UseFsCanonicalization else RootFolderPath)

            # directive: path-class-perfection | # see path.C23
            from Core.Path.Path import Path as _PathFS, PathError as _PEFS
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMFS, GetStorageRoots as _GSRFS
            _Pm = _GPMFS()
            _Srs = _GSRFS()
            ExistingFolders = self.Repository.GetAllRootFolders()
            for Folder in ExistingFolders:
                try:
                    _FolderP = Folder.Path
                    if _FolderP is None:
                        continue
                    _FolderDisplay = _FolderP.CanonicalDisplay(_Pm)
                    if UseFsCanonicalization:
                        if _CanonicalExists(_FolderDisplay):
                            ExistingCanonical = self.GetCanonicalPathFromFilesystem(_FolderDisplay)
                            if ExistingCanonical == CanonicalPath:
                                _Parsed = _PathFS.FromLegacyString(CanonicalPath, _Srs)
                                Folder.StorageRootId = _Parsed.StorageRootId
                                Folder.RelativePath = _Parsed.RelativePath
                                Folder.LastScannedDate = datetime.now(timezone.utc)
                                Folder.TotalSizeGB = TotalSizeGB
                                FolderId = self.Repository.SaveRootFolder(Folder)
                                Folder.Id = FolderId
                                LoggingService.LogInfo(f"Updated existing root folder: {CanonicalPath}")
                                return Folder
                    else:
                        if _FolderDisplay == CanonicalPath:
                            Folder.LastScannedDate = datetime.now(timezone.utc)
                            Folder.TotalSizeGB = TotalSizeGB
                            FolderId = self.Repository.SaveRootFolder(Folder)
                            Folder.Id = FolderId
                            LoggingService.LogInfo(f"Updated existing root folder: {CanonicalPath}")
                            return Folder
                except Exception:
                    continue

            NewFolder = RootFolderModel(
                RootFolder=CanonicalPath,
                LastScannedDate=datetime.now(timezone.utc),
                TotalSizeGB=TotalSizeGB
            )
            FolderId = self.Repository.SaveRootFolder(NewFolder)
            NewFolder.Id = FolderId
            LoggingService.LogInfo(f"Created new root folder: {CanonicalPath}")
            return NewFolder

        except Exception as e:
            LoggingService.LogException("Error managing root folder", e)
            raise

    # directive: paths-canonical-completion
    def GetCanonicalPathFromFilesystem(self, Path: str) -> str:
        # see filescanning.ST1
        """Get the actual case-sensitive path as it exists on the filesystem."""
        try:
            if not Path:
                return Path

            normalized_path = ntpath.normpath(Path or "")

            # Check if path exists
            if not LocalExists(normalized_path):
                LoggingService.LogWarning(f"Path does not exist, cannot get canonical case: {Path}",
                                         'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
                return normalized_path

            # normalized_path is canonical display (Windows backslash) -- literal "\\" keeps splitting correct on Linux workers
            if len(normalized_path) >= 2 and normalized_path[1] == ':':
                drive = normalized_path[0:2]
                remainder = normalized_path[2:].lstrip("\\")
                result_path = drive + "\\"
                if remainder:
                    parts = remainder.split("\\")
                else:
                    parts = []
            else:
                parts = normalized_path.split("\\")
                result_path = parts[0] if parts else ''
                parts = parts[1:] if parts else []

            # Resolve each component by listing parent directory
            current_path = result_path
            for part in parts:
                if not part:  # Skip empty parts
                    continue

                try:
                    # current_path stays canonical display through the walk -- use ntpath.join, not LocalJoin
                    if LocalIsDir(current_path):
                        dir_contents = os.listdir(current_path)
                        actual_name = None
                        for item in dir_contents:
                            if item.upper() == part.upper():
                                actual_name = item
                                break

                        if actual_name:
                            current_path = ntpath.join(current_path, actual_name)
                        else:
                            current_path = ntpath.join(current_path, part)
                    else:
                        current_path = ntpath.join(current_path, part)
                except Exception as e:
                    LoggingService.LogWarning(f"Could not list directory '{current_path}' to get actual case, using: {part}",
                                             'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
                    current_path = ntpath.join(current_path, part)

            # Log if case changed
            if current_path != normalized_path:
                LoggingService.LogInfo(f"Normalized path case: '{normalized_path}' -> '{current_path}'",
                                     'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')

            return current_path

        except Exception as e:
            LoggingService.LogWarning(f"Could not resolve canonical path for {Path}, using original: {str(e)}",
                                     'GetCanonicalPathFromFilesystem', 'FileScanningBusinessService')
            return Path if Path else normalized_path

    def ProcessMediaFiles(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process each media file found during scanning with optional metadata extraction."""
        try:
            LoggingService.LogFunctionEntry("ProcessMediaFiles", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")

            # Use the new metadata-aware processing method
            self.ProcessMediaFilesWithMetadata(MediaFiles, RootFolderId, RootFolderPath, ExtractMetadata)

        except Exception as e:
            LoggingService.LogException("Error processing media files", e, 'ProcessMediaFiles', 'FileScanningBusinessService')
            raise

    def ExtractSeasonFromPath(self, FilePath: str, RootFolderPath: str) -> str:
        """Simplified season extraction - return empty string since season functionality is disabled."""
        return ""


    def ExtractShowInfo(self, FileName: str) -> Dict[str, str]:
        """Extract show, season, and episode information from filename."""
        try:
            # Remove file extension
            NameWithoutExt = Path(FileName).stem

            ShowInfo = {
                'ShowName': '',
                'Season': '',
                'Episode': '',
                'Quality': '',
                'Source': ''
            }

            # Extract season/episode pattern (S01E11, S1E11, 1x11, etc.)
            SeasonEpisodePattern = r'[Ss](\d+)[Ee](\d+)'
            Match = re.search(SeasonEpisodePattern, NameWithoutExt)

            if Match:
                ShowInfo['Season'] = f"S{Match.group(1).zfill(2)}"
                ShowInfo['Episode'] = f"E{Match.group(2).zfill(2)}"

                # Extract show name (everything before season/episode)
                ShowName = NameWithoutExt[:Match.start()].strip()
                ShowName = re.sub(r'[-._]', ' ', ShowName).strip()
                ShowInfo['ShowName'] = ShowName
            else:
                # Try alternative pattern (1x11, 1.11, etc.)
                AltPattern = r'(\d+)[x.](\d+)'
                AltMatch = re.search(AltPattern, NameWithoutExt)
                if AltMatch:
                    ShowInfo['Season'] = f"S{AltMatch.group(1).zfill(2)}"
                    ShowInfo['Episode'] = f"E{AltMatch.group(2).zfill(2)}"

                    # Extract show name
                    ShowName = NameWithoutExt[:AltMatch.start()].strip()
                    ShowName = re.sub(r'[-._]', ' ', ShowName).strip()
                    ShowInfo['ShowName'] = ShowName

            # Extract quality indicators
            QualityPatterns = ['1080p', '720p', '480p', '4K', 'Bluray', 'HDTV', 'WEBRip', 'WEB-DL', 'BRRip', 'DVDRip']
            for Pattern in QualityPatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    ShowInfo['Quality'] = Pattern
                    break

            # Extract source indicators
            SourcePatterns = ['Bluray', 'HDTV', 'WEBRip', 'WEB-DL', 'BRRip', 'DVDRip', 'TVRip']
            for Pattern in SourcePatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    ShowInfo['Source'] = Pattern
                    break

            return ShowInfo

        except Exception as e:
            LoggingService.LogException("Error extracting show info", e)
            return {'ShowName': '', 'Season': '', 'Episode': '', 'Quality': '', 'Source': ''}

    def IsFuzzyMatch(self, FileInfo: Dict[str, str], DbFileInfo: Dict[str, str],
                    FileSize: float, DbFileSize: float) -> bool:
        """Determine if two files are a fuzzy match."""
        try:
            # Must have same show name (case insensitive)
            if FileInfo['ShowName'].lower() != DbFileInfo['ShowName'].lower():
                return False

            # Must have same season and episode
            if FileInfo['Season'] != DbFileInfo['Season'] or FileInfo['Episode'] != DbFileInfo['Episode']:
                return False

            # Size difference tolerance (within 10% or 100MB, whichever is larger)
            SizeDifference = abs(FileSize - DbFileSize)
            SizeTolerance = max(FileSize * 0.1, 100)  # 10% or 100MB, whichever is larger

            if SizeDifference > SizeTolerance:
                return False

            # If we get here, it's a fuzzy match
            return True

        except Exception as e:
            LoggingService.LogException("Error in fuzzy match logic", e)
            return False

    def _BuildShowEpisodeIndex(self, RootFolderId: int) -> Dict[tuple, List[MediaFileModel]]:
        """Owns FileScanning.feature.md criterion 25 (per-scan precompute).
        Single GetMediaFilesByRootFolderId call + one ExtractShowInfo per row;
        FindFuzzyFileMatch then looks up candidates in O(1) instead of
        re-loading and re-parsing all RootFolder rows for every new file.
        Read-only after build, safe for the parallel processor pool.
        """
        Index: Dict[tuple, List[MediaFileModel]] = {}
        try:
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)
            for DbFile in DatabaseFiles:
                if not DbFile.FileName:
                    continue
                Info = self.ExtractShowInfo(DbFile.FileName)
                if not (Info.get('ShowName') and Info.get('Season') and Info.get('Episode')):
                    continue
                Key = (Info['ShowName'].lower(), Info['Season'], Info['Episode'])
                Index.setdefault(Key, []).append(DbFile)
            LoggingService.LogInfo(
                f"Built show/episode index: {len(DatabaseFiles)} rows -> {len(Index)} (show, season, episode) keys",
                'FileScanningBusinessService', '_BuildShowEpisodeIndex'
            )
        except Exception as e:
            LoggingService.LogException("Error building show/episode index", e, 'FileScanningBusinessService', '_BuildShowEpisodeIndex')
        return Index

    # directive: paths-canonical-completion
    def FindFuzzyFileMatch(self, FilePath: str, FileName: str, FileSizeMB: float, RootFolderId: int) -> Optional[MediaFileModel]:
        # see filescanning.ST5
        """Find a fuzzy match for a file in the database. When a per-scan
        show/episode index is set on `self._ShowEpisodeIndex` (criterion 25),
        candidate lookup is O(1); otherwise falls back to the legacy O(N)
        per-call scan for safety on out-of-band callers.
        """
        try:
            FileShowInfo = self.ExtractShowInfo(FileName)
            if not FileShowInfo['ShowName'] or not FileShowInfo['Season'] or not FileShowInfo['Episode']:
                return None

            Index = getattr(self, '_ShowEpisodeIndex', None)
            if Index is not None:
                Candidates = Index.get((FileShowInfo['ShowName'].lower(), FileShowInfo['Season'], FileShowInfo['Episode']), [])
            else:
                Candidates = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)

            for DbFile in Candidates:
                if Index is None:
                    DbShowInfo = self.ExtractShowInfo(DbFile.FileName)
                    if not self.IsFuzzyMatch(FileShowInfo, DbShowInfo, FileSizeMB, DbFile.SizeMB):
                        continue
                else:
                    if abs((FileSizeMB or 0) - (DbFile.SizeMB or 0)) >= 1.0:
                        continue

                if not _CanonicalExists(DbFile.FilePath):
                    return DbFile
                else:
                    return None

            return None

        except Exception as e:
            LoggingService.LogException("Error in fuzzy file matching", e)
            return None

    # directive: path-schema-migration | # see path.S8
    def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        """Process a single media file with fuzzy matching and optional metadata extraction; FilePath param is the canonical path string."""
        try:
            # Canonicalize path string for DB consistency (lookups vs inserts).
            FilePath = ntpath.normpath(FilePath or "")
            LocalPath = self._ToLocalPath(FilePath)

            # Existence check uses the translated local path.
            if not LocalExists(LocalPath):
                LoggingService.LogWarning(f"File does not exist on disk: {FilePath} (local: {LocalPath})", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                ExistingFile = self.Repository.GetMediaFileByPath(FilePath)
                if ExistingFile:
                    LoggingService.LogInfo(f"Deleting database entry for missing file: {FilePath} (ID: {ExistingFile.Id})", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    self.Repository.DeleteMediaFile(ExistingFile.Id)
                else:
                    LoggingService.LogDebug(f"No database entry found for missing file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

                return

            # Filesystem reads use LocalPath; DB writes use canonical FilePath.
            FileSizeMB = self.FileManager.GetFileSizeMB(LocalPath)
            FileName = self.FileManager.GetFileNameFromPath(FilePath)
            FileModificationTime = self.GetFileModificationTime(LocalPath)

            try:
                FileSize = LocalGetSize(LocalPath)
            except Exception:
                FileSize = int(FileSizeMB * 1024 * 1024) if FileSizeMB else 0

            # Check if this file already exists in database (exact match)
            ExistingFile = self.Repository.GetMediaFileByPath(FilePath)
            if ExistingFile:
                # OPTIMIZATION: Quick check using LastModifiedDate and FileSize
                # This is MUCH faster than re-extracting metadata
                HasChanged = self.HasFileChanged(ExistingFile, FileSizeMB, FileName, FileModificationTime)

                if HasChanged:
                    # File has changed - update it
                    LoggingService.LogInfo(f"File changed, updating: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    ExistingFile.SizeMB = FileSizeMB
                    ExistingFile.FileName = FileName
                    ExistingFile.FileModificationTime = FileModificationTime
                    ExistingFile.LastModifiedDate = FileModificationTime
                    ExistingFile.FileSize = FileSize
                    ExistingFile.SeasonId = None  # Season functionality disabled
                    ExistingFile.LastScannedDate = datetime.now(timezone.utc)

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                        self.ExtractAndUpdateMetadata(ExistingFile, LocalPath)

                    self.Repository.SaveMediaFile(ExistingFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.UpdatedFilesCount += 1
                else:
                    # FILE UNCHANGED - SKIP PROCESSING (HUGE PERFORMANCE WIN!)
                    # Only update LastScannedDate to mark it was checked
                    ExistingFile.LastScannedDate = datetime.now(timezone.utc)
                    self.UpdateLastScannedDate(ExistingFile.Id, ExistingFile.LastScannedDate)
                    self.ScanResults.TotalFilesSkipped += 1
                    LoggingService.LogDebug(f"Skipped unchanged file: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')

            else:
                # File doesn't exist in database - check for fuzzy match (renamed file)
                FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)

                try:
                    _PPair = Path.FromLegacyString(FilePath, _GetStorageRoots())
                    StorageRootId, RelativePath = _PPair.StorageRootId, _PPair.RelativePath
                except PathError:
                    StorageRootId, RelativePath = None, None

                if FuzzyMatch:
                    # Found a fuzzy match - this is likely a renamed file; typed pair drives FilePath display
                    FuzzyMatch.StorageRootId = StorageRootId
                    FuzzyMatch.RelativePath = RelativePath or ''
                    FuzzyMatch.FileName = FileName  # Update to new filename
                    FuzzyMatch.SizeMB = FileSizeMB  # Update to new size
                    FuzzyMatch.FileModificationTime = FileModificationTime
                    FuzzyMatch.SeasonId = None  # Season functionality disabled
                    FuzzyMatch.LastScannedDate = datetime.now(timezone.utc)

                    # Extract metadata if requested and not already present
                    if ExtractMetadata and self.ShouldExtractMetadata(FuzzyMatch):
                        self.ExtractAndUpdateMetadata(FuzzyMatch, LocalPath)

                    self.Repository.SaveMediaFile(FuzzyMatch)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.UpdatedFilesCount += 1
                else:
                    # No fuzzy match found - create new file record. The
                    # transcoded-file-match path was retired with criterion 18a
                    # (post-FileReplacement, transcoded outputs land at the
                    # original path atomically; there is no _transcoded/ dir).
                    LoggingService.LogInfo(f"New file discovered: {FilePath}", 'ProcessSingleMediaFile', 'FileScanningBusinessService')
                    NewFile = MediaFileModel(
                        SeasonId=None,  # Season functionality disabled
                        StorageRootId=StorageRootId,
                        RelativePath=RelativePath or '',
                        FileName=FileName,
                        SizeMB=FileSizeMB,
                        FileModificationTime=FileModificationTime,
                        LastModifiedDate=FileModificationTime,
                        FileSize=FileSize,
                        LastScannedDate=datetime.now(timezone.utc)
                    )

                    if ExtractMetadata:
                        self.ExtractAndUpdateMetadata(NewFile, LocalPath)

                    self.Repository.SaveMediaFile(NewFile)
                    self.ScanResults.TotalFilesProcessed += 1
                    self.ScanResults.NewFilesCount += 1

        except Exception as e:
            LoggingService.LogException("Error processing single media file", e)
            self.ScanResults.TotalFilesSkipped += 1
            raise


    # Note: Duplicate detection methods have been moved to DuplicateDetectionService
    # to keep the scanning process focused and fast. Use the dedicated service
    # for duplicate file detection and cleanup operations.

    def UpdateScanResults(self):
        """Update scan results with file manager statistics."""
        try:
            FileManagerStats = self.FileManager.GetProcessingStats()
            EncodingErrors = self.FileManager.GetEncodingErrors()

            # Update scan results with file manager statistics
            self.ScanResults.TotalFilesSkipped = FileManagerStats.get('SkippedFiles', 0)
            self.ScanResults.TotalFilesWithErrors = FileManagerStats.get('EncodingErrors', 0)

            # Add encoding errors to scan errors
            self.ScanErrors.extend(EncodingErrors)

            LoggingService.LogInfo(f"Scan results updated: TotalFiles={self.ScanResults.TotalFilesFound}, Processed={self.ScanResults.TotalFilesProcessed}, Skipped={self.ScanResults.TotalFilesSkipped}, Errors={self.ScanResults.TotalFilesWithErrors}")

        except Exception as e:
            LoggingService.LogException("Error updating scan results", e)


    def GetScanStatus(self) -> Dict[str, Any]:
        """Get current scan status and progress (public API for /api/Scan/Status).

        Aggregates the running ScanJobs rows into the UI-shaped dict the
        FileScanning page expects. Uses the unified Repository.GetRunningScans
        per criterion 18b -- the eight is-running wrappers are gone.
        """
        try:
            RunningScans = self.Repository.GetRunningScans()

            if not RunningScans:
                return {
                    'Success': True,
                    'IsScanning': False,
                    'Progress': 0.0,
                    'CurrentDirectory': '',
                    'RootFolderPath': '',
                    'Results': FileScanResultModel(),
                    'Errors': [],
                    'RunningScans': [],
                    'TotalRunningScans': 0
                }

            PrimaryScan = RunningScans[0]
            Results = FileScanResultModel()
            Results.Id = PrimaryScan['JobId']
            Results.RootFolderId = None
            Results.ScanStartTime = PrimaryScan['StartTime']
            Results.ScanEndTime = PrimaryScan['EndTime']
            Results.TotalFilesFound = PrimaryScan['TotalFiles'] or 0
            Results.TotalFilesProcessed = PrimaryScan['ProcessedFiles'] or 0
            Results.TotalFilesSkipped = PrimaryScan['SkippedFiles'] or 0
            Results.TotalFilesWithErrors = PrimaryScan['EncodingErrors'] or 0
            Results.ScanStatus = PrimaryScan['Status']
            Results.ErrorMessage = PrimaryScan['ErrorMessage']
            Results.ProcessId = PrimaryScan['ProcessId']

            Errors = [PrimaryScan['ErrorMessage']] if PrimaryScan['ErrorMessage'] else []

            self.IsScanning = True
            self.ScanProgress = PrimaryScan['Progress'] or 0.0
            self.CurrentScanDirectory = PrimaryScan['CurrentDirectory'] or ''

            return {
                'Success': True,
                'IsScanning': True,
                'Progress': PrimaryScan['Progress'] or 0.0,
                'CurrentDirectory': PrimaryScan['CurrentDirectory'] or '',
                'RootFolderPath': PrimaryScan['RootFolderPath'] or '',
                'Results': Results,
                'Errors': Errors,
                'Status': PrimaryScan['Status'],
                'JobId': PrimaryScan['JobId'],
                'ProcessId': PrimaryScan['ProcessId'],
                'RunningScans': RunningScans,
                'TotalRunningScans': len(RunningScans)
            }

        except Exception as e:
            LoggingService.LogException("Error getting scan status", e, "FileScanningBusinessService", "GetScanStatus")
            return {
                'Success': False,
                'IsScanning': False,
                'Progress': 0.0,
                'CurrentDirectory': '',
                'RootFolderPath': '',
                'Results': {},
                'Errors': [str(e)],
                'RunningScans': [],
                'TotalRunningScans': 0
            }

    def GetRootFolders(self, SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> List[RootFolderModel]:
        """Get all root folders with optional sorting."""
        try:
            return self.Repository.GetAllRootFolders(SortColumn, SortOrder)
        except Exception as e:
            LoggingService.LogException("Error getting root folders", e)
            return []

    def GetMediaFiles(self, RootFolderPath: Optional[str] = None) -> List[MediaFileModel]:
        """Get media files, optionally filtered by root folder."""
        try:
            if RootFolderPath:
                return self.Repository.GetMediaFilesByRootFolder(RootFolderPath)
            else:
                return self.Repository.GetAllMediaFiles()
        except Exception as e:
            LoggingService.LogException("Error getting media files", e)
            return []

    def AddRootFolder(self, RootFolderPath: str, PreferredWorkerName: str = None) -> Dict[str, Any]:
        """Add a new root folder for scanning.

        Validates the path format, checks for duplicates, and inserts into RootFolders.
        Does NOT require the path to be accessible from the WebService host -- the
        worker that scans it validates accessibility at scan time (criterion 20).
        """
        try:
            if not RootFolderPath or not RootFolderPath.strip():
                return {'Success': False, 'Message': 'Root folder path is required'}

            RootFolderPath = RootFolderPath.strip()
            # Ensure trailing backslash for drive roots (e.g. T:\ not T:)
            if len(RootFolderPath) == 2 and RootFolderPath[1] == ':':
                RootFolderPath += '\\'

            # directive: path-class-perfection | # see path.C23
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPM_DUP
            _PmDup = _GPM_DUP()
            Existing = self.Repository.GetAllRootFolders()
            for Folder in Existing:
                _FolderP = Folder.Path
                if _FolderP is None:
                    continue
                _Display = _FolderP.CanonicalDisplay(_PmDup)
                if _Display.lower().rstrip('\\') == RootFolderPath.lower().rstrip('\\'):
                    return {'Success': False, 'Message': f'Root folder already exists: {_Display}'}

            NewFolder = RootFolderModel(
                Id=None,
                RootFolder=RootFolderPath,
                LastScannedDate=None,
                TotalSizeGB=0.0,
                PreferredWorkerName=PreferredWorkerName,
            )
            NewId = self.Repository.SaveRootFolder(NewFolder)
            LoggingService.LogInfo(f"Added root folder: {RootFolderPath} (Id={NewId}, PreferredWorker={PreferredWorkerName})", 'FileScanningBusinessService', 'AddRootFolder')
            return {'Success': True, 'Message': 'Root folder added successfully', 'Data': {'Id': NewId, 'RootFolder': RootFolderPath}}

        except Exception as e:
            LoggingService.LogException("Error adding root folder", e, 'FileScanningBusinessService', 'AddRootFolder')
            return {'Success': False, 'Message': f'Error adding root folder: {str(e)}'}

    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            return self.Repository.DeleteRootFolder(RootFolderId)
        except Exception as e:
            LoggingService.LogException("Error deleting root folder", e)
            return False

    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete a media file."""
        try:
            return self.Repository.DeleteMediaFile(MediaFileId)
        except Exception as e:
            LoggingService.LogException("Error deleting media file", e)
            return False

    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all ScanDir%-prefixed entries from SystemSettings.

        Routed through SystemSettingsRepository per criterion 18d -- the
        FileScanningRepository duplicate methods were retired.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            return SystemSettingsRepository().GetScanDirectories()
        except Exception as e:
            LoggingService.LogException("Error getting scan directories", e)
            return []

    def GetStatistics(self) -> Dict[str, Any]:
        """Get library statistics for display."""
        try:
            Query = """
                SELECT
                    COUNT(*) AS TotalMediaFiles,
                    COUNT(CASE WHEN TranscodedByMediaVortex = true THEN 1 END) AS EncodedByMediaVortex,
                    COUNT(CASE WHEN FFProbeFailureCount >= 3 THEN 1 END) AS PossiblyCorrupt,
                    ROUND(SUM(SizeMB)::numeric / 1024, 1) AS TotalSizeGB
                FROM MediaFiles
            """
            Result = self.Repository.DatabaseService.ExecuteQuery(Query)
            Row = Result[0] if Result else {}

            SpaceSavedQuery = """
                SELECT ROUND(COALESCE(SUM(OldSizeBytes - NewSizeBytes), 0)::numeric / 1024 / 1024 / 1024, 1) AS SpaceSavedGB
                FROM TranscodeAttempts
                WHERE Success = true AND FileReplaced = true
            """
            SpaceSavedResult = self.Repository.DatabaseService.ExecuteQuery(SpaceSavedQuery)
            SpaceSavedGB = float(SpaceSavedResult[0]['SpaceSavedGB']) if SpaceSavedResult and SpaceSavedResult[0]['SpaceSavedGB'] else 0.0

            return {
                'TotalMediaFiles': Row.get('TotalMediaFiles', 0),
                'EncodedByMediaVortex': Row.get('EncodedByMediaVortex', 0),
                'SpaceSavedGB': SpaceSavedGB,
                'TotalSizeGB': float(Row.get('TotalSizeGB', 0) or 0),
                'PossiblyCorrupt': Row.get('PossiblyCorrupt', 0)
            }

        except Exception as e:
            LoggingService.LogException("Error getting statistics", e, "FileScanningBusinessService", "GetStatistics")
            return {
                'TotalMediaFiles': 0,
                'EncodedByMediaVortex': 0,
                'SpaceSavedGB': 0.0,
                'TotalSizeGB': 0.0,
                'PossiblyCorrupt': 0
            }

    def ResetScanState(self):
        """Reset the scan state to allow new scans."""
        # Clear current job reference
        self.CurrentJobId = None
        # Clean up old completed jobs
        self.CleanupCompletedJobs()

    # directive: paths-canonical-completion
    def ShouldExtractMetadata(self, MediaFile: MediaFileModel) -> bool:
        # see filescanning.ST4
        """Determine if metadata should be extracted for a media file based on change detection."""
        try:
            # Don't extract if media analysis is not available
            if not self.FileManager.IsMediaAnalysisAvailable():
                LoggingService.LogWarning("Media analysis not available - skipping metadata extraction", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return False

            LoggingService.LogDebug(f"Media analysis is available for file: {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')

            # Skip files that have exceeded the FFprobe failure limit
            if (MediaFile.FFprobeFailureCount or 0) >= MediaProbeBusinessService.MaxFFprobeFailures:
                LoggingService.LogDebug(f"Skipping file with {MediaFile.FFprobeFailureCount} probe failures (max {MediaProbeBusinessService.MaxFFprobeFailures}): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return False

            # Always extract for new files (no metadata at all)
            if (MediaFile.VideoBitrateKbps is None and
                MediaFile.AudioBitrateKbps is None and
                MediaFile.Resolution is None and
                MediaFile.Codec is None and
                MediaFile.DurationMinutes is None and
                MediaFile.FrameRate is None):
                LoggingService.LogDebug(f"File needs metadata extraction (new file): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Always extract if resolution is None (FFprobe analysis failed or never ran)
            if MediaFile.Resolution is None:
                LoggingService.LogDebug(f"File needs metadata extraction (no resolution): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Always extract if TotalFrames is missing (critical for transcode progress tracking)
            if MediaFile.TotalFrames is None:
                LoggingService.LogDebug(f"File needs metadata extraction (no TotalFrames): {MediaFile.FilePath}", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                return True

            # Check if file has changed (size or name)
            # Get current file information to compare
            try:
                WorkerName = _CurrentWorkerName()
                if _CanonicalExists(MediaFile.FilePath):
                    CurrentSizeMB = _CanonicalGetSize(MediaFile.FilePath) / (1024 * 1024)
                    CurrentFileName = ntpath.basename(MediaFile.FilePath)  # canonical display
                    CurrentModificationTime = self.GetFileModificationTime(MediaFile.FilePath)

                    if self.HasFileChanged(MediaFile, CurrentSizeMB, CurrentFileName, CurrentModificationTime):
                        return True
                else:
                    # File doesn't exist, should be cleaned up
                    LoggingService.LogWarning(f"File {MediaFile.FilePath} no longer exists", 'ShouldExtractMetadata', 'FileScanningBusinessService')
                    return False
            except Exception as e:
                LoggingService.LogException(f"Error checking file changes for {MediaFile.FilePath}", e, 'ShouldExtractMetadata', 'FileScanningBusinessService')
                # If we can't check, assume it needs analysis to be safe
                return True

            # File hasn't changed and has metadata, skip extraction
            return False

        except Exception as e:
            LoggingService.LogException("Error determining if metadata should be extracted", e, 'ShouldExtractMetadata', 'FileScanningBusinessService')
            return False

    # directive: paths-canonical-completion
    def GetFileModificationTime(self, FilePath: str) -> datetime:
        # see filescanning.ST4
        """Return the file modification time as a NAIVE datetime in UTC.
        Owns FileScanning.feature.md criterion 26 (cross-worker mtime
        consistency). The DB column is `timestamp without time zone`; if
        we let `fromtimestamp` interpret in the worker's local timezone,
        two workers in different timezones produce different stored values
        for the SAME physical file -- HasFileChanged then flips True for
        every file every time a different worker scans, generating a
        cross-worker write storm. Always interpreting the POSIX timestamp
        in UTC and stripping the tz back to naive makes the stored value
        worker-independent.
        """
        try:
            ModificationTime = LocalGetMTime(FilePath)
            # Windows datetime.fromtimestamp() cannot handle negative timestamps (pre-1970 dates)
            if ModificationTime < 0:
                ModificationTime = 0
            return datetime.fromtimestamp(ModificationTime, tz=timezone.utc).replace(tzinfo=None)
        except Exception as e:
            LoggingService.LogException(f"Error getting file modification time for {FilePath}", e, 'GetFileModificationTime', 'FileScanningBusinessService')
            return datetime.now(timezone.utc).replace(tzinfo=None)

    def HasFileChanged(self, MediaFile: MediaFileModel, CurrentSizeMB: float, CurrentFileName: str, CurrentModificationTime: datetime) -> bool:
        """Check if a file has changed by comparing size, name, and modification time."""
        try:
            # Compare with stored values
            SizeChanged = abs(CurrentSizeMB - MediaFile.SizeMB) > 0.1  # Allow small floating point differences
            NameChanged = CurrentFileName != MediaFile.FileName

            # Compare modification time (allow 1 second tolerance for filesystem precision)
            ModificationTimeChanged = False
            if MediaFile.FileModificationTime and CurrentModificationTime:
                # Handle case where FileModificationTime might be a string from database
                StoredModificationTime = MediaFile.FileModificationTime
                if isinstance(StoredModificationTime, str):
                    try:
                        from datetime import datetime
                        StoredModificationTime = datetime.fromisoformat(StoredModificationTime.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # If we can't parse the string, assume it changed
                        ModificationTimeChanged = True
                else:
                    TimeDifference = abs((CurrentModificationTime - StoredModificationTime).total_seconds())
                    ModificationTimeChanged = TimeDifference > 1.0

            if SizeChanged or NameChanged or ModificationTimeChanged:
                LoggingService.LogDebug(f"File changed detected for {MediaFile.FilePath}: Size={SizeChanged}, Name={NameChanged}, ModTime={ModificationTimeChanged}", 'FileScanningBusinessService', 'HasFileChanged')
                return True

            return False

        except Exception as e:
            LoggingService.LogException("Error checking if file has changed", e, 'HasFileChanged', 'FileScanningBusinessService')
            # If we can't check, assume it changed to be safe
            return True

    # directive: paths-canonical-completion
    def IsSameFile(self, DbFile: MediaFileModel, FilePath: str) -> bool:
        # see filescanning.ST5
        """Check if a file at a given path is the same as a database file record."""
        try:
            if not LocalExists(FilePath):
                return False

            # mtime in UTC: see FileScanning.feature.md C26 for cross-worker invariant.
            CurrentSize = LocalGetSize(FilePath) / (1024 * 1024)  # MB
            CurrentModTime = datetime.fromtimestamp(LocalGetMTime(FilePath), tz=timezone.utc).replace(tzinfo=None)

            # Allow 1MB size difference (to account for transcoding compression)
            SizeMatch = abs(CurrentSize - DbFile.SizeMB) < 1.0

            # Allow 2 second modification time difference (to account for filesystem precision)
            TimeMatch = True
            if DbFile.FileModificationTime and CurrentModTime:
                # Handle case where FileModificationTime might be a string from database
                StoredModTime = DbFile.FileModificationTime
                if isinstance(StoredModTime, str):
                    try:
                        StoredModTime = datetime.fromisoformat(StoredModTime.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # If we can't parse, just use size match
                        TimeMatch = True
                else:
                    TimeDifference = abs((CurrentModTime - StoredModTime).total_seconds())
                    TimeMatch = TimeDifference < 2.0

            IsMatch = SizeMatch and TimeMatch
            if IsMatch:
                LoggingService.LogDebug(f"File match confirmed: DB '{DbFile.FilePath}' matches '{FilePath}' (Size: {DbFile.SizeMB}MB vs {CurrentSize}MB)", 'IsSameFile', 'FileScanningBusinessService')

            return IsMatch

        except Exception as e:
            LoggingService.LogException("Error checking if files are the same", e, 'IsSameFile', 'FileScanningBusinessService')
            return False

    def UpdateLastScannedDate(self, MediaFileId: int, LastScannedDate: datetime):
        """Update only the LastScannedDate for a media file without full save."""
        try:
            Query = "UPDATE MediaFiles SET LastScannedDate = %s WHERE Id = %s"
            self.Repository.DatabaseService.ExecuteNonQuery(Query, (LastScannedDate, MediaFileId))
        except Exception as e:
            LoggingService.LogException(f"Error updating LastScannedDate for file ID {MediaFileId}", e, 'UpdateLastScannedDate', 'FileScanningBusinessService')

    def ExtractAndUpdateMetadata(self, MediaFile: MediaFileModel, FilePath: str):
        """Extract metadata and update the media file model."""
        try:
            LoggingService.LogDebug(f"Extracting metadata for: {FilePath}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')

            # Update file size, name, and modification time to current values (in case file changed)
            MediaFile.SizeMB = self.FileManager.GetFileSizeMB(FilePath)
            MediaFile.FileName = self.FileManager.GetFileNameFromPath(FilePath)
            MediaFile.FileModificationTime = self.GetFileModificationTime(FilePath)

            # Extract metadata using FileManagerService
            MetadataResult = self.FileManager.ExtractMediaMetadata(FilePath)

            # Log what metadata we extracted

            if MetadataResult.get('Success', False):
                # Update the media file with extracted metadata
                MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
                MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
                MediaFile.Resolution = MetadataResult.get('Resolution')
                MediaFile.Codec = MetadataResult.get('VideoCodec')
                MediaFile.DurationMinutes = MetadataResult.get('DurationMinutes')
                MediaFile.FrameRate = MetadataResult.get('FrameRate')

                # Extract new metadata fields
                MediaFile.TotalFrames = MetadataResult.get('TotalFrames')
                MediaFile.CodecProfile = MetadataResult.get('CodecProfile')
                MediaFile.ColorRange = MetadataResult.get('ColorRange')
                MediaFile.FieldOrder = MetadataResult.get('FieldOrder')
                MediaFile.HasBFrames = MetadataResult.get('HasBFrames')
                MediaFile.RefFrames = MetadataResult.get('RefFrames')
                MediaFile.PixelFormat = MetadataResult.get('PixelFormat')
                MediaFile.Level = MetadataResult.get('Level')
                MediaFile.AudioChannels = MetadataResult.get('AudioChannels')
                MediaFile.AudioSampleRate = MetadataResult.get('AudioSampleRate')
                MediaFile.AudioSampleFormat = MetadataResult.get('AudioSampleFormat')
                MediaFile.AudioChannelLayout = MetadataResult.get('AudioChannelLayout')
                MediaFile.AudioCodec = MetadataResult.get('AudioCodec')
                MediaFile.SubtitleFormats = MetadataResult.get('SubtitleFormats')
                MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
                MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')

                # Derive ResolutionCategory from Resolution
                if MediaFile.Resolution and 'x' in MediaFile.Resolution:
                    try:
                        Height = int(MediaFile.Resolution.split('x')[1])
                        if Height >= 2160:
                            MediaFile.ResolutionCategory = "2160p"
                        elif Height >= 1080:
                            MediaFile.ResolutionCategory = "1080p"
                        elif Height >= 720:
                            MediaFile.ResolutionCategory = "720p"
                        else:
                            MediaFile.ResolutionCategory = "480p"
                    except (ValueError, IndexError):
                        pass

                LoggingService.LogDebug(f"Successfully extracted metadata for: {FilePath}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
                # Clear failure tracking on success
                MediaFile.FFprobeFailureCount = 0
                MediaFile.LastFFprobeError = None
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)
            else:
                # Record failure
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"Failed to extract metadata for {FilePath}: {ErrorMessage}", 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
                MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
                MediaFile.LastFFprobeError = ErrorMessage
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)

        except Exception as e:
            LoggingService.LogException("Error extracting and updating metadata", e, 'ExtractAndUpdateMetadata', 'FileScanningBusinessService')
            MediaFile.FFprobeFailureCount = (MediaFile.FFprobeFailureCount or 0) + 1
            MediaFile.LastFFprobeError = str(e)
            MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)

    # directive: path-schema-migration | # see path.S8
    def ReconcileWithDisk(self, MediaFiles: List[str], RootFolderId: int) -> Dict[str, Any]:
        # see filescanning.ST5
        """Single-pass merge of move-detection and missing-file cleanup against
        the disk file list already produced by `FileManager.ScanDirectory`.
        Owns FileScanning.feature.md criterion 23 (throughput dimension) and
        moves this code path to the path-storage Phase 4 read pattern: set
        membership is computed on `(StorageRootId, RelativePath.lower())`
        tuples, not on OS-coupled `FilePath` strings. Same comparison works
        identically on Windows and Linux workers; no `_ToCanonicalPath`
        round-trip in the comparison hot path.

        Per-row decision:
          - DB row's `(StorageRootId, RelativePath.lower())` in disk set ->
            skip; the per-file processor handles it normally.
          - DB row has NULL StorageRootId (rows that missed the Phase 2
            backfill, ~2 in production) -> preserve; never delete.
          - Not in disk set, fuzzy match found by basename + IsSameFile ->
            update DB row's FilePath / FileName / StorageRootId /
            RelativePath in place (preserves Id and metadata).
          - Not in disk set, no fuzzy match -> delete DB row.

        Safety guard: if proposed delete count exceeds 90% of DatabaseFiles,
        abort the reconcile entirely and log an error. This catches the
        catastrophic translation-failure case where every disk path falls
        outside any registered StorageRoot (e.g. WorkerShareMappings missing
        on a worker that shouldn't have been ScanEnabled).

        Move-detection cap (criterion 12) is preserved: above the cap, the
        fuzzy-match step is skipped and missing rows are deleted directly
        rather than reassigned. The throughput win still applies; only the
        rename-recovery semantics degrade.
        """
        try:
            LoggingService.LogInfo(
                f"=== RECONCILE WITH DISK STARTED ({len(MediaFiles)} disk files) ===",
                'ReconcileWithDisk', 'FileScanningBusinessService'
            )

            StorageRoots = _GetStorageRoots()

            # OS-independent disk set keyed on (StorageRootId, RelativePath.lower()); unparseable disk paths skipped.
            DiskSet: set = set()
            DiskByBasenameLower: Dict[str, List[tuple]] = {}
            UnparseableCount = 0
            for CanonicalPath in MediaFiles:
                try:
                    _PPair = Path.FromLegacyString(CanonicalPath, StorageRoots)
                    Sid, Rel = _PPair.StorageRootId, _PPair.RelativePath
                except PathError:
                    Sid, Rel = None, None
                if Sid is None or Rel is None:
                    UnparseableCount += 1
                    continue
                DiskSet.add((Sid, Rel.lower()))
                Basename = ntpath.basename(CanonicalPath).lower()  # canonical display
                DiskByBasenameLower.setdefault(Basename, []).append((CanonicalPath, Sid, Rel))
            if UnparseableCount > 0:
                LoggingService.LogWarning(
                    f"Reconcile: {UnparseableCount} disk paths did not match any registered StorageRoot prefix; skipped from disk set",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )

            RootFolder = self.Repository.GetRootFolderById(RootFolderId)
            if not RootFolder:
                LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'ReconcileWithDisk', 'FileScanningBusinessService')
                return {'Success': False, 'ErrorMessage': 'Root folder not found'}
            # directive: path-class-perfection | # see path.C23
            _RfDisplay = str(RootFolder.Path) if RootFolder.Path is not None else ''
            DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(_RfDisplay)

            MaxFiles = self._GetMoveDetectionMaxFiles()
            MoveDetectionEnabled = len(DatabaseFiles) <= MaxFiles
            if not MoveDetectionEnabled:
                LoggingService.LogWarning(
                    f"Move detection disabled: {len(DatabaseFiles)} DB rows exceed limit {MaxFiles}; missing files will be deleted, not reassigned",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )

            # First pass: classify every DB row as keep / reassign / delete WITHOUT
            # mutating the database. Lets the safety guard veto the whole reconcile
            # before a single row is touched.
            ToReassign: List[tuple] = []  # (DbFile, CandidateCanonical, CandidateSid, CandidateRel)
            ToDelete: List = []  # DbFile rows to delete
            PreservedNullStorageRoot = 0
            for DbFile in DatabaseFiles:
                DbSid = getattr(DbFile, 'StorageRootId', None)
                DbRel = getattr(DbFile, 'RelativePath', None) or ''
                if DbSid is None:
                    PreservedNullStorageRoot += 1
                    continue  # row missed Phase 2 backfill; never delete here
                if (DbSid, DbRel.lower()) in DiskSet:
                    continue  # exists on disk

                ResolvedMove = None
                if MoveDetectionEnabled and DbFile.FileName:
                    Candidates = DiskByBasenameLower.get(DbFile.FileName.lower(), [])
                    for (CandidateCanonical, CandidateSid, CandidateRel) in Candidates:
                        if (CandidateSid, CandidateRel.lower()) == (DbSid, DbRel.lower()):
                            continue  # same logical path
                        LocalCandidate = self._ToLocalPath(CandidateCanonical)
                        if self.IsSameFile(DbFile, LocalCandidate):
                            ResolvedMove = (CandidateCanonical, CandidateSid, CandidateRel)
                            break

                if ResolvedMove:
                    ToReassign.append((DbFile, *ResolvedMove))
                else:
                    ToDelete.append(DbFile)

            # Safety guard: refuse to delete >90% of DB rows in one reconcile pass.
            # Catches the "translation broken on this worker, every row looks
            # missing" failure mode that would otherwise wipe the rootfolder.
            if DatabaseFiles and len(ToDelete) > 0.9 * len(DatabaseFiles):
                LoggingService.LogError(
                    f"Reconcile ABORTED: would delete {len(ToDelete)} of {len(DatabaseFiles)} rows "
                    f"({100.0 * len(ToDelete) / len(DatabaseFiles):.1f}%). Likely translation failure -- "
                    f"check StorageRootResolutions for this worker. Disk set has {len(DiskSet)} entries; "
                    f"{UnparseableCount} disk paths were unparseable.",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                return {
                    'Success': False,
                    'ErrorMessage': 'Reconcile safety guard tripped (>90% delete proposal)',
                    'ProposedDeletes': len(ToDelete),
                    'DatabaseRows': len(DatabaseFiles),
                }

            # Second pass: execute the planned mutations.
            MovedCount = 0
            DeletedCount = 0
            for (DbFile, CandidateCanonical, CandidateSid, CandidateRel) in ToReassign:
                LoggingService.LogInfo(
                    f"Reassigning moved file: {DbFile.FilePath} -> {CandidateCanonical}",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                DbFile.FileName = ntpath.basename(CandidateCanonical)  # canonical display
                DbFile.StorageRootId = CandidateSid
                DbFile.RelativePath = CandidateRel
                DbFile.LastScannedDate = datetime.now(timezone.utc)
                self.Repository.SaveMediaFile(DbFile)
                MovedCount += 1
                self.ScanResults.UpdatedFilesCount += 1
            for DbFile in ToDelete:
                LoggingService.LogInfo(
                    f"Deleting DB row for missing file: {DbFile.FilePath} (Id={DbFile.Id})",
                    'ReconcileWithDisk', 'FileScanningBusinessService'
                )
                self.Repository.DeleteMediaFile(DbFile.Id)
                DeletedCount += 1
                self.ScanResults.DeletedFilesCount += 1

            LoggingService.LogInfo(
                f"=== RECONCILE WITH DISK COMPLETED === moved={MovedCount} deleted={DeletedCount} preserved_null_storageroot={PreservedNullStorageRoot}",
                'ReconcileWithDisk', 'FileScanningBusinessService'
            )
            return {'Success': True, 'MovedFiles': MovedCount, 'DeletedFiles': DeletedCount, 'PreservedNullStorageRoot': PreservedNullStorageRoot}
        except Exception as e:
            LoggingService.LogException("Error in ReconcileWithDisk", e, 'ReconcileWithDisk', 'FileScanningBusinessService')
            return {'Success': False, 'ErrorMessage': str(e)}

    # directive: paths-canonical-completion
    def CleanupMissingFiles(self, RootFolderId: Optional[int] = None):
        # see filescanning.ST5
        """Remove database records for files that no longer exist on disk."""
        try:
            LoggingService.LogInfo("=== CLEANUP MISSING FILES STARTED ===", 'CleanupMissingFiles', 'FileScanningBusinessService')

            if RootFolderId:
                # Get root folder path
                RootFolder = self.Repository.GetRootFolderById(RootFolderId)
                if not RootFolder:
                    LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'CleanupMissingFiles', 'FileScanningBusinessService')
                    return

                # directive: path-class-perfection | # see path.C23
                _RfDisplayCM = str(RootFolder.Path) if RootFolder.Path is not None else ''
                DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(_RfDisplayCM)
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} database files for root folder: {_RfDisplayCM}", 'CleanupMissingFiles', 'FileScanningBusinessService')
            else:
                # Get all files in database
                DatabaseFiles = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} total database files", 'CleanupMissingFiles', 'FileScanningBusinessService')

            # Check each database file to see if it actually exists on disk
            # Translate canonical (Windows-style) DB path to local for the fs check.
            DeletedCount = 0
            for DbFile in DatabaseFiles:
                if not _CanonicalExists(DbFile.FilePath):
                    LoggingService.LogInfo(f"FILE NOT FOUND ON DISK - DELETING FROM DATABASE: {DbFile.FilePath}", 'CleanupMissingFiles', 'FileScanningBusinessService')

                    # Delete directly using the database service
                    DeleteQuery = "DELETE FROM MediaFiles WHERE Id = %s"
                    AffectedRows = self.Repository.DatabaseService.ExecuteNonQuery(DeleteQuery, (DbFile.Id,))

                    if AffectedRows > 0:
                        LoggingService.LogInfo(f"SUCCESS: Deleted missing file from database: {DbFile.FilePath} (ID: {DbFile.Id})", 'CleanupMissingFiles', 'FileScanningBusinessService')
                        DeletedCount += 1
                    else:
                        LoggingService.LogWarning(f"Failed to delete missing file from database: {DbFile.FilePath} (ID: {DbFile.Id})", 'CleanupMissingFiles', 'FileScanningBusinessService')

            LoggingService.LogInfo("=== CLEANUP MISSING FILES COMPLETED ===", 'CleanupMissingFiles', 'FileScanningBusinessService')
            if DeletedCount > 0:
                LoggingService.LogInfo(f"SUCCESS: Cleaned up {DeletedCount} missing files from database", 'CleanupMissingFiles', 'FileScanningBusinessService')
            else:
                LoggingService.LogInfo("No missing files found to clean up", 'CleanupMissingFiles', 'FileScanningBusinessService')

        except Exception as e:
            LoggingService.LogException("CRITICAL ERROR in CleanupMissingFiles", e, 'CleanupMissingFiles', 'FileScanningBusinessService')

    # directive: paths-canonical-completion
    def FindMovedFile(self, DbFile: MediaFileModel) -> Optional[Dict[str, str]]:
        # see filescanning.ST5
        """Try to find a moved file by searching all root folders."""
        try:
            LoggingService.LogDebug(f"Searching for moved file: {DbFile.FileName}", 'FindMovedFile', 'FileScanningBusinessService')

            # Get the filename to search for
            SearchFileName = DbFile.FileName

            # directive: path-class-perfection | # see path.C23
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPM_FMF
            _PmFmf = _GPM_FMF()
            AllRootFolders = self.Repository.GetAllRootFolders()

            for RootFolder in AllRootFolders:
                _RfP = RootFolder.Path
                if _RfP is None:
                    continue
                _RfDisplayFM = _RfP.CanonicalDisplay(_PmFmf)
                LocalRoot = self._ToLocalPath(_RfDisplayFM)
                if not LocalExists(LocalRoot):
                    LoggingService.LogDebug(f"Root folder does not exist (local: {LocalRoot}): {_RfDisplayFM}", 'FindMovedFile', 'FileScanningBusinessService')
                    continue

                try:
                    for root, dirs, files in os.walk(LocalRoot):
                        for file in files:
                            if file == SearchFileName:
                                FoundLocalPath = LocalJoin(root, file)
                                FoundCanonicalPath = self._ToCanonicalPath(FoundLocalPath)

                                if FoundCanonicalPath.lower() == DbFile.FilePath.lower():
                                    continue

                                if self.IsSameFile(DbFile, FoundLocalPath):
                                    LoggingService.LogInfo(f"MOVED FILE FOUND: '{DbFile.FilePath}' -> '{FoundCanonicalPath}'", 'FindMovedFile', 'FileScanningBusinessService')
                                    return {
                                        'OldPath': DbFile.FilePath,
                                        'NewPath': FoundCanonicalPath,
                                    }

                except Exception as e:
                    LoggingService.LogException(f"Error searching root folder: {_RfDisplayFM}", e, 'FindMovedFile', 'FileScanningBusinessService')
                    continue

            LoggingService.LogDebug(f"No moved location found for: {DbFile.FileName}", 'FindMovedFile', 'FileScanningBusinessService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding moved file", e, 'FindMovedFile', 'FileScanningBusinessService')
            return None

    def _GetMoveDetectionMaxFiles(self) -> int:
        """Read the move-detection ceiling from SystemSettings each call (no cache)."""
        Default = 100000
        try:
            Result = self.Repository.DatabaseService.ExecuteQuery(
                "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s",
                ('MoveDetectionMaxFiles',),
            )
            if Result:
                Value = Result[0].get('SettingValue')
                if Value is not None:
                    return int(Value)
        except Exception as e:
            LoggingService.LogException("Error reading MoveDetectionMaxFiles, using default", e, 'FileScanningBusinessService', '_GetMoveDetectionMaxFiles')
        return Default

    # directive: path-schema-migration | # see path.S8
    def DetectMovedFiles(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        # see filescanning.ST5
        """Detect files that have been moved and update their paths."""
        try:
            LoggingService.LogInfo("=== DETECT MOVED FILES STARTED ===", 'DetectMovedFiles', 'FileScanningBusinessService')

            MovedFiles = []
            DeletedFiles = []

            # Get all files (or files for specific root folder)
            if RootFolderId:
                RootFolder = self.Repository.GetRootFolderById(RootFolderId)
                if not RootFolder:
                    LoggingService.LogError(f"Root folder not found for ID: {RootFolderId}", 'DetectMovedFiles', 'FileScanningBusinessService')
                    return {'Success': False, 'ErrorMessage': 'Root folder not found'}

                # directive: path-class-perfection | # see path.C23
                _RfDisplayDM = str(RootFolder.Path) if RootFolder.Path is not None else ''
                DatabaseFiles = self.Repository.GetMediaFilesByRootFolder(_RfDisplayDM)
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} files in root folder: {_RfDisplayDM}", 'DetectMovedFiles', 'FileScanningBusinessService')
            else:
                DatabaseFiles = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Checking {len(DatabaseFiles)} total database files", 'DetectMovedFiles', 'FileScanningBusinessService')

            # Performance ceiling: skip move detection above SystemSettings('MoveDetectionMaxFiles').
            # Read fresh from the DB on every call (do not cache) so an operator can raise the cap
            # without restarting workers. Default 100000 mirrors the migration seed.
            MaxFiles = self._GetMoveDetectionMaxFiles()
            if len(DatabaseFiles) > MaxFiles:
                LoggingService.LogWarning(f"Skipping move detection: Database has {len(DatabaseFiles)} files (exceeds limit of {MaxFiles})", 'DetectMovedFiles', 'FileScanningBusinessService')
                return {
                    'Success': True,
                    'MovedFiles': 0,
                    'DeletedFiles': 0,
                    'Skipped': True,
                    'Reason': f'File count exceeds limit ({len(DatabaseFiles)} > {MaxFiles})'
                }

            # Check each file for moves (translate canonical -> local for fs check)
            for DbFile in DatabaseFiles:
                if not _CanonicalExists(DbFile.FilePath):
                    # File missing - try to find it
                    MovedFile = self.FindMovedFile(DbFile)

                    if MovedFile:
                        # File was moved, update typed-pair identity (FilePath is derived)
                        LoggingService.LogInfo(f"Updating moved file: {MovedFile['OldPath']} -> {MovedFile['NewPath']}", 'DetectMovedFiles', 'FileScanningBusinessService')
                        _P = Path.FromLegacyString(MovedFile['NewPath'], _GetStorageRoots())
                        DbFile.StorageRootId = _P.StorageRootId
                        DbFile.RelativePath = _P.RelativePath
                        DbFile.FileName = ntpath.basename(MovedFile['NewPath'])  # canonical display
                        DbFile.LastScannedDate = datetime.now(timezone.utc)
                        self.Repository.SaveMediaFile(DbFile)
                        MovedFiles.append({
                            'OldPath': MovedFile['OldPath'],
                            'NewPath': MovedFile['NewPath'],
                            'FileName': DbFile.FileName
                        })
                    else:
                        # File was deleted (will be cleaned up by CleanupMissingFiles)
                        DeletedFiles.append({
                            'FilePath': DbFile.FilePath,
                            'FileName': DbFile.FileName
                        })

            LoggingService.LogInfo("=== DETECT MOVED FILES COMPLETED ===", 'DetectMovedFiles', 'FileScanningBusinessService')
            LoggingService.LogInfo(f"Results: {len(MovedFiles)} files moved, {len(DeletedFiles)} files deleted", 'DetectMovedFiles', 'FileScanningBusinessService')

            return {
                'Success': True,
                'MovedFiles': len(MovedFiles),
                'DeletedFiles': len(DeletedFiles),
                'MovedFilesList': MovedFiles,
                'DeletedFilesList': DeletedFiles
            }

        except Exception as e:
            LoggingService.LogException("Error detecting moved files", e, 'DetectMovedFiles', 'FileScanningBusinessService')
            return {
                'Success': False,
                'ErrorMessage': str(e),
                'MovedFiles': 0,
                'DeletedFiles': 0
            }

    # directive: paths-canonical-completion
    def ProcessMediaFilesWithMetadata(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
        # see filescanning.ST4
        """Process media files with optional metadata extraction using parallel processing."""
        try:
            LoggingService.LogFunctionEntry("ProcessMediaFilesWithMetadata", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")

            # Reconcile DB rows against the disk file list in a single pass.
            # Replaces the previous DetectMovedFiles + CleanupMissingFiles
            # sequence which serially stat-checked every DB row twice over
            # NFS (criterion 23 fix).
            if RootFolderId:
                # Directive 2026-05-27 criterion 13: phase transition visible to operator.
                self._SetPhase(self.CurrentJobId, 'Reconciling')
                ReconcileResult = self.ReconcileWithDisk(MediaFiles, RootFolderId)
                LoggingService.LogInfo(
                    f"Reconcile result: moved={ReconcileResult.get('MovedFiles', 0)} deleted={ReconcileResult.get('DeletedFiles', 0)}",
                    'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService'
                )
            # Per-file insert/update pass -- back to Walking semantically (the bar
            # tracks ProcessedFiles / TotalFiles which is what the operator wants
            # to see during this slice).
            self._SetPhase(self.CurrentJobId, 'Walking')

            TotalFiles = len(MediaFiles)
            ProcessedCount = 0
            ProgressLock = threading.Lock()

            def ProcessSingleFile(FilePath: str):
                """Process a single file and return result."""
                nonlocal ProcessedCount

                # Directive 2026-05-27 criterion 21: soft-stop. The heartbeat thread
                # observes ScanJobs.Status='Stopping' and flips _StopRequested; we exit
                # without queuing additional disk/DB work for remaining files.
                if self._StopRequested:
                    return {'Success': False, 'FilePath': FilePath, 'Error': 'Stopped'}

                try:
                    # Process the file with metadata extraction
                    self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath, ExtractMetadata)

                    # Update progress thread-safely. Mirror to ScanResults so
                    # the heartbeat thread (criterion 17) writes a real
                    # ProcessedFiles count, not zero, mid-scan.
                    with ProgressLock:
                        ProcessedCount += 1
                        Progress = 30.0 + (60.0 * ProcessedCount / TotalFiles)
                        self.ScanProgress = Progress
                        self.ScanResults.TotalFilesProcessed = ProcessedCount
                        self.CurrentScanDirectory = ntpath.dirname(FilePath)  # canonical display

                    return {'Success': True, 'FilePath': FilePath}
                except Exception as e:
                    LoggingService.LogException(f"Error processing media file: {FilePath}", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                    ErrorMessage = f"Error processing {FilePath}: {str(e)}"
                    with ProgressLock:
                        self.ScanErrors.append(ErrorMessage)
                    return {'Success': False, 'FilePath': FilePath, 'Error': str(e)}

            # Process files in parallel with 5 workers
            MaxWorkers = 5
            with ThreadPoolExecutor(max_workers=MaxWorkers) as Executor:
                # Submit all files for processing
                FutureToFile = {Executor.submit(ProcessSingleFile, FilePath): FilePath for FilePath in MediaFiles}

                # Wait for all tasks to complete
                for Future in as_completed(FutureToFile):
                    FilePath = FutureToFile[Future]
                    try:
                        Result = Future.result()
                        if not Result.get('Success', False):
                            LoggingService.LogWarning(f"Failed to process file: {FilePath}", 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                    except Exception as e:
                        LoggingService.LogException(f"Exception in future for file: {FilePath}", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
                        with ProgressLock:
                            self.ScanErrors.append(f"Error processing {FilePath}: {str(e)}")

            # Note: Duplicate file detection has been moved to a separate process
            # to avoid slowing down the scanning process. Use the dedicated
            # duplicate detection methods when needed.


        except Exception as e:
            LoggingService.LogException("Error processing media files with metadata", e, 'ProcessMediaFilesWithMetadata', 'FileScanningBusinessService')
            raise

    def ExtractMetadataForExistingFiles(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Extract metadata for existing files that don't have metadata."""
        try:
            LoggingService.LogFunctionEntry("ExtractMetadataForExistingFiles", 'FileScanningBusinessService', f"RootFolderId: {RootFolderId}")

            if not self.FileManager.IsMediaAnalysisAvailable():
                return {
                    'Success': False,
                    'Message': 'Media analysis service not available',
                    'Error': 'MediaAnalysisNotAvailable'
                }

            # Get files that need metadata extraction
            # Filter by root folder if RootFolderId is provided, otherwise get all files
            if RootFolderId is not None:
                FilesNeedingMetadata = self.Repository.GetMediaFilesByRootFolderId(RootFolderId)
                LoggingService.LogInfo(f"Found {len(FilesNeedingMetadata)} files for RootFolderId: {RootFolderId}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
            else:
                FilesNeedingMetadata = self.Repository.GetAllMediaFiles()
                LoggingService.LogInfo(f"Found {len(FilesNeedingMetadata)} total files for metadata extraction", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

            # Filter files that need metadata
            FilesToProcess = []
            for File in FilesNeedingMetadata:
                if self.ShouldExtractMetadata(File):
                    FilesToProcess.append(File)

            LoggingService.LogInfo(f"Files needing metadata extraction: {len(FilesToProcess)} out of {len(FilesNeedingMetadata)}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

            if not FilesToProcess:
                return {
                    'Success': True,
                    'Message': 'No files need metadata extraction',
                    'ProcessedFiles': 0
                }


            # Process files in batches
            BatchSize = 10
            ProcessedCount = 0

            for i in range(0, len(FilesToProcess), BatchSize):
                Batch = FilesToProcess[i:i + BatchSize]

                for File in Batch:
                    try:
                        # Extract metadata and update file
                        self.ExtractAndUpdateMetadata(File, File.FilePath)
                        self.Repository.SaveMediaFile(File)
                        ProcessedCount += 1

                        LoggingService.LogDebug(f"Extracted metadata for: {File.FilePath}", 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')

                    except Exception as e:
                        LoggingService.LogException(f"Error extracting metadata for: {File.FilePath}", e, 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
                        continue


            return {
                'Success': True,
                'Message': f'Successfully extracted metadata for {ProcessedCount} files',
                'ProcessedFiles': ProcessedCount
            }

        except Exception as e:
            LoggingService.LogException("Error extracting metadata for existing files", e, 'ExtractMetadataForExistingFiles', 'FileScanningBusinessService')
            return {
                'Success': False,
                'Message': f'Error extracting metadata: {str(e)}',
                'Error': 'MetadataExtractionError'
            }

    def AddOrUpdateScanDirectory(self, Key: Optional[str], Path: str, Description: str) -> Dict[str, Any]:
        """Add or update a ScanDir%% SystemSettings entry. Routes through
        SystemSettingsRepository per criterion 18d.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            settings = SystemSettingsRepository()

            if not Key:
                # Pick next ScanDir<N>
                Existing = settings.GetScanDirectories()
                Numbers = []
                for E in Existing:
                    K = E.get('Key', '')
                    if K.startswith('ScanDir'):
                        try:
                            Numbers.append(int(K.replace('ScanDir', '')))
                        except ValueError:
                            continue
                NextNumber = 1
                while NextNumber in Numbers:
                    NextNumber += 1
                Key = f'ScanDir{NextNumber}'

            result = settings.AddOrUpdateSystemSetting(Key, Path, Description, 'string')
            if result:
                return {'Success': True, 'Message': f'Successfully saved scan directory: {Path}'}
            return {'Success': False, 'Error': 'Failed to save scan directory to database'}

        except Exception as e:
            LoggingService.LogException("Error adding/updating scan directory", e, "AddOrUpdateScanDirectory", "FileScanningBusinessService")
            return {'Success': False, 'Error': f'Error adding/updating scan directory: {str(e)}'}

    def DeleteScanDirectory(self, Key: str) -> Dict[str, Any]:
        """Delete a ScanDir%% SystemSettings entry. Routes through
        SystemSettingsRepository per criterion 18d.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            result = SystemSettingsRepository().DeleteSystemSetting(Key)
            if result:
                return {'Success': True, 'Message': f'Successfully deleted scan directory: {Key}'}
            return {'Success': False, 'Error': f'Scan directory {Key} not found or could not be deleted'}

        except Exception as e:
            LoggingService.LogException("Error deleting scan directory", e, "DeleteScanDirectory", "FileScanningBusinessService")
            return {'Success': False, 'Error': f'Error deleting scan directory: {str(e)}'}

