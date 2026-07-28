import os
import threading

from Core.Database.DatabaseService import DatabaseService
from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path as CorePath
from Core.Path import Worker as CoreWorker
from Core.Path.LocalPath import LocalExists
from Features.AudioNormalization.Services.LanguageEnrichmentError import LanguageEnrichmentError
from Features.AudioNormalization.Services.LanguageEnrichmentService import LanguageEnrichmentService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


ACTIVE_JOB_INSERT_SQL = (
    "INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, "
    "Status, StartedAt, Phase, PhaseTransitionedAt) "
    "VALUES ('LanguageService', 'Language', %s, %s, %s, %s, 'Running', NOW(), 'Detect', NOW()) "
    "RETURNING Id"
)
ACTIVE_JOB_DELETE_SQL = "DELETE FROM ActiveJobs WHERE Id = %s"


# directive: audio-language-detection
class LanguageWorker:

    DEFAULT_BATCH_SIZE = 50
    DEFAULT_POLL_INTERVAL_SEC = 60

    def __init__(self, WorkerName, Service=None, SettingsRepo=None, Db=None):
        self.WorkerName = WorkerName
        self._ServiceOverride = Service
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
        self._Thread = threading.Thread(target=self._MainLoop, daemon=True, name='LanguageWorker')
        self._Thread.start()
        LoggingService.LogInfo(f"LanguageWorker started for {self.WorkerName}", 'LanguageWorker', 'Start')

    def Stop(self, TimeoutSec=30):
        if not self.IsRunning:
            return
        self.StopEvent.set()
        self.IsRunning = False
        if self._Thread and self._Thread.is_alive():
            self._Thread.join(timeout=TimeoutSec)
        LoggingService.LogInfo(f"LanguageWorker stopped for {self.WorkerName}", 'LanguageWorker', 'Stop')

    def _MainLoop(self):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Bind()
        if self.Service is None:
            self.Service = LanguageEnrichmentService()
            LoggingService.LogInfo(
                f"LanguageWorker backend resolved: {type(self.Service.Backend).__name__}",
                'LanguageWorker', '_MainLoop',
            )
        while not self.StopEvent.is_set():
            try:
                self._PollOnce()
            except Exception as Ex:
                LoggingService.LogException("LanguageWorker._PollOnce raised", Ex, 'LanguageWorker', '_MainLoop')
            Interval = self._ResolveIntSetting('LanguagePollIntervalSec', self.DEFAULT_POLL_INTERVAL_SEC)
            self.StopEvent.wait(timeout=Interval)

    def _PollOnce(self):
        BatchSize = self._ResolveIntSetting('LanguageBatchSize', self.DEFAULT_BATCH_SIZE)
        Batch = self._FetchBatch(BatchSize)
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

    def _FetchBatch(self, BatchSize):
        CapFragment, CapParams = BuildClaimPredicate(self.WorkerName, 'LanguageEnabled')
        Sql = (
            "SELECT mf.Id, mf.StorageRootId, mf.RelativePath, mf.FileName "
            "FROM MediaFiles mf "
            "WHERE (mf.AudioLanguages IS NULL "
            "OR 'und' = ANY(string_to_array(LOWER(mf.AudioLanguages), ','))) "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM MediaFileLanguageDetections d WHERE d.MediaFileId = mf.Id"
            ") "
            "AND mf.StorageRootId IS NOT NULL "
            "AND mf.RelativePath IS NOT NULL "
            f"AND {CapFragment} "
            "ORDER BY mf.LastScannedDate DESC NULLS LAST "
            "LIMIT %s "
            "FOR UPDATE OF mf SKIP LOCKED"
        )
        Params = CapParams + (BatchSize,)
        try:
            return self.Db.ExecuteQuery(Sql, Params)
        except Exception as Ex:
            LoggingService.LogException("LanguageWorker._FetchBatch failed", Ex, 'LanguageWorker', '_FetchBatch')
            return []

    def _ProcessOne(self, Row):
        MediaFileId = Row.get('id') if hasattr(Row, 'get') else Row['Id']
        StorageRootId = Row.get('storagerootid') if hasattr(Row, 'get') else Row['StorageRootId']
        RelativePath = Row.get('relativepath') if hasattr(Row, 'get') else Row['RelativePath']
        try:
            P = CorePath(StorageRootId, RelativePath)
            Wk = CoreWorker.Current()
            LocalFilePath = P.Resolve(Wk)
        except Exception as Ex:
            LoggingService.LogException(
                f"LanguageWorker.Resolve failed for MediaFileId={MediaFileId}",
                Ex, 'LanguageWorker', '_ProcessOne',
            )
            return
        if not LocalExists(LocalFilePath):
            LoggingService.LogWarning(
                f"LanguageWorker: local path missing MediaFileId={MediaFileId} path={LocalFilePath!r}",
                'LanguageWorker', '_ProcessOne',
            )
            return
        ActiveJobId = self._CreateActiveJob(MediaFileId)
        try:
            self.Service.EnrichAndStamp(MediaFileId, LocalFilePath)
        except LanguageEnrichmentError as Ex:
            LoggingService.LogWarning(
                f"LanguageWorker: EnrichAndStamp raised MediaFileId={MediaFileId} reason={Ex.Reason}",
                'LanguageWorker', '_ProcessOne',
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"LanguageWorker: unhandled failure MediaFileId={MediaFileId}",
                Ex, 'LanguageWorker', '_ProcessOne',
            )
        finally:
            if ActiveJobId is not None:
                self._DeleteActiveJob(ActiveJobId)

    def _CreateActiveJob(self, MediaFileId):
        try:
            Rows = self.Db.ExecuteQuery(ACTIVE_JOB_INSERT_SQL, (
                MediaFileId, os.getpid(), threading.get_ident(), self.WorkerName,
            ))
            if Rows:
                Row = Rows[0]
                return int(Row.get('Id') or Row.get('id'))
            return None
        except Exception as Ex:
            LoggingService.LogException(
                f"LanguageWorker._CreateActiveJob failed MediaFileId={MediaFileId}",
                Ex, 'LanguageWorker', '_CreateActiveJob',
            )
            return None

    def _DeleteActiveJob(self, ActiveJobId):
        try:
            self.Db.ExecuteNonQuery(ACTIVE_JOB_DELETE_SQL, (ActiveJobId,))
        except Exception as Ex:
            LoggingService.LogException(
                f"LanguageWorker._DeleteActiveJob failed Id={ActiveJobId}",
                Ex, 'LanguageWorker', '_DeleteActiveJob',
            )
