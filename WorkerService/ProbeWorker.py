# directive: probe-worker-decoupled -- standalone ffprobe worker; decouples probe cadence from scan-cycle-per-RootFolder scoping.
import os
import threading

from Core.Database.DatabaseService import DatabaseService
from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate
from Core.Logging.LoggingService import LoggingService
from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


ACTIVE_JOB_INSERT_SQL = (
    "INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, "
    "Status, StartedAt, Phase, PhaseTransitionedAt) "
    "VALUES ('ProbeService', 'Probe', %s, %s, %s, %s, 'Running', NOW(), 'Probing', NOW()) "
    "RETURNING Id"
)
ACTIVE_JOB_DELETE_SQL = "DELETE FROM ActiveJobs WHERE Id = %s"


class ProbeWorker:

    DEFAULT_BATCH_SIZE = 25
    DEFAULT_POLL_INTERVAL_SEC = 30

    def __init__(self, WorkerName, Service=None, SettingsRepo=None, Db=None):
        self.WorkerName = WorkerName
        self.Service = Service
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
        self._Thread = threading.Thread(target=self._MainLoop, daemon=True, name='ProbeWorker')
        self._Thread.start()
        LoggingService.LogInfo(f"ProbeWorker started for {self.WorkerName}", 'ProbeWorker', 'Start')

    def Stop(self, TimeoutSec=30):
        if not self.IsRunning:
            return
        self.StopEvent.set()
        self.IsRunning = False
        if self._Thread and self._Thread.is_alive():
            self._Thread.join(timeout=TimeoutSec)
        LoggingService.LogInfo(f"ProbeWorker stopped for {self.WorkerName}", 'ProbeWorker', 'Stop')

    def _MainLoop(self):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Bind()
        if self.Service is None:
            self.Service = MediaProbeBusinessService()
        while not self.StopEvent.is_set():
            try:
                self._PollOnce()
            except Exception as Ex:
                LoggingService.LogException("ProbeWorker._PollOnce raised", Ex, 'ProbeWorker', '_MainLoop')
            Interval = self._ResolveIntSetting('ProbePollIntervalSec', self.DEFAULT_POLL_INTERVAL_SEC)
            self.StopEvent.wait(timeout=Interval)

    def _PollOnce(self):
        BatchSize = self._ResolveIntSetting('ProbeBatchSize', self.DEFAULT_BATCH_SIZE)
        MaxFailures = MediaProbeBusinessService.MaxFFprobeFailures
        Batch = self._FetchBatch(BatchSize, MaxFailures)
        for Row in Batch:
            if self.StopEvent.is_set():
                break
            self._ProcessOne(Row)

    def _ResolveIntSetting(self, Key, Default):
        try:
            Val = self.SettingsRepo.GetSystemSetting(Key)
            return int(Val) if Val else Default
        except (TypeError, ValueError):
            return Default

    def _FetchBatch(self, BatchSize, MaxFailures):
        CapFragment, CapParams = BuildClaimPredicate(self.WorkerName, 'ProbeEnabled')
        Sql = (
            "SELECT mf.Id FROM MediaFiles mf "
            "WHERE (mf.Resolution IS NULL OR mf.Codec IS NULL OR mf.AudioCodec IS NULL) "
            "AND COALESCE(mf.FFprobeFailureCount, 0) < %s "
            "AND mf.StorageRootId IS NOT NULL "
            "AND mf.RelativePath IS NOT NULL "
            f"AND {CapFragment} "
            "ORDER BY mf.LastScannedDate DESC NULLS LAST "
            "LIMIT %s "
            "FOR UPDATE OF mf SKIP LOCKED"
        )
        Params = (MaxFailures,) + CapParams + (BatchSize,)
        try:
            return self.Db.ExecuteQuery(Sql, Params)
        except Exception as Ex:
            LoggingService.LogException("ProbeWorker._FetchBatch failed", Ex, 'ProbeWorker', '_FetchBatch')
            return []

    def _CreateActiveJob(self, MediaFileId):
        # directive: probe-worker-decoupled -- record in-flight probe in ActiveJobs so DrainWorker sees us truthfully.
        try:
            self.Db.ExecuteNonQuery(
                ACTIVE_JOB_INSERT_SQL,
                (MediaFileId, os.getpid(), threading.get_ident(), self.WorkerName),
            )
            return self.Db.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException("ProbeWorker._CreateActiveJob failed", Ex, 'ProbeWorker', '_CreateActiveJob')
            return None

    def _DeleteActiveJob(self, ActiveJobId):
        if not ActiveJobId:
            return
        try:
            self.Db.ExecuteNonQuery(ACTIVE_JOB_DELETE_SQL, (ActiveJobId,))
        except Exception as Ex:
            LoggingService.LogException("ProbeWorker._DeleteActiveJob failed", Ex, 'ProbeWorker', '_DeleteActiveJob')

    def _ProcessOne(self, Row):
        MediaFileId = Row.get('id') if hasattr(Row, 'get') else Row['Id']
        ActiveJobId = self._CreateActiveJob(MediaFileId)
        try:
            Result = self.Service.ProbeFile(MediaFileId)
            if not Result or not Result.get('Success', False):
                Msg = (Result or {}).get('ErrorMessage', 'unknown')
                LoggingService.LogWarning(
                    f"ProbeWorker: ProbeFile failed MediaFileId={MediaFileId}: {Msg}",
                    'ProbeWorker', '_ProcessOne',
                )
                return
            self._Reclassify(MediaFileId)
        except Exception as Ex:
            LoggingService.LogException(
                f"ProbeWorker: ProbeFile raised MediaFileId={MediaFileId}",
                Ex, 'ProbeWorker', '_ProcessOne',
            )
        finally:
            self._DeleteActiveJob(ActiveJobId)

    def _Reclassify(self, MediaFileId):
        # directive: probe-worker-decoupled -- probe owns making derived compliance state consistent with the columns it just wrote.
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        if not hasattr(self, '_Qmbs'):
            self._Qmbs = QueueManagementBusinessService()
        self._Qmbs.RecomputeForFiles([MediaFileId])
