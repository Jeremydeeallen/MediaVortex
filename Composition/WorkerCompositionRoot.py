from typing import Optional
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobProcessorRegistry import JobProcessorRegistry
from Features.TranscodeJob.Worker.VariantJobProcessor import VariantJobProcessor
from Features.TranscodeJob.Worker.Strategies.JobProcessorRegistry import JobProcessorRegistry as StrategyRegistry
from Features.TranscodeJob.Worker.Strategies.TranscodeJobStrategy import TranscodeJobStrategy
from Features.TranscodeJob.Worker.Strategies.RemuxJobStrategy import RemuxJobStrategy
from Features.TranscodeJob.Worker.Strategies.AudioFixJobStrategy import AudioFixJobStrategy
from Features.TranscodeJob.Worker.Strategies.QuickJobStrategy import QuickJobStrategy
from Features.TranscodeJob.Worker.Strategies.SubtitleFixJobStrategy import SubtitleFixJobStrategy
from Features.TranscodeJob.Worker.WorkerLoopService import WorkerLoopService
from Features.TranscodeJob.Worker.StuckJobMonitor import StuckJobMonitor


# directive: transcode-worker-unification | # see worker-loop.C4
class WorkerCompositionRoot:
    """Single composition root for the worker tier; the only class naming concrete dependency types."""

    # directive: transcode-worker-unification | # see worker-loop.C4
    def __init__(self, WorkerName: str, WorkerConfig: Optional[dict] = None):
        """Assemble the entire worker graph: queue service + strategy registry + unified processor + loop + monitor."""
        self.WorkerName = WorkerName
        self.WorkerConfig = WorkerConfig or {}
        self.DatabaseManager = DatabaseManager()
        Capabilities = self._LoadCapabilities()
        self.QueueService = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager,
            WorkerName=self.WorkerName,
            WorkerConfig=self.WorkerConfig,
        )
        # directive: transcode-worker-unification | # see worker-loop.C4
        StratReg = StrategyRegistry(Db=self.DatabaseManager.DatabaseService)
        StratReg.Register('Transcode', TranscodeJobStrategy)
        StratReg.Register('Remux', RemuxJobStrategy)
        StratReg.Register('AudioFix', AudioFixJobStrategy)
        StratReg.Register('Quick', QuickJobStrategy)
        StratReg.Register('SubtitleFix', SubtitleFixJobStrategy)
        self.JobProcessorRegistry = JobProcessorRegistry({
            'Transcode': JobProcessor(QueueService=self.QueueService, Registry=StratReg),
            'Remux': JobProcessor(QueueService=self.QueueService, Registry=StratReg),
            'Quick': JobProcessor(QueueService=self.QueueService, Registry=StratReg),
            'AudioFix': JobProcessor(QueueService=self.QueueService, Registry=StratReg),
            'SubtitleFix': JobProcessor(QueueService=self.QueueService, Registry=StratReg),
            'TestVariant': VariantJobProcessor(self.QueueService),
        })
        self.WorkerLoop = WorkerLoopService(
            DatabaseManager=self.DatabaseManager,
            JobProcessorRegistryInstance=self.JobProcessorRegistry,
            WorkerName=self.WorkerName,
            TranscodeEnabled=bool(Capabilities.get('TranscodeEnabled', False)),
            RemuxEnabled=bool(Capabilities.get('RemuxEnabled', False)),
            AcceptsInterlaced=bool(Capabilities.get('AcceptsInterlaced', True)),
            MaxConcurrentJobs=int(Capabilities.get('MaxConcurrentJobs') or 1),
        )
        self.StuckJobMonitor = StuckJobMonitor(DatabaseManager=self.DatabaseManager, WorkerName=self.WorkerName)

    # directive: transcode-worker-unification | # see worker-loop.C4
    def _LoadCapabilities(self) -> dict:
        """Read the Workers row for this WorkerName; returns capability flags + concurrency knobs."""
        try:
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT TranscodeEnabled, RemuxEnabled, AcceptsInterlaced, MaxConcurrentJobs FROM Workers WHERE WorkerName = %s",
                (self.WorkerName,),
            )
            if Rows:
                return dict(Rows[0])
            return {}
        except Exception as Ex:
            LoggingService.LogException(f"_LoadCapabilities failed for {self.WorkerName}; defaulting to no capabilities", Ex, "WorkerCompositionRoot", "_LoadCapabilities")
            return {}

    # directive: transcode-worker-unification | # see worker-loop.C4
    def Run(self):
        """Boot the worker tier: stuck-job sweep, then start the loop."""
        try:
            self.StuckJobMonitor.DetectAndCleanBeforeStart()
        except Exception as Ex:
            LoggingService.LogException("StuckJobMonitor pre-start sweep failed; continuing to Run", Ex, "WorkerCompositionRoot", "Run")
        return self.WorkerLoop.Run()

    # directive: transcode-worker-unification | # see worker-loop.C4
    def Stop(self):
        """Signal the loop + monitor to stop."""
        try:
            self.StuckJobMonitor.Stop()
        except Exception:
            pass
        return self.WorkerLoop.Stop()
