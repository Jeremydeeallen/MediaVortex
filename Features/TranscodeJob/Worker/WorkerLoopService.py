import threading
import time
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessorRegistry import JobProcessorRegistry


# directive: transcode-flow-canonical
class WorkerLoopService:
    """Single per-worker poll loop. One slot semaphore capped at Workers.MaxConcurrentJobs. Handles every ProcessingMode the worker is capable of via unified ClaimNextPendingJob."""

    # directive: transcode-flow-canonical
    def __init__(self, DatabaseManager, JobProcessorRegistryInstance: JobProcessorRegistry, WorkerName: str,
                 TranscodeEnabled: bool, RemuxEnabled: bool, AcceptsInterlaced: bool = True,
                 MaxConcurrentJobs: int = 1,
                 StateReporter=None):
        """Inject DB + registry + worker capability flags + single MaxConcurrentJobs cap."""
        self.DatabaseManager = DatabaseManager
        self.JobProcessorRegistry = JobProcessorRegistryInstance
        self.WorkerName = WorkerName
        self.TranscodeEnabled = TranscodeEnabled
        self.RemuxEnabled = RemuxEnabled
        self.AcceptsInterlaced = AcceptsInterlaced
        self.MaxConcurrentJobs = max(1, int(MaxConcurrentJobs))
        self.ActiveJobs = []
        self.IsProcessing = False
        self.StopRequested = False
        self.ProcessingThread = None
        self.StateReporter = StateReporter
        self.SlotSemaphore = threading.BoundedSemaphore(self.MaxConcurrentJobs)

    # directive: transcode-flow-canonical
    def Run(self) -> Dict[str, Any]:
        try:
            if self.IsProcessing:
                return {"Success": False, "ErrorMessage": "WorkerLoopService is already running"}
            self.StopRequested = False
            self.IsProcessing = True
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()
            LoggingService.LogInfo(f"WorkerLoopService started (MaxConcurrentJobs={self.MaxConcurrentJobs}, Transcode={self.TranscodeEnabled}, Remux={self.RemuxEnabled})", "WorkerLoopService", "Run")
            return {"Success": True, "Message": "WorkerLoopService running"}
        except Exception as Ex:
            self.IsProcessing = False
            LoggingService.LogException("Failed to start WorkerLoopService", Ex, "WorkerLoopService", "Run")
            return {"Success": False, "ErrorMessage": str(Ex)}

    # directive: transcode-flow-canonical
    def Stop(self) -> Dict[str, Any]:
        try:
            self.StopRequested = True
            LoggingService.LogInfo("WorkerLoopService stop requested", "WorkerLoopService", "Stop")
            return {"Success": True, "Message": "Stop signal sent"}
        except Exception as Ex:
            LoggingService.LogException("Failed to stop WorkerLoopService", Ex, "WorkerLoopService", "Stop")
            return {"Success": False, "ErrorMessage": str(Ex)}

    # directive: transcode-flow-canonical
    def GetStatus(self) -> Dict[str, Any]:
        return {
            "Success": True,
            "IsProcessing": self.IsProcessing,
            "TranscodeEnabled": self.TranscodeEnabled,
            "RemuxEnabled": self.RemuxEnabled,
            "MaxConcurrentJobs": self.MaxConcurrentJobs,
            "ActiveJobs": len([T for T in self.ActiveJobs if T.is_alive()]),
        }

    # directive: transcode-flow-canonical
    def ProcessQueueLoop(self):
        try:
            LoggingService.LogInfo(f"WorkerLoopService.ProcessQueueLoop entering (MaxConcurrentJobs={self.MaxConcurrentJobs})", "WorkerLoopService", "ProcessQueueLoop")
            while not self.StopRequested:
                if not self.SlotSemaphore.acquire(blocking=False):
                    time.sleep(2)
                    continue
                Job = self._ClaimJob()
                if not Job:
                    self.SlotSemaphore.release()
                    time.sleep(2)
                    continue
                Thread = threading.Thread(target=self._DispatchJobWithSlotRelease, args=(Job,), daemon=True)
                Thread.start()
                self.ActiveJobs.append(Thread)
                self.ActiveJobs = [T for T in self.ActiveJobs if T.is_alive()]
            for T in self.ActiveJobs:
                if T.is_alive():
                    T.join(timeout=300)
            LoggingService.LogInfo("WorkerLoopService.ProcessQueueLoop exiting", "WorkerLoopService", "ProcessQueueLoop")
        except Exception as Ex:
            LoggingService.LogException("Exception in WorkerLoopService loop", Ex, "WorkerLoopService", "ProcessQueueLoop")
        finally:
            self.IsProcessing = False

    # directive: transcode-flow-canonical
    def _ClaimJob(self):
        try:
            return self.DatabaseManager.ClaimNextPendingJob(self.WorkerName, AcceptsInterlaced=self.AcceptsInterlaced)
        except Exception as Ex:
            LoggingService.LogException("Failed to claim job", Ex, "WorkerLoopService", "_ClaimJob")
            return None

    # directive: transcode-flow-canonical
    def _DispatchJobWithSlotRelease(self, Job):
        try:
            self._DispatchJob(Job)
        finally:
            try:
                self.SlotSemaphore.release()
            except ValueError:
                LoggingService.LogWarning("SlotSemaphore over-released; ignoring", "WorkerLoopService", "_DispatchJobWithSlotRelease")

    # directive: transcode-flow-canonical
    def _DispatchJob(self, Job):
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
