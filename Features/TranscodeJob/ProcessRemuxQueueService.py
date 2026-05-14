"""
ProcessRemuxQueueService
Owns the remux queue loop and concurrency management.
Claims only ProcessingMode='Remux' jobs from TranscodeQueue and delegates
job execution to ProcessTranscodeQueueService.ProcessRemuxJob.
"""

from typing import Dict, Any, Optional
import threading
import time
import os
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService


class ProcessRemuxQueueService:
    """Processes remux jobs from the TranscodeQueue independently of transcode jobs."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 WorkerName: str = None, WorkerConfig: dict = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()

        import socket
        self.WorkerName = WorkerName or socket.gethostname()
        self.WorkerConfig = WorkerConfig or {}

        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 2
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False

        # Lazily-created executor (ProcessTranscodeQueueService instance for job execution)
        self._Executor = None

    def _GetExecutor(self):
        """Lazily create a ProcessTranscodeQueueService for executing remux jobs."""
        if self._Executor is None:
            from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
            self._Executor = ProcessTranscodeQueueService(
                DatabaseManagerInstance=self.DatabaseManager,
                WorkerName=self.WorkerName,
                WorkerConfig=self.WorkerConfig
            )
        return self._Executor

    def Run(self, MaxConcurrentJobs: int = 2) -> Dict[str, Any]:
        """Start processing the remux queue with specified concurrent jobs."""
        try:
            if self.IsProcessing:
                return {
                    "Success": False,
                    "ErrorMessage": "Remux processing is already in progress"
                }

            if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1:
                return {
                    "Success": False,
                    "ErrorMessage": "MaxConcurrentJobs must be a positive integer"
                }

            self.MaxConcurrentJobs = MaxConcurrentJobs
            self.StopRequested = False
            self.IsProcessing = True

            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()

            LoggingService.LogInfo(f"Started remux queue processing with {MaxConcurrentJobs} concurrent jobs",
                                 "ProcessRemuxQueueService", "Run")

            return {
                "Success": True,
                "Message": f"Started remux processing with {MaxConcurrentJobs} concurrent jobs",
                "MaxConcurrentJobs": MaxConcurrentJobs
            }

        except Exception as e:
            self.IsProcessing = False
            ErrorMsg = f"Exception starting remux processing: {str(e)}"
            LoggingService.LogException(ErrorMsg, e, "ProcessRemuxQueueService", "Run")
            return {
                "Success": False,
                "ErrorMessage": ErrorMsg
            }

    def ProcessQueueLoop(self):
        """Main processing loop that claims and dispatches remux jobs."""
        try:
            LoggingService.LogInfo("Starting remux queue processing loop", "ProcessRemuxQueueService", "ProcessQueueLoop")

            while not self.StopRequested:
                if len(self.ActiveJobs) < self.MaxConcurrentJobs:
                    Job = self._ClaimNextRemuxJob()
                    if Job:
                        JobThread = threading.Thread(
                            target=self._ProcessJob,
                            args=(Job,),
                            daemon=True
                        )
                        JobThread.start()
                        self.ActiveJobs.append(JobThread)
                    else:
                        time.sleep(2)
                else:
                    time.sleep(1)

                # Clean up completed threads
                self.ActiveJobs = [T for T in self.ActiveJobs if T.is_alive()]

            # Wait for active jobs to finish
            for T in self.ActiveJobs:
                if T.is_alive():
                    T.join(timeout=300)

            LoggingService.LogInfo("Remux queue processing loop completed", "ProcessRemuxQueueService", "ProcessQueueLoop")

        except Exception as e:
            LoggingService.LogException("Exception in remux processing loop", e, "ProcessRemuxQueueService", "ProcessQueueLoop")
        finally:
            self.IsProcessing = False

    def _ClaimNextRemuxJob(self):
        """Claim the next pending remux job from the queue."""
        try:
            return self.DatabaseManager.ClaimNextPendingRemuxJob(self.WorkerName)
        except Exception as e:
            LoggingService.LogException("Exception claiming next remux job", e, "ProcessRemuxQueueService", "_ClaimNextRemuxJob")
            return None

    def _ProcessJob(self, Job):
        """Delegate remux job execution to ProcessTranscodeQueueService."""
        try:
            Executor = self._GetExecutor()
            Executor.ProcessRemuxJob(Job)
        except Exception as e:
            LoggingService.LogException(f"Exception processing remux job {Job.Id}", e, "ProcessRemuxQueueService", "_ProcessJob")

    def GetStatus(self) -> Dict[str, Any]:
        """Get current remux processing status."""
        return {
            "Success": True,
            "IsProcessing": self.IsProcessing,
            "MaxConcurrentJobs": self.MaxConcurrentJobs,
            "ActiveJobsCount": len([T for T in self.ActiveJobs if T.is_alive()]),
        }
