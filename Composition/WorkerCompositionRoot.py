from typing import Optional
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Features.TranscodeJob.Worker.JobProcessorRegistry import JobProcessorRegistry
from Features.TranscodeJob.Worker.TranscodeJobProcessor import TranscodeJobProcessor
from Features.TranscodeJob.Worker.RemuxJobProcessor import RemuxJobProcessor
from Features.TranscodeJob.Worker.SubtitleFixJobProcessor import SubtitleFixJobProcessor
from Features.TranscodeJob.Worker.VariantJobProcessor import VariantJobProcessor
from Features.TranscodeJob.Worker.WorkerLoopService import WorkerLoopService
from Features.TranscodeJob.Worker.StuckJobMonitor import StuckJobMonitor


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C15
class WorkerCompositionRoot:
    """Single composition root for the worker tier; the only class naming concrete dependency types."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C15
    def __init__(self, WorkerName: str, WorkerConfig: Optional[dict] = None):
        """Assemble the entire worker graph: queue service + processors + registry + loop + monitor."""
        self.WorkerName = WorkerName
        self.WorkerConfig = WorkerConfig or {}
        self.DatabaseManager = DatabaseManager()
        Capabilities = self._LoadCapabilities()
        self.QueueService = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager,
            WorkerName=self.WorkerName,
            WorkerConfig=self.WorkerConfig,
        )
        self.JobProcessorRegistry = JobProcessorRegistry({
            'Transcode': TranscodeJobProcessor(self.QueueService),
            'Remux': RemuxJobProcessor(self.QueueService),
            'Quick': RemuxJobProcessor(self.QueueService),
            'AudioFix': RemuxJobProcessor(self.QueueService),
            'SubtitleFix': SubtitleFixJobProcessor(self.QueueService),
            'TestVariant': VariantJobProcessor(self.QueueService),
        })
        self.WorkerLoop = WorkerLoopService(
            DatabaseManager=self.DatabaseManager,
            JobProcessorRegistryInstance=self.JobProcessorRegistry,
            WorkerName=self.WorkerName,
            TranscodeEnabled=bool(Capabilities.get('TranscodeEnabled', False)),
            RemuxEnabled=bool(Capabilities.get('RemuxEnabled', False)),
            AcceptsInterlaced=bool(Capabilities.get('AcceptsInterlaced', True)),
            MaxConcurrentTranscodeJobs=int(Capabilities.get('MaxConcurrentJobs') or 1),
            MaxConcurrentRemuxJobs=2,
        )
        self.StuckJobMonitor = StuckJobMonitor(DatabaseManager=self.DatabaseManager, WorkerName=self.WorkerName)

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C15
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

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C15
    def Run(self):
        """Boot the worker tier: stuck-job sweep, then start the loop."""
        try:
            self.StuckJobMonitor.DetectAndCleanBeforeStart()
        except Exception as Ex:
            LoggingService.LogException("StuckJobMonitor pre-start sweep failed; continuing to Run", Ex, "WorkerCompositionRoot", "Run")
        return self.WorkerLoop.Run()

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C15
    def Stop(self):
        """Signal the loop + monitor to stop."""
        try:
            self.StuckJobMonitor.Stop()
        except Exception:
            pass
        return self.WorkerLoop.Stop()
