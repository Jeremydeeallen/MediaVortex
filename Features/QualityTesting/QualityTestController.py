"""
QualityTestController - Simple controller for quality testing operations
Implements MVVM pattern using MVVM architecture
"""

import os
import json
from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from Services.QualityTestQueueService import QualityTestQueueService

QualityTestBlueprint = Blueprint('QualityTest', __name__)

class QualityTestController:
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.LoggingService = LoggingService()
        self.QualityTestQueueService = QualityTestQueueService(self.DatabaseManager)

    def StartQualityTest(self, JobId: int) -> dict:
        """Trigger quality test processing - the job is already in the queue, just verify it exists."""
        try:
            self.LoggingService.LogInfo(f"Triggering quality test for job {JobId}")

            # Verify the job exists in the queue
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)

            if JobDetails:
                return {"Success": True, "Message": "Quality test job exists in queue and will be processed"}
            else:
                return {"Success": False, "Message": "Quality test job not found in queue"}

        except Exception as e:
            self.LoggingService.LogError(f"Error triggering quality test: {str(e)}")
            return {"Success": False, "Message": str(e)}


    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a quality test job by checking both queue and results tables."""
        try:
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}

            # Determine status from queue dates
            if JobDetails.get("DateCompleted"):
                Status = "Completed"
            elif JobDetails.get("DateStarted"):
                Status = "Running"
            else:
                Status = "Pending"

            # Get VMAF score from QualityTestResults if available
            TranscodeAttemptId = JobDetails.get("TranscodeAttemptId")
            VMAFScore = None
            if TranscodeAttemptId:
                query = "SELECT VMAFScore FROM QualityTestResults WHERE TranscodeAttemptId = %s ORDER BY DateTested DESC LIMIT 1"
                results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
                if results:
                    VMAFScore = results[0].get("VMAFScore")

            return {"Success": True, "Status": Status, "VMAFScore": VMAFScore, "JobDetails": JobDetails}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def GetQualityTestQueue(self) -> dict:
        """Get all quality test jobs in queue"""
        try:
            Jobs = self.DatabaseManager.GetQualityTestQueue()
            return {"Success": True, "Jobs": Jobs}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def GetQualityTestServiceStatus(self) -> dict:
        """Get overall quality test service status"""
        try:
            # Check if there are any active quality test jobs
            ActiveJobs = self.DatabaseManager.GetActiveJobsByService("QualityTest")
            IsRunning = len(ActiveJobs) > 0

            return {"Success": True, "IsRunning": IsRunning, "ActiveJobs": len(ActiveJobs)}
        except Exception as e:
            return {"Success": False, "Message": str(e)}


    def LogError(self, ErrorMessage: str, ErrorContext: str, RequestUrl: str) -> dict:
        """Log an error to the database"""
        try:
            self.LoggingService.LogError(f"Quality Test Error - Context: {ErrorContext}, URL: {RequestUrl}, Message: {ErrorMessage}")
            return {"Success": True, "Message": "Error logged successfully"}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def RetryQualityTest(self, JobId: int) -> dict:
        """Retry a failed quality test job by deleting old results and re-queuing."""
        try:
            self.LoggingService.LogInfo(f"Retrying quality test for job {JobId}")

            # Get job details from queue
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}

            TranscodeAttemptId = JobDetails.get("TranscodeAttemptId")
            if not TranscodeAttemptId:
                return {"Success": False, "Message": "Job has no TranscodeAttemptId"}

            # Delete existing quality test records and re-queue
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}

            # Re-add to queue
            NewJobId = self.QualityTestQueueService.AddToQualityTestQueue(TranscodeAttemptId)
            if NewJobId:
                return {"Success": True, "Message": "Job re-queued for retry", "NewJobId": NewJobId}
            else:
                return {"Success": False, "Message": "Failed to re-queue job for retry"}

        except Exception as e:
            self.LoggingService.LogError(f"Error retrying quality test: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def GetQualityTestHistory(self, Page: int = 1, Limit: int = 10) -> dict:
        """Get recent quality test results from QualityTestResults table with pagination"""
        try:
            # Calculate offset for pagination
            Offset = (Page - 1) * Limit

            # Get results with pagination
            Results = self.DatabaseManager.GetQualityTestResults(Limit, Offset)

            # Get total count for pagination info
            TotalCount = self.DatabaseManager.GetQualityTestResultsCount()

            # Calculate pagination info
            TotalPages = (TotalCount + Limit - 1) // Limit  # Ceiling division
            HasNextPage = Page < TotalPages
            HasPreviousPage = Page > 1

            return {
                "Success": True,
                "QualityTestingResults": Results,
                "Pagination": {
                    "CurrentPage": Page,
                    "PageSize": Limit,
                    "TotalCount": TotalCount,
                    "TotalPages": TotalPages,
                    "HasNextPage": HasNextPage,
                    "HasPreviousPage": HasPreviousPage
                }
            }
        except Exception as e:
            self.LoggingService.LogError(f"Error getting quality test history: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def GetQualityTestProgress(self) -> dict:
        """Get running quality test progress from QualityTestProgress table"""
        try:
            Progress = self.DatabaseManager.GetRunningQualityTestProgress()
            if Progress:
                return {
                    "Success": True,
                    "IsRunning": True,
                    "CurrentJob": Progress,
                    "Progress": Progress
                }
            else:
                return {"Success": True, "IsRunning": False, "CurrentJob": None}
        except Exception as e:
            self.LoggingService.LogError(f"Error getting quality test progress: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def AddToQueue(self, TranscodeAttemptId: int) -> dict:
        """Add a transcode attempt to the quality test queue."""
        try:
            self.LoggingService.LogInfo(f"Adding transcode attempt {TranscodeAttemptId} to quality test queue", "QualityTestController", "AddToQueue")

            # Delete existing quality test records for this attempt (allows re-queueing)
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}

            # Use QualityTestQueueService to add to queue (handles all validation and file path resolution)
            JobId = self.QualityTestQueueService.AddToQualityTestQueue(TranscodeAttemptId)

            if JobId:
                self.LoggingService.LogInfo(f"Successfully added quality test job {JobId} for transcode attempt {TranscodeAttemptId}",
                                          "QualityTestController", "AddToQueue")
                return {"Success": True, "Message": "Added to quality test queue successfully", "JobId": JobId}
            else:
                return {"Success": False, "Message": "Failed to create quality test queue entry"}

        except Exception as e:
            ErrorMsg = f"Exception adding transcode attempt {TranscodeAttemptId} to queue: {str(e)}"
            self.LoggingService.LogException(ErrorMsg, e, "QualityTestController", "AddToQueue")
            return {"Success": False, "Message": ErrorMsg}

# Flask routes
@QualityTestBlueprint.route('/QualityTest/Start', methods=['POST'])
def StartQualityTest():
    try:
        LoggingService.LogFunctionEntry("StartQualityTest", "QualityTestController")

        Controller = QualityTestController()
        Data = request.get_json()

        # Individual job start request
        JobId = Data.get('JobId') if Data else None

        if not JobId:
            return jsonify({"Success": False, "Message": "JobId required"}), 400

        Result = Controller.StartQualityTest(JobId)

        LoggingService.LogInfo(f"StartQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "StartQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in StartQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "StartQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to start quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/QualityTest/Status/<int:JobId>', methods=['GET'])
def GetQualityTestStatus(JobId):
    Controller = QualityTestController()
    Result = Controller.GetQualityTestStatus(JobId)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/Status', methods=['GET'])
def GetQualityTestServiceStatus():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestServiceStatus()
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/Queue', methods=['GET'])
def GetQualityTestQueue():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestQueue()
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Stop', methods=['POST'])
def StopQualityTestService():
    try:
        LoggingService.LogFunctionEntry("StopQualityTestService", "QualityTestController")

        Controller = QualityTestController()
        Result = Controller.StopQualityTestService()

        LoggingService.LogInfo(f"StopQualityTestService completed: {Result.get('Success', False)}", "QualityTestController", "StopQualityTestService")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in StopQualityTestService endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "StopQualityTestService")
        return jsonify({
            "Success": False,
            "Message": "Failed to stop quality test service",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/QualityTest/Retry', methods=['POST'])
def RetryQualityTest():
    try:
        LoggingService.LogFunctionEntry("RetryQualityTest", "QualityTestController")

        Controller = QualityTestController()
        Data = request.get_json()
        JobId = Data.get('JobId') if Data else None

        if not JobId:
            return jsonify({"Success": False, "Message": "JobId required"}), 400

        Result = Controller.RetryQualityTest(JobId)

        LoggingService.LogInfo(f"RetryQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "RetryQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in RetryQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "RetryQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to retry quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/api/QualityTesting/History', methods=['GET'])
def GetQualityTestHistory():
    Controller = QualityTestController()
    Page = request.args.get('Page', 1, type=int)
    Limit = request.args.get('Limit', 10, type=int)

    # Validate parameters
    if Page < 1:
        Page = 1
    if Limit < 1 or Limit > 50:  # Max 50 per page
        Limit = 10

    Result = Controller.GetQualityTestHistory(Page, Limit)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTesting/Progress', methods=['GET'])
def GetQualityTestProgress():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestProgress()
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTesting/LogError', methods=['POST'])
def LogQualityTestError():
    Controller = QualityTestController()
    Data = request.get_json()

    if not Data:
        return jsonify({"Success": False, "Message": "No data provided"}), 400

    ErrorMessage = Data.get('ErrorMessage', '')
    ErrorContext = Data.get('ErrorContext', '')
    RequestUrl = Data.get('RequestUrl', '')

    Result = Controller.LogError(ErrorMessage, ErrorContext, RequestUrl)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/AddToQueue', methods=['POST'])
def AddToQueue():
    Controller = QualityTestController()
    Data = request.get_json()

    if not Data:
        return jsonify({"Success": False, "Message": "No data provided"}), 400

    TranscodeAttemptId = Data.get('TranscodeAttemptId')
    if not TranscodeAttemptId:
        return jsonify({"Success": False, "Message": "TranscodeAttemptId required"}), 400

    Result = Controller.AddToQueue(TranscodeAttemptId)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/Skip', methods=['POST'])
def SkipQualityTest():
    """Skip quality test for a transcode attempt"""
    Controller = QualityTestController()
    Data = request.get_json()

    if not Data:
        return jsonify({"Success": False, "Message": "No data provided"}), 400

    TranscodeAttemptId = Data.get('TranscodeAttemptId')
    if not TranscodeAttemptId:
        return jsonify({"Success": False, "Message": "TranscodeAttemptId required"}), 400

    # Use the business service to handle the skip logic
    from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
    business_service = QualityTestingBusinessService(Controller.DatabaseManager)
    Result = business_service.SkipQualityTest(TranscodeAttemptId)

    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/CancelActive', methods=['POST'])
def CancelActiveQualityTest():
    """Cancel the currently running quality test"""
    try:
        LoggingService.LogFunctionEntry("CancelActiveQualityTest", "QualityTestController")

        Controller = QualityTestController()

        # Use the business service to handle the cancel logic
        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        business_service = QualityTestingBusinessService(Controller.DatabaseManager)
        Result = business_service.CancelActiveQualityTest()

        LoggingService.LogInfo(f"CancelActiveQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "CancelActiveQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in CancelActiveQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "CancelActiveQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to cancel quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/api/QualityTest/StopAfterCurrent', methods=['POST'])
def StopQualityTestAfterCurrent():
    """Graceful stop - allow current quality test to complete before stopping."""
    try:
        LoggingService.LogFunctionEntry("StopQualityTestAfterCurrent", "QualityTestController")

        # Update ServiceStatus to GracefulStop
        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'GracefulStop',
            'IsProcessing': False
        })

        if success:
            LoggingService.LogInfo("Graceful stop requested - quality testing will complete current job before stopping",
                                 "QualityTestController", "StopQualityTestAfterCurrent")
            return jsonify({
                "Success": True,
                "Message": "Graceful stop requested - quality testing will complete current job before stopping",
                "Status": "GracefulStop"
            })
        else:
            LoggingService.LogError("Failed to request graceful stop", "QualityTestController", "StopQualityTestAfterCurrent")
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to request graceful stop"
            }), 500

    except Exception as e:
        errorMsg = f"Exception requesting graceful stop: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "StopQualityTestAfterCurrent")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Pause', methods=['POST'])
def PauseQualityTest():
    """Pause quality test queue - finish current job, don't start new ones."""
    try:
        LoggingService.LogFunctionEntry("PauseQualityTest", "QualityTestController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'Paused',
            'IsProcessing': False
        })

        if success:
            LoggingService.LogInfo("Quality testing paused successfully",
                                 "QualityTestController", "PauseQualityTest")
            return jsonify({
                "Success": True,
                "Message": "Quality testing paused - current job will complete, no new jobs will start"
            })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to pause quality testing"
            }), 500

    except Exception as e:
        errorMsg = f"Exception pausing quality testing: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "PauseQualityTest")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Resume', methods=['POST'])
def ResumeQualityTest():
    """Resume quality test queue processing."""
    try:
        LoggingService.LogFunctionEntry("ResumeQualityTest", "QualityTestController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'Running',
            'IsProcessing': True
        })

        if success:
            LoggingService.LogInfo("Quality testing resumed successfully",
                                 "QualityTestController", "ResumeQualityTest")
            return jsonify({
                "Success": True,
                "Message": "Quality testing resumed - queue processing will continue"
            })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to resume quality testing"
            }), 500

    except Exception as e:
        errorMsg = f"Exception resuming quality testing: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "ResumeQualityTest")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500
