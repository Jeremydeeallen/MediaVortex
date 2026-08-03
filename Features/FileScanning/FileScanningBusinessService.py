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
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
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
        _FS_WORKER_HOLDER["_Worker"] = Worker.Current()
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
        Ctx = WorkerContext.TryCurrent()
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
        self.MediaFilesRepository = MediaFilesRepository(self.Repository.DatabaseService)
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

    # directive: transcode-flow-canonical -- fail loud; caller must distinguish resolve-failure from disk-missing
    def _ToLocalPath(self, CanonicalPath: str) -> str:
        from Core.Path.Path import Path as _Path
        from Core.Path.PathStorageRoots import GetStorageRoots as _GSR
        from Core.Path.Worker import Worker as _W
        return _Path.FromLegacyString(CanonicalPath, _GSR()).Resolve(_W.Current(Db=self.Repository.DatabaseService))

    # directive: path-perfect-implementation | # see path.S11
    def _ToCanonicalPath(self, LocalPath: str) -> str:
        try:
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPM
            from Core.Path.Worker import Worker as _W
            P = _W.Current(Db=self.Repository.DatabaseService).LocalToPath(LocalPath)
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
                    Ctx = WorkerContext.TryCurrent()
                    if Ctx is not None:
                        WorkerName = Ctx.WorkerName
                except Exception:
                    pass

            # directive: transcode-flow-canonical -- per-rootfolder claim enforced by DB partial UNIQUE index sj_one_active_per_root; INSERT ... ON CONFLICT DO NOTHING is the atomic claim

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

            JobId = str(uuid.uuid4())
            self.CurrentJobId = JobId

            # directive: transcode-flow-canonical -- atomic claim; loser returns cleanly
            if not self.CreateScanJob(JobId, RootFolderPath, Recursive, WorkerName=WorkerName):
                self.CurrentJobId = None
                return {
                    'Success': False,
                    'Message': f'Scan already running for {RootFolderPath}',
                    'Error': 'ScanAlreadyRunning'
                }

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

    # directive: transcode-flow-canonical -- atomic per-rootfolder claim via ON CONFLICT DO NOTHING; returns True on win, False if another worker already has an active scan for this StorageRootId+RelativePath
    def CreateScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool, WorkerName: Optional[str] = None) -> bool:
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
                "SELECT %s, %s, %s, %s, 'Running', %s, %s, 'File', %s "
                "WHERE NOT EXISTS ( "
                "  SELECT 1 FROM ScanJobs sj_dup "
                "  WHERE sj_dup.StorageRootId = %s "
                "    AND COALESCE(sj_dup.RelativePath, '') = COALESCE(%s, '') "
                "    AND sj_dup.Status IN ('Pending', 'Running') "
                ")"
            )
            Now = datetime.now(timezone.utc)
            Affected = self.Repository.DatabaseService.ExecuteNonQuery(Query, (JobId, Sid, Rel, Recursive, Now, Now, WorkerName, Sid, Rel))
            return int(Affected or 0) > 0
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

    # see filescanning.C29
    def _ComputeRealProgress(self) -> float:
        Floor = float(self.ScanProgress) if self.ScanProgress is not None else 0.0
        Needed = self._FilesNeedingProbe or 0
        Probed = self._ProbedFiles or 0
        if Needed <= 0:
            return Floor
        Ratio = min(1.0, max(0.0, Probed / Needed))
        Phase = self._CurrentPhase or ''
        if Phase == 'SizeSurvey':
            return 10.0 + Ratio * 20.0
        if Phase == 'Probing':
            return 90.0 + Ratio * 10.0
        return Floor

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
                        Progress=self._ComputeRealProgress(),
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
            self.ScanResults = FileScanResultModel()

            LocalRootPath = self._ToLocalPath(RootFolderPath)

            self.ScanProgress = 10.0
            RootFolder = self.GetOrCreateRootFolder(RootFolderPath, 0.0)

            if not RootFolder or not RootFolder.Id:
                LoggingService.LogError(f"Failed to create or get root folder for: {RootFolderPath}", 'PerformScan', 'FileScanningBusinessService')
                return {
                    'Success': False,
                    'Message': f'Failed to create root folder record for: {RootFolderPath}',
                    'Error': 'RootFolderCreationFailed'
                }

            self.ScanProgress = 30.0
            self._SetPhase(self.CurrentJobId, 'Walking')
            LocalMediaFiles = self.FileManager.ScanDirectory(LocalRootPath, Recursive)
            self.ScanResults.RootFolderId = RootFolder.Id

            DiskMap: Dict[str, Dict[str, Any]] = {}
            Roots = _GetStorageRoots()
            NowUtc = datetime.now(timezone.utc).replace(tzinfo=None)
            for LocalPath in LocalMediaFiles or []:
                try:
                    CanonicalPath = self._ToCanonicalPath(LocalPath)
                    try:
                        Parsed = Path.FromLegacyString(CanonicalPath, Roots)
                        Sid, Rel = Parsed.StorageRootId, Parsed.RelativePath
                    except PathError:
                        continue
                    if Sid is None or not Rel:
                        continue
                    try:
                        Size = LocalGetSize(LocalPath)
                        Mtime = datetime.fromtimestamp(LocalGetMTime(LocalPath), tz=timezone.utc).replace(tzinfo=None)
                    except OSError:
                        continue
                    FileName = LocalBasename(LocalPath)
                    DiskMap[Rel.lower()] = {
                        'StorageRootId': Sid,
                        'RelativePath': Rel,
                        'FileName': FileName,
                        'FileSize': Size,
                        'FileModificationTime': Mtime,
                    }
                except Exception as WalkEx:
                    LoggingService.LogException(f"Walk entry failed for {LocalPath}", WalkEx, 'PerformScan', 'FileScanningBusinessService')

            self.ScanResults.TotalFilesFound = len(DiskMap)

            DbMap = self.MediaFilesRepository.BatchFetchExistingByRootFolder(RootFolder.Id)

            DiskKeys = set(DiskMap.keys())
            DbKeys = set(DbMap.keys())
            NewKeys = DiskKeys - DbKeys
            DeletedKeys = DbKeys - DiskKeys
            CommonKeys = DiskKeys & DbKeys

            RenamePairs = []
            if NewKeys and DeletedKeys:
                DeletedByKey: Dict[tuple, list] = {}
                for K in DeletedKeys:
                    Dbr = DbMap[K]
                    KeyTuple = (Dbr.get('FileSize'), (Dbr.get('FileName') or '').lower())
                    DeletedByKey.setdefault(KeyTuple, []).append(K)
                for Nk in list(NewKeys):
                    Dsk = DiskMap[Nk]
                    KeyTuple = (Dsk['FileSize'], Dsk['FileName'].lower())
                    Bucket = DeletedByKey.get(KeyTuple)
                    if Bucket:
                        Dk = Bucket.pop(0)
                        RenamePairs.append((Dk, Nk))
                for Dk, Nk in RenamePairs:
                    NewKeys.discard(Nk)
                    DeletedKeys.discard(Dk)

            ChangedRows: List[dict] = []
            for K in CommonKeys:
                Dsk = DiskMap[K]
                Dbr = DbMap[K]
                if Dsk['FileSize'] != Dbr.get('FileSize') or Dsk['FileModificationTime'] != Dbr.get('FileModificationTime'):
                    ChangedRows.append({
                        'Id': Dbr['Id'],
                        'FileSize': Dsk['FileSize'],
                        'FileModificationTime': Dsk['FileModificationTime'],
                    })

            NewInserts = 0
            if NewKeys:
                InsertRows = []
                for K in NewKeys:
                    D = DiskMap[K]
                    InsertRows.append((
                        None,
                        D['StorageRootId'],
                        D['RelativePath'],
                        D['FileName'],
                        round(D['FileSize'] / (1024.0 * 1024.0), 2),
                        D['FileSize'],
                        D['FileModificationTime'],
                        D['FileModificationTime'],
                        NowUtc,
                        False,
                    ))
                NewInserts = self.MediaFilesRepository.BatchInsertMediaFiles(InsertRows)

            Updates = 0
            if ChangedRows:
                UpdateRows = [
                    (
                        C['Id'],
                        round(C['FileSize'] / (1024.0 * 1024.0), 2),
                        C['FileSize'],
                        C['FileModificationTime'],
                        C['FileModificationTime'],
                        NowUtc,
                    )
                    for C in ChangedRows
                ]
                Updates = self.MediaFilesRepository.BatchUpdateChanged(UpdateRows)

            Renames = 0
            if RenamePairs:
                RenameRows = []
                for Dk, Nk in RenamePairs:
                    D = DiskMap[Nk]
                    RenameRows.append((
                        DbMap[Dk]['Id'],
                        D['RelativePath'],
                        D['FileName'],
                        round(D['FileSize'] / (1024.0 * 1024.0), 2),
                        D['FileSize'],
                        D['FileModificationTime'],
                        D['FileModificationTime'],
                        NowUtc,
                    ))
                Renames = self.MediaFilesRepository.BatchRenameMediaFiles(RenameRows)

            Deletes = 0
            if DeletedKeys:
                DeleteIds = [DbMap[K]['Id'] for K in DeletedKeys]
                Deletes = self.MediaFilesRepository.BatchDeleteMediaFiles(DeleteIds)

            self.ScanResults.NewFilesCount = NewInserts
            self.ScanResults.UpdatedFilesCount = Updates + Renames
            self.ScanResults.DeletedFilesCount = Deletes
            self.ScanResults.TotalFilesProcessed = NewInserts + Updates + Renames
            self.ScanResults.TotalFilesSkipped = max(0, len(CommonKeys) - len(ChangedRows))

            self.ScanProgress = 90.0

            self._SetPhase(self.CurrentJobId, 'Completing')
            try:
                self.Repository.UpdateRootFolderPostScan(RootFolder.Id)
            except Exception as AggEx:
                LoggingService.LogException("Post-scan RootFolder aggregate failed", AggEx, 'PerformScan', 'FileScanningBusinessService')

            self.ScanProgress = 100.0
            self.IsScanning = False

            LoggingService.LogInfo(
                f"Scan complete for {RootFolderPath}: disk={len(DiskMap)}, new={NewInserts}, changed={Updates}, renamed={Renames}, deleted={Deletes}, unchanged={self.ScanResults.TotalFilesSkipped}"
            )

            return {
                'Success': True,
                'Message': 'Scan completed successfully',
                'Results': self.ScanResults,
                'RootFolderId': RootFolder.Id,
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
            Ctx = WorkerContext.TryCurrent()
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

            # directive: path-class-perfection | # see path.C27
            _ParsedNew = _PathFS.FromLegacyString(CanonicalPath, _Srs)
            NewFolder = RootFolderModel(
                StorageRootId=_ParsedNew.StorageRootId,
                RelativePath=_ParsedNew.RelativePath,
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
                return self.MediaFilesRepository.GetMediaFilesByRootFolder(RootFolderPath)
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

            # directive: path-class-perfection | # see path.C27
            from Core.Path.Path import Path as _PathAdd
            from Core.Path.PathStorageRoots import GetStorageRoots as _GSRAdd
            _ParsedAdd = _PathAdd.FromLegacyString(RootFolderPath, _GSRAdd())
            NewFolder = RootFolderModel(
                Id=None,
                StorageRootId=_ParsedAdd.StorageRootId,
                RelativePath=_ParsedAdd.RelativePath,
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
            return self.MediaFilesRepository.DeleteMediaFile(MediaFileId)
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

