import threading
import time
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessorRegistry import JobProcessorRegistry


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C14
class WorkerLoopService:
    """Unified worker loop service; polls Transcode + Remux queues per worker capabilities and dispatches via JobProcessorRegistry. Replaces the dual ProcessTranscodeQueueService / ProcessRemuxQueueService poller pair."""

    # directive: worker-runtime-state | # see workerservice.S8
    def __init__(self, DatabaseManager, JobProcessorRegistryInstance: JobProcessorRegistry, WorkerName: str,
                 TranscodeEnabled: bool, RemuxEnabled: bool, AcceptsInterlaced: bool = True,
                 MaxConcurrentTranscodeJobs: int = 1, MaxConcurrentRemuxJobs: int = 2,
                 StateReporter=None):
        """Inject DB + registry + worker capability + concurrency knobs."""
        self.DatabaseManager = DatabaseManager
        self.JobProcessorRegistry = JobProcessorRegistryInstance
        self.WorkerName = WorkerName
        self.TranscodeEnabled = TranscodeEnabled
        self.RemuxEnabled = RemuxEnabled
        self.AcceptsInterlaced = AcceptsInterlaced
        self.MaxConcurrentTranscodeJobs = MaxConcurrentTranscodeJobs
        self.MaxConcurrentRemuxJobs = MaxConcurrentRemuxJobs
        self.ActiveTranscodeJobs = []
        self.ActiveRemuxJobs = []
        self.IsProcessing = False
        self.StopRequested = False
        self.ProcessingThread = None
        self.StateReporter = StateReporter
        # directive: transcode-flow-canonical
        SlotCount = max(1, MaxConcurrentTranscodeJobs + MaxConcurrentRemuxJobs)
        self.SlotSemaphore = threading.BoundedSemaphore(SlotCount)
        self.SlotCount = SlotCount

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C14
    def Run(self) -> Dict[str, Any]:
        """Start the unified processing loop on a daemon thread."""
        try:
            if self.IsProcessing:
                return {"Success": False, "ErrorMessage": "WorkerLoopService is already running"}
            self.StopRequested = False
            self.IsProcessing = True
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()
            LoggingService.LogInfo(f"WorkerLoopService started (Transcode={self.TranscodeEnabled}, Remux={self.RemuxEnabled})", "WorkerLoopService", "Run")
            return {"Success": True, "Message": "WorkerLoopService running"}
        except Exception as Ex:
            self.IsProcessing = False
            LoggingService.LogException("Failed to start WorkerLoopService", Ex, "WorkerLoopService", "Run")
            return {"Success": False, "ErrorMessage": str(Ex)}

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C14
    def Stop(self) -> Dict[str, Any]:
        """Signal the loop to stop on the next tick; wait for in-flight jobs to drain."""
        try:
            self.StopRequested = True
            LoggingService.LogInfo("WorkerLoopService stop requested", "WorkerLoopService", "Stop")
            return {"Success": True, "Message": "Stop signal sent"}
        except Exception as Ex:
            LoggingService.LogException("Failed to stop WorkerLoopService", Ex, "WorkerLoopService", "Stop")
            return {"Success": False, "ErrorMessage": str(Ex)}

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C14
    def GetStatus(self) -> Dict[str, Any]:
        """Return current loop status + active job counts."""
        return {
            "Success": True,
            "IsProcessing": self.IsProcessing,
            "TranscodeEnabled": self.TranscodeEnabled,
            "RemuxEnabled": self.RemuxEnabled,
            "ActiveTranscodeJobs": len([T for T in self.ActiveTranscodeJobs if T.is_alive()]),
            "ActiveRemuxJobs": len([T for T in self.ActiveRemuxJobs if T.is_alive()]),
        }

    # directive: transcode-worker-unification | # see transcode.ST6
    def ProcessQueueLoop(self):
        """Main loop: polls ClaimNextPendingJob for all enabled modes; dispatches via JobProcessorRegistry."""
        try:
            LoggingService.LogInfo(f"WorkerLoopService.ProcessQueueLoop entering (SlotCount={self.SlotCount})", "WorkerLoopService", "ProcessQueueLoop")
            while not self.StopRequested:
                # directive: transcode-flow-canonical
                Acquired = self.SlotSemaphore.acquire(blocking=False)
                if not Acquired:
                    time.sleep(2)
                    continue
                Job = self._ClaimJob()
                if not Job:
                    self.SlotSemaphore.release()
                    time.sleep(2)
                    continue
                Thread = threading.Thread(target=self._DispatchJobWithSlotRelease, args=(Job,), daemon=True)
                Thread.start()
                self.ActiveTranscodeJobs.append(Thread)
                self.ActiveTranscodeJobs = [T for T in self.ActiveTranscodeJobs if T.is_alive()]
            for T in self.ActiveTranscodeJobs:
                if T.is_alive():
                    T.join(timeout=300)
            LoggingService.LogInfo("WorkerLoopService.ProcessQueueLoop exiting", "WorkerLoopService", "ProcessQueueLoop")
        except Exception as Ex:
            LoggingService.LogException("Exception in WorkerLoopService loop", Ex, "WorkerLoopService", "ProcessQueueLoop")
        finally:
            self.IsProcessing = False

    # directive: transcode-worker-unification | # see transcode.ST6
    def _ClaimJob(self):
        """Claim the next pending job across all enabled modes via ClaimNextPendingJob."""
        try:
            return self.DatabaseManager.ClaimNextPendingJob(self.WorkerName, AcceptsInterlaced=self.AcceptsInterlaced)
        except Exception as Ex:
            LoggingService.LogException("Failed to claim job", Ex, "WorkerLoopService", "_ClaimJob")
            return None

    # directive: transcode-flow-canonical
    def _DispatchJobWithSlotRelease(self, Job):
        """Wrap _DispatchJob to guarantee slot release even on exception (hard concurrency guard)."""
        try:
            self._DispatchJob(Job)
        finally:
            try:
                self.SlotSemaphore.release()
            except ValueError:
                LoggingService.LogWarning("SlotSemaphore over-released; ignoring.", "WorkerLoopService", "_DispatchJobWithSlotRelease")

    # directive: worker-runtime-state | # see workerservice.S8
    def _DispatchJob(self, Job):
        """Look up the JobProcessor for Job.ProcessingMode and run it."""
        Mode = None
        AttemptId = getattr(Job, 'Id', None)
        try:
            Mode = getattr(Job, 'ProcessingMode', None) or 'Transcode'
            if getattr(Job, 'IsTestMode', False):
                Mode = 'TestVariant'
            Processor = self.JobProcessorRegistry.Get(Mode)
            if self.StateReporter is not None:
                self.StateReporter.Transition('Encoding', AttemptId=AttemptId)
            Processor.Process(Job)
        except KeyError as KeyEx:
            LoggingService.LogError(f"No JobProcessor registered for ProcessingMode={Mode!r} (Job.Id={AttemptId})", "WorkerLoopService", "_DispatchJob")
        except Exception as Ex:
            LoggingService.LogException(f"_DispatchJob failed for Job.Id={AttemptId}", Ex, "WorkerLoopService", "_DispatchJob")
        finally:
            if self.StateReporter is not None:
                try:
                    self.StateReporter.Transition('Idle')
                except Exception:
                    pass
