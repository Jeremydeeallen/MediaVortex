#!/usr/bin/env python3
"""
ProcessQualityTestQueueService
Orchestrates the complete quality testing queue processing workflow using MVVM architecture
"""

from typing import Dict, Any, Optional
from datetime import datetime
import threading
import time
import os
from Repositories.DatabaseManager import DatabaseManager
from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.QualityTestRepository import QualityTestRepository


class ProcessQualityTestQueueService:
    """Orchestrates the complete quality testing queue processing workflow using MVVM architecture."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 QualityTestingBusinessInstance: QualityTestingBusinessService = None, QualityTestRepositoryInstance: Optional[QualityTestRepository] = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.QualityTestingBusiness = QualityTestingBusinessInstance or QualityTestingBusinessService(self.DatabaseManager)

        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 1
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False

        # Stuck job monitoring
        self.StuckJobMonitoringThread = None
        self.StuckJobMonitoringActive = False
        self.QualityTestRepository = QualityTestRepositoryInstance or QualityTestRepository()

    def Run(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start processing the quality testing queue with specified concurrent jobs."""
        try:
            LoggingService.LogFunctionEntry("Run", "ProcessQualityTestQueueService", MaxConcurrentJobs)

            if self.IsProcessing:
                return {
                    "Success": False,
                    "ErrorMessage": "Quality testing is already in progress"
                }

            # Validate parameters
            if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1:
                return {
                    "Success": False,
                    "ErrorMessage": "MaxConcurrentJobs must be a positive integer"
                }

            self.MaxConcurrentJobs = MaxConcurrentJobs
            self.StopRequested = False
            self.IsProcessing = True

            # Clean up any stuck jobs before starting
            self.DetectAndCleanStuckJobsBeforeStart()

            # Start processing in background thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()

            # Start stuck job monitoring thread
            self.StartStuckJobMonitoring()

            LoggingService.LogInfo(f"Started quality testing queue processing with {MaxConcurrentJobs} concurrent jobs",
                                 "ProcessQualityTestQueueService", "Run")

            return {
                "Success": True,
                "Message": f"Started quality testing with {MaxConcurrentJobs} concurrent jobs",
                "MaxConcurrentJobs": MaxConcurrentJobs
            }

        except Exception as e:
            self.IsProcessing = False
            errorMsg = f"Exception starting quality testing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessQualityTestQueueService", "Run")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }

    def Stop(self) -> Dict[str, Any]:
        """Stop processing the quality testing queue."""
        try:
            LoggingService.LogFunctionEntry("Stop", "ProcessQualityTestQueueService")

            if not self.IsProcessing:
                return {
                    "Success": True,
                    "Message": "Quality testing is not currently running"
                }

            self.StopRequested = True

            # Wait for processing to stop
            if self.ProcessingThread and self.ProcessingThread.is_alive():
                self.ProcessingThread.join(timeout=10)

            # Stop stuck job monitoring
            self.StopStuckJobMonitoring()

            self.IsProcessing = False
            self.ActiveJobs = []

            LoggingService.LogInfo("Quality testing queue processing stopped",
                                 "ProcessQualityTestQueueService", "Stop")

            return {
                "Success": True,
                "Message": "Quality testing stopped successfully"
            }

        except Exception as e:
            errorMsg = f"Exception stopping quality testing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessQualityTestQueueService", "Stop")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }

    def ProcessQueueLoop(self):
        """Main processing loop that continuously checks for quality testing jobs."""
        try:
            LoggingService.LogInfo("Quality testing queue processing loop started",
                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")

            while not self.StopRequested:
                # Single control plane: this loop runs iff the capability poller
                # (WorkerService._CapabilityPollingLoop) deems Workers.QualityTestEnabled
                # is True for our worker. The legacy ServiceStatus.QualityTestService
                # gate that lived here was a fossil from the retired multi-process
                # architecture and is intentionally NOT read. See
                # Features/ServiceControl/capability-control-plane.feature.md.
                try:
                    # Check if we can process more jobs (concurrency limit)
                    if len(self.ActiveJobs) < self.MaxConcurrentJobs:
                        # Try to claim a job from the queue
                        job = self.ClaimNextJob()

                        if job:
                            # Process the job in a separate thread
                            job_thread = threading.Thread(
                                target=self.ProcessJob,
                                args=(job,),
                                daemon=True
                            )
                            job_thread.start()
                            self.ActiveJobs.append(job_thread)

                            LoggingService.LogInfo(f"Started processing quality test job {job['Id']}",
                                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")
                        else:
                            # No jobs available, wait a bit
                            time.sleep(2)
                    else:
                        # At concurrency limit, wait a bit
                        time.sleep(1)

                    # Clean up completed threads
                    self.ActiveJobs = [thread for thread in self.ActiveJobs if thread.is_alive()]

                except Exception as e:
                    LoggingService.LogException("Error in quality testing queue processing loop", e,
                                             "ProcessQualityTestQueueService", "ProcessQueueLoop")
                    time.sleep(5)  # Wait before retrying

            LoggingService.LogInfo("Quality testing queue processing loop stopped",
                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")

        except Exception as e:
            LoggingService.LogException("Fatal error in quality testing queue processing loop", e,
                                     "ProcessQualityTestQueueService", "ProcessQueueLoop")
            self.IsProcessing = False

    def ClaimNextJob(self) -> Optional[Dict[str, Any]]:
        """Claim the next available quality testing job from the queue.

        Worker name is sourced from WorkerContext (the canonical singleton);
        the DB authority check inside ClaimQualityTestJob refuses the claim
        when this worker is Paused or has QualityTestEnabled=FALSE. No local
        capability check needed here -- the DB is the gate.
        """
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            WorkerName = Ctx.WorkerName if Ctx else None
            if not WorkerName:
                LoggingService.LogWarning(
                    "ClaimNextJob: no WorkerContext.WorkerName registered; refusing claim",
                    "ProcessQualityTestQueueService", "ClaimNextJob",
                )
                return None

            job = self.QualityTestRepository.ClaimQualityTestJob(WorkerName)

            if job:
                LoggingService.LogInfo(f"Claimed quality test job {job['Id']}",
                                     "ProcessQualityTestQueueService", "ClaimNextJob")
                return job
            else:
                # No jobs available or all jobs already claimed
                return None

        except Exception as e:
            LoggingService.LogException("Error claiming next quality test job", e,
                                     "ProcessQualityTestQueueService", "ClaimNextJob")
            return None

    def ProcessJob(self, job: Dict[str, Any]):
        """Process a single quality testing job."""
        try:
            LoggingService.LogInfo(f"Processing quality test job {job['Id']}",
                                 "ProcessQualityTestQueueService", "ProcessJob")

            # Use the business service to process the job
            result = self.QualityTestingBusiness.ProcessClaimedJob(job)

            if result.get('Success', False):
                LoggingService.LogInfo(f"Successfully processed quality test job {job['Id']}",
                                     "ProcessQualityTestQueueService", "ProcessJob")
            else:
                LoggingService.LogError(f"Failed to process quality test job {job['Id']}: {result.get('Message', 'Unknown error')}",
                                      "ProcessQualityTestQueueService", "ProcessJob")

        except Exception as e:
            LoggingService.LogException(f"Exception processing quality test job {job['Id']}", e,
                                     "ProcessQualityTestQueueService", "ProcessJob")
        finally:
            # Job processing is complete (success or failure)
            LoggingService.LogInfo(f"Quality test job {job['Id']} processing completed",
                                 "ProcessQualityTestQueueService", "ProcessJob")

    def GetStatus(self) -> Dict[str, Any]:
        """Get current processing status."""
        try:
            return {
                "Success": True,
                "IsProcessing": self.IsProcessing,
                "MaxConcurrentJobs": self.MaxConcurrentJobs,
                "ActiveJobsCount": len(self.ActiveJobs),
                "StopRequested": self.StopRequested
            }
        except Exception as e:
            LoggingService.LogException("Error getting quality testing status", e,
                                     "ProcessQualityTestQueueService", "GetStatus")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }

    def IsStopRequested(self) -> bool:
        """Check if stop was requested."""
        return self.StopRequested

    def DetectAndCleanStuckJobsBeforeStart(self):
        """Detect and clean up stuck jobs before starting quality testing."""
        try:
            LoggingService.LogInfo("Checking for stuck quality test jobs before starting",
                                 "ProcessQualityTestQueueService", "DetectAndCleanStuckJobsBeforeStart")

            from Services.StuckJobDetectionService import StuckJobDetectionService
            detection_service = StuckJobDetectionService(self.DatabaseManager)

            result = detection_service.DetectAndCleanStuckQualityTestJobs()

            if result.get("Success", False):
                stuck_found = result.get("StuckJobsFound", 0)
                jobs_cleaned = result.get("JobsCleaned", 0)
                if stuck_found > 0:
                    LoggingService.LogInfo(f"Pre-start stuck quality test job detection: {stuck_found} stuck jobs found, {jobs_cleaned} jobs cleaned",
                                         "ProcessQualityTestQueueService", "DetectAndCleanStuckJobsBeforeStart")
                else:
                    LoggingService.LogInfo("Pre-start stuck quality test job detection: No stuck jobs found",
                                         "ProcessQualityTestQueueService", "DetectAndCleanStuckJobsBeforeStart")
            else:
                LoggingService.LogWarning(f"Pre-start stuck quality test job detection failed: {result.get('ErrorMessage', 'Unknown error')}",
                                        "ProcessQualityTestQueueService", "DetectAndCleanStuckJobsBeforeStart")

        except Exception as e:
            LoggingService.LogException("Error during pre-start stuck quality test job detection", e,
                                      "ProcessQualityTestQueueService", "DetectAndCleanStuckJobsBeforeStart")

    def StartStuckJobMonitoring(self):
        """Start background monitoring for stuck quality test jobs."""
        try:
            if self.StuckJobMonitoringActive:
                LoggingService.LogInfo("Stuck quality test job monitoring already active",
                                     "ProcessQualityTestQueueService", "StartStuckJobMonitoring")
                return

            self.StuckJobMonitoringActive = True
            self.StuckJobMonitoringThread = threading.Thread(
                target=self.StuckJobMonitoringLoop,
                daemon=True,
                name="StuckQualityTestJobMonitor"
            )
            self.StuckJobMonitoringThread.start()

            LoggingService.LogInfo("Started stuck quality test job monitoring thread",
                                 "ProcessQualityTestQueueService", "StartStuckJobMonitoring")

        except Exception as e:
            LoggingService.LogException("Error starting stuck quality test job monitoring", e,
                                      "ProcessQualityTestQueueService", "StartStuckJobMonitoring")

    def StopStuckJobMonitoring(self):
        """Stop background monitoring for stuck quality test jobs."""
        try:
            if not self.StuckJobMonitoringActive:
                return

            self.StuckJobMonitoringActive = False

            if self.StuckJobMonitoringThread and self.StuckJobMonitoringThread.is_alive():
                self.StuckJobMonitoringThread.join(timeout=5)

            LoggingService.LogInfo("Stopped stuck quality test job monitoring thread",
                                 "ProcessQualityTestQueueService", "StopStuckJobMonitoring")

        except Exception as e:
            LoggingService.LogException("Error stopping stuck quality test job monitoring", e,
                                      "ProcessQualityTestQueueService", "StopStuckJobMonitoring")

    def StuckJobMonitoringLoop(self):
        """Background monitoring loop for stuck quality test jobs - runs every 5 minutes."""
        try:
            LoggingService.LogInfo("Stuck quality test job monitoring loop started",
                                 "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")

            while self.StuckJobMonitoringActive and not self.StopRequested:
                try:
                    # Check for stuck quality test jobs
                    from Services.StuckJobDetectionService import StuckJobDetectionService
                    detection_service = StuckJobDetectionService(self.DatabaseManager)

                    result = detection_service.DetectAndCleanStuckQualityTestJobs()

                    if result.get("Success", False):
                        stuck_found = result.get("StuckJobsFound", 0)
                        jobs_cleaned = result.get("JobsCleaned", 0)

                        if stuck_found > 0:
                            LoggingService.LogInfo(f"Periodic stuck quality test job detection: {stuck_found} stuck jobs found, {jobs_cleaned} jobs cleaned",
                                                 "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")
                        else:
                            # Log periodic check even when no stuck jobs found (for audit trail)
                            LoggingService.LogInfo("Periodic stuck quality test job detection: No stuck jobs found",
                                                 "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")
                    else:
                        LoggingService.LogWarning(f"Periodic stuck quality test job detection failed: {result.get('ErrorMessage', 'Unknown error')}",
                                                "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")

                except Exception as e:
                    LoggingService.LogException("Error in periodic stuck quality test job detection", e,
                                              "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")

                # Wait 5 minutes before next check
                for _ in range(300):  # 5 minutes = 300 seconds
                    if not self.StuckJobMonitoringActive or self.StopRequested:
                        break
                    time.sleep(1)

            LoggingService.LogInfo("Stuck quality test job monitoring loop completed",
                                 "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")

        except Exception as e:
            LoggingService.LogException("Error in stuck quality test job monitoring loop", e,
                                      "ProcessQualityTestQueueService", "StuckJobMonitoringLoop")
        finally:
            self.StuckJobMonitoringActive = False
