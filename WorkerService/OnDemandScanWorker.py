# directive: probe-worker-decoupled -- polls OnDemandScanRequests, walks the requested subtree via FileScanningBusinessService, auto-chains OnDemandProbeRequests for the same path on completion.
import threading

from Core.Database.DatabaseService import DatabaseService
from Core.Path import Path as CorePath
from Core.Path import Worker as CoreWorker
from Core.Logging.LoggingService import LoggingService
from Features.OnDemandIngest.OnDemandIngestRepository import OnDemandIngestRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


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

    def _PollOnce(self):
        Repo = OnDemandIngestRepository(self.Db)
        Claim = Repo.ClaimNextPendingScanRequest(self.WorkerName)
        if not Claim:
            return
        RequestId = Claim.get('id') or Claim.get('Id')
        Sid = Claim.get('storagerootid') or Claim.get('StorageRootId')
        Rel = Claim.get('relativepath') or Claim.get('RelativePath') or ''
        LoggingService.LogInfo(
            f"OnDemandScanWorker: claimed RequestId={RequestId} sid={Sid} rel={Rel!r}",
            'OnDemandScanWorker', '_PollOnce',
        )
        try:
            Wk = CoreWorker.Current()
            LocalPath = CorePath(Sid, Rel).Resolve(Wk)
        except Exception as Ex:
            Repo.MarkScanFailed(RequestId, f'Path resolve failed: {Ex}')
            LoggingService.LogException("Path resolve failed", Ex, 'OnDemandScanWorker', '_PollOnce')
            return
        try:
            Discovered = self._ScanSubtree(Sid, Rel, LocalPath)
            Repo.MarkScanComplete(RequestId, Discovered)
            LoggingService.LogInfo(
                f"OnDemandScanWorker: RequestId={RequestId} complete; {Discovered} files discovered",
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

    def _ScanSubtree(self, StorageRootId: int, RelativePath: str, LocalPath: str) -> int:
        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
        Svc = FileScanningBusinessService()
        Result = Svc.PerformScan(LocalPath)
        if isinstance(Result, dict):
            Results = Result.get('Results') or {}
            return int(Results.get('NewFiles', 0) or 0) + int(Results.get('UpdatedFiles', 0) or 0)
        return 0
