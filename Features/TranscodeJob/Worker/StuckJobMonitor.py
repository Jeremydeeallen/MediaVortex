import threading
import time
from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
class StuckJobMonitor:
    """Detects and cleans up stuck transcode jobs; runs a recurring monitoring loop."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def __init__(self, DatabaseManager, WorkerName: str):
        """Stash dependencies needed for stuck-job detection (DB + worker identity)."""
        self.DatabaseManager = DatabaseManager
        self.WorkerName = WorkerName
        self.MonitoringThread = None
        self.MonitoringActive = False

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def DetectAndCleanBeforeStart(self):
        """Run a one-shot detection sweep before WorkerLoopService.Run accepts jobs."""
        try:
            LoggingService.LogInfo("Checking for stuck jobs before starting transcoding",
                                   "StuckJobMonitor", "DetectAndCleanBeforeStart")

            from Services.StuckJobDetectionService import StuckJobDetectionService
            DetectionService = StuckJobDetectionService(self.DatabaseManager)

            Result = DetectionService.DetectAndCleanStuckTranscodeJobs()

            if Result.get("Success", False):
                StuckFound = Result.get("StuckJobsFound", 0)
                JobsCleaned = Result.get("JobsCleaned", 0)
                if StuckFound > 0:
                    LoggingService.LogInfo(f"Pre-start stuck job detection: {StuckFound} stuck jobs found, {JobsCleaned} jobs cleaned",
                                           "StuckJobMonitor", "DetectAndCleanBeforeStart")
                else:
                    LoggingService.LogInfo("Pre-start stuck job detection: No stuck jobs found",
                                           "StuckJobMonitor", "DetectAndCleanBeforeStart")
            else:
                LoggingService.LogWarning(f"Pre-start stuck job detection failed: {Result.get('ErrorMessage', 'Unknown error')}",
                                          "StuckJobMonitor", "DetectAndCleanBeforeStart")

        except Exception as Ex:
            LoggingService.LogException("Error during pre-start stuck job detection", Ex,
                                        "StuckJobMonitor", "DetectAndCleanBeforeStart")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def Start(self):
        """Start the background monitoring loop on a daemon thread."""
        try:
            if self.MonitoringActive:
                LoggingService.LogInfo("Stuck job monitoring already active",
                                       "StuckJobMonitor", "Start")
                return

            self.MonitoringActive = True
            self.MonitoringThread = threading.Thread(
                target=self._MonitoringLoop,
                daemon=True,
                name="StuckJobMonitor"
            )
            self.MonitoringThread.start()

            LoggingService.LogInfo("Started stuck job monitoring thread",
                                   "StuckJobMonitor", "Start")

        except Exception as Ex:
            LoggingService.LogException("Error starting stuck job monitoring", Ex,
                                        "StuckJobMonitor", "Start")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def Stop(self):
        """Signal the monitoring loop to stop on the next tick."""
        try:
            if not self.MonitoringActive:
                return

            self.MonitoringActive = False

            if self.MonitoringThread and self.MonitoringThread.is_alive():
                self.MonitoringThread.join(timeout=5)

            LoggingService.LogInfo("Stopped stuck job monitoring thread",
                                   "StuckJobMonitor", "Stop")

        except Exception as Ex:
            LoggingService.LogException("Error stopping stuck job monitoring", Ex,
                                        "StuckJobMonitor", "Stop")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def _MonitoringLoop(self):
        """Recurring loop body; runs StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs per tick."""
        try:
            LoggingService.LogInfo("Stuck job monitoring loop started",
                                   "StuckJobMonitor", "_MonitoringLoop")

            while self.MonitoringActive:
                try:
                    from Services.StuckJobDetectionService import StuckJobDetectionService
                    DetectionService = StuckJobDetectionService(self.DatabaseManager)

                    Result = DetectionService.DetectAndCleanStuckTranscodeJobs()

                    if Result.get("Success", False):
                        StuckFound = Result.get("StuckJobsFound", 0)
                        JobsCleaned = Result.get("JobsCleaned", 0)

                        if StuckFound > 0:
                            LoggingService.LogInfo(f"Periodic stuck job detection: {StuckFound} stuck jobs found, {JobsCleaned} jobs cleaned",
                                                   "StuckJobMonitor", "_MonitoringLoop")
                        else:
                            LoggingService.LogInfo("Periodic stuck job detection: No stuck jobs found",
                                                   "StuckJobMonitor", "_MonitoringLoop")
                    else:
                        LoggingService.LogWarning(f"Periodic stuck job detection failed: {Result.get('ErrorMessage', 'Unknown error')}",
                                                  "StuckJobMonitor", "_MonitoringLoop")

                except Exception as Ex:
                    LoggingService.LogException("Error in periodic stuck job detection", Ex,
                                                "StuckJobMonitor", "_MonitoringLoop")

                for _ in range(300):
                    if not self.MonitoringActive:
                        break
                    time.sleep(1)

            LoggingService.LogInfo("Stuck job monitoring loop completed",
                                   "StuckJobMonitor", "_MonitoringLoop")

        except Exception as Ex:
            LoggingService.LogException("Error in stuck job monitoring loop", Ex,
                                        "StuckJobMonitor", "_MonitoringLoop")
        finally:
            self.MonitoringActive = False
