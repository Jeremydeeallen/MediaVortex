#!/usr/bin/env python3
"""
Quality Testing ViewModel
Presentation logic layer for quality testing using MVVM architecture
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
from Core.Logging.LoggingService import LoggingService


class QualityTestingViewModel:
    """Quality Testing ViewModel - Presentation logic layer."""

    def __init__(self, DatabaseManagerInstance=None, QualityTestingInstance=None, ThreadingInstance=None):
        """Initialize the ViewModel with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance
        self.QualityTestingBusinessService = QualityTestingBusinessService(DatabaseManagerInstance)
        self.ThreadingService = ThreadingInstance

        # LoggingService.LogInfo("QualityTestingViewModel initialized", "QualityTestingViewModel", "__init__")

    def ProcessQueue(self) -> dict:
        """Process the quality testing queue."""
        try:
            LoggingService.LogDebug("Processing quality testing queue", "QualityTestingViewModel", "ProcessQueue")

            # Delegate to business service
            result = self.QualityTestingBusinessService.ProcessQualityTestQueue()

            LoggingService.LogDebug(f"Queue processing result: {result}", "QualityTestingViewModel", "ProcessQueue")
            return result

        except Exception as e:
            LoggingService.LogException("Error processing queue", e, "QualityTestingViewModel", "ProcessQueue")
            return {"Success": False, "Message": str(e)}

    def ClaimJob(self) -> dict:
        """Atomically claim a pending quality test job."""
        try:
            # Use the new atomic job claiming method
            job = self.DatabaseManager.ClaimQualityTestJob()
            return job

        except Exception as e:
            LoggingService.LogException("Error claiming job", e, "QualityTestingViewModel", "ClaimJob")
            return None

    def ProcessJob(self, job: dict) -> dict:
        """Process a claimed quality test job."""
        try:
            LoggingService.LogInfo(f"Processing claimed job {job['Id']}", "QualityTestingViewModel", "ProcessJob")

            # Delegate to business service to process the specific job
            result = self.QualityTestingBusinessService.ProcessClaimedJob(job)

            LoggingService.LogDebug(f"Job {job['Id']} processing result: {result}", "QualityTestingViewModel", "ProcessJob")
            return result

        except Exception as e:
            LoggingService.LogException(f"Error processing job {job['Id']}", e, "QualityTestingViewModel", "ProcessJob")
            return {"Success": False, "Message": str(e)}

    def GetActiveJobs(self) -> dict:
        """Get list of active quality testing jobs."""
        try:
            # LoggingService.LogInfo("Getting active quality testing jobs", "QualityTestingViewModel", "GetActiveJobs")

            # Delegate to business service
            result = self.QualityTestingBusinessService.GetActiveJobs()

            # LoggingService.LogInfo(f"Active jobs result: {result}", "QualityTestingViewModel", "GetActiveJobs")
            return result

        except Exception as e:
            LoggingService.LogException("Error getting active jobs", e, "QualityTestingViewModel", "GetActiveJobs")
            return {"Success": False, "Message": str(e)}

    def CheckMicroServiceStatus(self) -> bool:
        """Check if microservice is enabled."""
        try:
            # Check if MicroServiceStatus is enabled (assuming it's in ServiceStatus table)
            microservice_status = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT MicroServiceStatus FROM ServiceStatus WHERE ServiceName = %s",
                ('QualityTestingService',)
            )

            if microservice_status and len(microservice_status) > 0:
                return bool(microservice_status[0][0])

            return False

        except Exception as e:
            LoggingService.LogException("Error checking microservice status", e, "QualityTestingViewModel", "CheckMicroServiceStatus")
            return False

    def CheckServiceStatus(self) -> dict:
        """Check if the service should be running."""
        try:
            # Get service status from database
            service_status = self.DatabaseManager.GetServiceStatus('QualityTestingService')

            return service_status

        except Exception as e:
            LoggingService.LogException("Error checking service status", e, "QualityTestingViewModel", "CheckServiceStatus")
            return None

    def StartQualityTest(self, JobId: int) -> dict:
        """Start a quality test for the specified job."""
        try:
            # LoggingService.LogInfo(f"Starting quality test for job {JobId}", "QualityTestingViewModel", "StartQualityTest")

            # Delegate to business service
            result = self.QualityTestingBusinessService.StartQualityTest(JobId)

            # LoggingService.LogInfo(f"Start quality test result: {result}", "QualityTestingViewModel", "StartQualityTest")
            return result

        except Exception as e:
            LoggingService.LogException("Error starting quality test", e, "QualityTestingViewModel", "StartQualityTest")
            return {"Success": False, "Message": str(e)}

    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a specific quality test."""
        try:
            # LoggingService.LogInfo(f"Getting quality test status for job {JobId}", "QualityTestingViewModel", "GetQualityTestStatus")

            # Delegate to business service
            result = self.QualityTestingBusinessService.GetQualityTestStatus(JobId)

            # LoggingService.LogInfo(f"Quality test status result: {result}", "QualityTestingViewModel", "GetQualityTestStatus")
            return result

        except Exception as e:
            LoggingService.LogException("Error getting quality test status", e, "QualityTestingViewModel", "GetQualityTestStatus")
            return {"Success": False, "Message": str(e)}

    def Shutdown(self) -> bool:
        """Graceful shutdown of the ViewModel."""
        try:
            # LoggingService.LogInfo("Shutting down QualityTestingViewModel", "QualityTestingViewModel", "Shutdown")

            # Just log completion - the worker handles the actual shutdown
            # LoggingService.LogInfo("QualityTestingViewModel shutdown completed", "QualityTestingViewModel", "Shutdown")
            return True

        except Exception as e:
            LoggingService.LogException("Error during ViewModel shutdown", e, "QualityTestingViewModel", "Shutdown")
            return False
