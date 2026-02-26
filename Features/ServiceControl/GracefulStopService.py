"""
GracefulStopService
Shared service for graceful shutdown of microservices
Implements MVVM pattern using MVVM architecture
"""

import time
import threading
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService


class GracefulStopService:
    """Shared service for graceful shutdown of microservices."""

    def __init__(self, ServiceName: str, DatabaseManagerInstance, ProcessQueueService):
        """
        Initialize the graceful stop service.

        Args:
            ServiceName: Name of the service (WebService, TranscodeService, QualityTestService)
            DatabaseManagerInstance: DatabaseManager instance
            ProcessQueueService: Queue processing service instance (ProcessTranscodeQueueService or ProcessQualityTestQueueService)
        """
        self.ServiceName = ServiceName
        self.DatabaseManager = DatabaseManagerInstance
        self.ProcessQueue = ProcessQueueService
        LoggingService.LogInfo(f"GracefulStopService initialized for {ServiceName}", "GracefulStopService", "__init__")

    def MonitorGracefulStop(self, ShutdownEvent: threading.Event, UpdateStatusCallback=None) -> Dict[str, Any]:
        """
        Monitor graceful stop progress and complete shutdown when current jobs finish.

        Args:
            ShutdownEvent: Threading event to signal shutdown completion
            UpdateStatusCallback: Optional callback to update service status

        Returns:
            Dict with Success, Message, and stats
        """
        try:
            LoggingService.LogInfo(f"Starting graceful stop monitoring for {self.ServiceName}",
                                 "GracefulStopService", "MonitorGracefulStop")

            # Set StopRequested flag to prevent new jobs
            self.ProcessQueue.StopRequested = True

            # Wait for active jobs to complete (check every 5 seconds)
            max_wait_time = 300  # 5 minutes max wait
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                active_jobs = [j for j in self.ProcessQueue.ActiveJobs if j.is_alive()]
                active_count = len(active_jobs)

                if active_count == 0:
                    break

                LoggingService.LogInfo(f"Waiting for {active_count} active job(s) to complete... ({elapsed_time}s elapsed)",
                                     "GracefulStopService", "MonitorGracefulStop")
                time.sleep(5)
                elapsed_time += 5

            # Check if we timed out
            final_active_count = len([j for j in self.ProcessQueue.ActiveJobs if j.is_alive()])
            if final_active_count > 0:
                LoggingService.LogWarning(f"Graceful stop timeout: {final_active_count} job(s) still active after {max_wait_time}s",
                                        "GracefulStopService", "MonitorGracefulStop")
            else:
                LoggingService.LogInfo(f"All jobs completed for {self.ServiceName}, proceeding with shutdown",
                                     "GracefulStopService", "MonitorGracefulStop")

            # Stop the processing queue
            stop_result = self.ProcessQueue.Stop()
            if not stop_result.get("Success", False):
                LoggingService.LogWarning(f"ProcessQueue.Stop() returned failure: {stop_result.get('ErrorMessage', 'Unknown')}",
                                        "GracefulStopService", "MonitorGracefulStop")

            # Update status to Stopped using callback if provided
            if UpdateStatusCallback:
                UpdateStatusCallback("Stopped", "Stopped", 0, False)
            else:
                # Fallback to direct database update
                self.DatabaseManager.UpdateServiceStatus(self.ServiceName, {
                    'Status': 'Stopped',
                    'ProcessId': 0,
                    'IsProcessing': False,
                    'ActiveJobsCount': 0
                })

            # Trigger shutdown event
            ShutdownEvent.set()

            LoggingService.LogInfo(f"Graceful stop completed for {self.ServiceName}",
                                 "GracefulStopService", "MonitorGracefulStop")

            return {
                "Success": True,
                "Message": "Graceful stop completed",
                "TimedOut": final_active_count > 0,
                "RemainingJobs": final_active_count
            }

        except Exception as e:
            LoggingService.LogException(f"Error in graceful stop monitoring for {self.ServiceName}", e,
                                      "GracefulStopService", "MonitorGracefulStop")
            ShutdownEvent.set()
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
