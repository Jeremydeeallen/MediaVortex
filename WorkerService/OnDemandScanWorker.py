# directive: probe-worker-decoupled -- polls OnDemandScanRequests, walks the requested subtree via FileScanningBusinessService, auto-chains OnDemandProbeRequests for the same path on completion.
import os
import threading

from Core.Database.DatabaseService import DatabaseService
from Core.Path import Path as CorePath
from Core.Path import Worker as CoreWorker
from Core.Logging.LoggingService import LoggingService
from Features.OnDemandIngest.OnDemandIngestRepository import OnDemandIngestRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


ACTIVE_JOB_INSERT_SQL = (
    "INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, "
    "Status, StartedAt, Phase, PhaseTransitionedAt) "
    "VALUES ('ScanService', 'OnDemandScan', %s, %s, %s, %s, 'Running', NOW(), 'Scanning', NOW()) "
    "RETURNING Id"
)
ACTIVE_JOB_DELETE_SQL = "DELETE FROM ActiveJobs WHERE Id = %s"


class OnDemandScanWorker:

    DEFAULT_POLL_INTERVAL_SEC = 15

    def __init__(self, WorkerName, SettingsRepo=None, Db=None):
        self.WorkerName = WorkerName
        self.SettingsRepo = SettingsRepo or SystemSettingsRepository()
        self.Db = Db or DatabaseService()
        self.IsRunning = False
        self.StopEvent = threading.Event()
        self._Thread = None

    def Start(self):
        if self.IsRunning:
            return
        self.IsRunning = True
        self.StopEvent.clear()
        self._Thread = threading.Thread(target=self._MainLoop, daemon=True, name='OnDemandScanWorker')
        self._Thread.start()
        LoggingService.LogInfo(f"OnDemandScanWorker started for {self.WorkerName}", 'OnDemandScanWorker', 'Start')

    def Stop(self, TimeoutSec=30):
        if not self.IsRunning:
            return
        self.StopEvent.set()
        self.IsRunning = False
        if self._Thread and self._Thread.is_alive():
            self._Thread.join(timeout=TimeoutSec)
        LoggingService.LogInfo(f"OnDemandScanWorker stopped for {self.WorkerName}", 'OnDemandScanWorker', 'Stop')

    def _MainLoop(self):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Bind()
        while not self.StopEvent.is_set():
            try:
                self._PollOnce()
            except Exception as Ex:
                LoggingService.LogException("OnDemandScanWorker._PollOnce raised", Ex, 'OnDemandScanWorker', '_MainLoop')
            self.StopEvent.wait(timeout=self._ResolveIntSetting('OnDemandScanPollIntervalSec', self.DEFAULT_POLL_INTERVAL_SEC))

    def _ResolveIntSetting(self, Key, Default):
        try:
            Val = self.SettingsRepo.GetSystemSetting(Key)
            return int(Val) if Val else Default
        except (TypeError, ValueError):
            return Default

    def _CreateActiveJob(self, RequestId):
        # directive: probe-worker-decoupled -- record in-flight on-demand scan in ActiveJobs so DrainWorker sees us truthfully.
        try:
            self.Db.ExecuteNonQuery(
                ACTIVE_JOB_INSERT_SQL,
                (RequestId, os.getpid(), threading.get_ident(), self.WorkerName),
            )
            return self.Db.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException("OnDemandScanWorker._CreateActiveJob failed", Ex, 'OnDemandScanWorker', '_CreateActiveJob')
            return None

    def _DeleteActiveJob(self, ActiveJobId):
        if not ActiveJobId:
            return
        try:
            self.Db.ExecuteNonQuery("DELETE FROM ActiveJobs WHERE Id = %s", (ActiveJobId,))
        except Exception as Ex:
            LoggingService.LogException("OnDemandScanWorker._DeleteActiveJob failed", Ex, 'OnDemandScanWorker', '_DeleteActiveJob')

    def _PollOnce(self):
        Repo = OnDemandIngestRepository(self.Db)
        Claim = Repo.ClaimNextPendingScanRequest(self.WorkerName)
        if not Claim:
            return
        RequestId = Claim.get('id') or Claim.get('Id')
        Sid = Claim.get('storagerootid') or Claim.get('StorageRootId')
        Rel = Claim.get('relativepath') or Claim.get('RelativePath') or ''
        ActiveJobId = self._CreateActiveJob(RequestId)
        LoggingService.LogInfo(
            f"OnDemandScanWorker: claimed RequestId={RequestId} sid={Sid} rel={Rel!r}",
            'OnDemandScanWorker', '_PollOnce',
        )
        try:
            try:
                CanonicalPath = CorePath(Sid, Rel).CanonicalDisplay()
            except Exception as Ex:
                Repo.MarkScanFailed(RequestId, f'Canonical path build failed: {Ex}')
                LoggingService.LogException("Canonical path build failed", Ex, 'OnDemandScanWorker', '_PollOnce')
                return
            try:
                Discovered = self._ScanSubtree(CanonicalPath)
                Repo.MarkScanComplete(RequestId, Discovered)
                LoggingService.LogInfo(
                    f"OnDemandScanWorker: RequestId={RequestId} complete; {Discovered} files discovered/updated",
                    'OnDemandScanWorker', '_PollOnce',
                )
                if Discovered > 0:
                    ProbeRid = Repo.InsertProbeRequest(Sid, Rel)
                    LoggingService.LogInfo(
                        f"OnDemandScanWorker: auto-chained OnDemandProbe RequestId={ProbeRid} for same path",
                        'OnDemandScanWorker', '_PollOnce',
                    )
            except Exception as Ex:
                Repo.MarkScanFailed(RequestId, str(Ex))
                LoggingService.LogException("Scan failed", Ex, 'OnDemandScanWorker', '_PollOnce')
        finally:
            self._DeleteActiveJob(ActiveJobId)

    def _ScanSubtree(self, CanonicalPath: str) -> int:
        # directive: probe-worker-decoupled -- use StartScanning (not PerformScan directly): it handles job creation, worker context, canonical->local translation, and ScanJobs status updates.
        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
        Svc = FileScanningBusinessService()
        Result = Svc.StartScanning(CanonicalPath, Recursive=True, WorkerName=self.WorkerName)
        if not isinstance(Result, dict) or not Result.get('Success', False):
            Err = (Result or {}).get('Message', 'unknown') if isinstance(Result, dict) else 'invalid result'
            raise RuntimeError(f'StartScanning returned failure: {Err}')
        Results = Result.get('Results') or {}
        if hasattr(Results, 'NewFiles'):
            return int(getattr(Results, 'NewFiles', 0) or 0) + int(getattr(Results, 'UpdatedFiles', 0) or 0)
        if isinstance(Results, dict):
            return int(Results.get('NewFiles', 0) or 0) + int(Results.get('UpdatedFiles', 0) or 0)
        return 0
