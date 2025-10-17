"""
QualityTestController - Simple controller for quality testing operations
Implements MVVM pattern using MVVM architecture
"""

import os
import subprocess
import json
from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.QualityTestQueueService import QualityTestQueueService

QualityTestBlueprint = Blueprint('QualityTest', __name__)

class QualityTestController:
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.LoggingService = LoggingService()
        self.QualityTestQueueService = QualityTestQueueService(self.DatabaseManager)
    
    def StartQualityTest(self, JobId: int) -> dict:
        """Start a quality test for the specified job"""
        try:
            self.LoggingService.LogInfo(f"Starting quality test for job {JobId}")
            
            # Get job details from QualityTestingQueue
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}
            
            # Create active job record
            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="QualityTest",
                JobType="QualityTest", 
                QueueId=JobId,
                ProcessId=os.getpid(),
                ThreadId=0
            )
            
            if ActiveJobId == 0:
                return {"Success": False, "Message": "Failed to create active job"}
            
            # Run FFmpeg VMAF comparison
            Result = self.RunFFmpegVMAF(JobDetails)
            
            # Update job status
            if Result["Success"]:
                self.DatabaseManager.UpdateQualityTestStatus(JobId, "Completed", Result["VMAFScore"])
                self.DatabaseManager.CompleteActiveJob(ActiveJobId)
                return {"Success": True, "VMAFScore": Result["VMAFScore"]}
            else:
                self.DatabaseManager.UpdateQualityTestStatus(JobId, "Failed", None)
                self.DatabaseManager.CompleteActiveJob(ActiveJobId)
                return {"Success": False, "Message": Result["Error"]}
                
        except Exception as e:
            self.LoggingService.LogError(f"Error starting quality test: {str(e)}")
            return {"Success": False, "Message": str(e)}
    
    def RunFFmpegVMAF(self, JobDetails: dict) -> dict:
        """Run FFmpeg VMAF comparison"""
        try:
            OriginalFile = JobDetails["LocalSourcePath"]
            TranscodedFile = JobDetails["TranscodedFilePath"]
            
            # Get the full path to FFmpeg executable
            ffmpeg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FFmpegMaster", "bin", "ffmpeg.exe")
            
            # Build FFmpeg command for VMAF comparison
            Command = [
                ffmpeg_path,
                "-i", TranscodedFile,
                "-i", OriginalFile,
                "-lavfi", "[0:v][1:v]libvmaf=log_path=vmaf_output.xml:n_subsample=10",
                "-f", "null",
                "-"
            ]
            
            self.LoggingService.LogInfo(f"Running FFmpeg VMAF: {' '.join(Command)}")
            
            # Execute FFmpeg without timeout (VMAF calculations can take a long time)
            Result = subprocess.run(Command, capture_output=True, text=True)
            
            if Result.returncode == 0:
                # Parse VMAF score from output
                VMAFScore = self.ParseVMAFScore(Result.stderr)
                return {"Success": True, "VMAFScore": VMAFScore}
            else:
                return {"Success": False, "Error": Result.stderr}
                
        except subprocess.TimeoutExpired:
            return {"Success": False, "Error": "FFmpeg timeout (this should not happen as timeout was removed)"}
        except Exception as e:
            return {"Success": False, "Error": str(e)}
    
    def ParseVMAFScore(self, Output: str) -> float:
        """Parse VMAF score from FFmpeg output"""
        try:
            # Look for VMAF score in output
            Lines = Output.split('\n')
            for Line in Lines:
                if 'VMAF score:' in Line:
                    Score = float(Line.split('VMAF score:')[1].strip())
                    return Score
            return 0.0
        except:
            return 0.0
    
    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a quality test job"""
        try:
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if JobDetails:
                return {"Success": True, "Status": JobDetails["Status"], "VMAFScore": JobDetails.get("VMAFScore")}
            else:
                return {"Success": False, "Message": "Job not found"}
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
    
    def StartQualityTestService(self, MaxConcurrentJobs: int = 1) -> dict:
        """Start the quality test service"""
        try:
            self.LoggingService.LogInfo(f"Starting quality test service with {MaxConcurrentJobs} concurrent jobs")
            
            # This would typically start a background service
            # For now, we'll just return success
            return {"Success": True, "Message": "Quality test service started"}
        except Exception as e:
            self.LoggingService.LogError(f"Error starting quality test service: {str(e)}")
            return {"Success": False, "Message": str(e)}
    
    def StopQualityTestService(self) -> dict:
        """Stop the quality test service"""
        try:
            self.LoggingService.LogInfo("Stopping quality test service")
            
            # This would typically stop the background service
            # For now, we'll just return success
            return {"Success": True, "Message": "Quality test service stopped"}
        except Exception as e:
            self.LoggingService.LogError(f"Error stopping quality test service: {str(e)}")
            return {"Success": False, "Message": str(e)}
    
    def LogError(self, ErrorMessage: str, ErrorContext: str, RequestUrl: str) -> dict:
        """Log an error to the database"""
        try:
            self.LoggingService.LogError(f"Quality Test Error - Context: {ErrorContext}, URL: {RequestUrl}, Message: {ErrorMessage}")
            return {"Success": True, "Message": "Error logged successfully"}
        except Exception as e:
            return {"Success": False, "Message": str(e)}
    
    def RetryQualityTest(self, JobId: int) -> dict:
        """Retry a failed quality test job"""
        try:
            self.LoggingService.LogInfo(f"Retrying quality test for job {JobId}")
            
            # Get job details
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}
            
            # Reset job status to Pending and increment retry count
            Success = self.DatabaseManager.ResetQualityTestJobForRetry(JobId)
            if Success:
                return {"Success": True, "Message": "Job reset for retry"}
            else:
                return {"Success": False, "Message": "Failed to reset job for retry"}
                
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
    
    def RequeueAttempt(self, TranscodeAttemptId: int) -> dict:
        """Requeue a transcode attempt for quality testing."""
        try:
            self.LoggingService.LogInfo(f"Requeuing transcode attempt {TranscodeAttemptId} for quality testing", "QualityTestController", "RequeueAttempt")
            
            # Delete existing quality test records for this attempt
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}
            
            # Use QualityTestQueueService to add to queue (handles all validation and file path resolution)
            JobId = self.QualityTestQueueService.AddToQualityTestQueue(TranscodeAttemptId)
            
            if JobId:
                self.LoggingService.LogInfo(f"Successfully queued quality test job {JobId} for transcode attempt {TranscodeAttemptId}", 
                                          "QualityTestController", "RequeueAttempt")
                return {"Success": True, "Message": "Quality test queued successfully", "JobId": JobId}
            else:
                return {"Success": False, "Message": "Failed to create quality test queue entry"}
                
        except Exception as e:
            ErrorMsg = f"Exception requeuing transcode attempt {TranscodeAttemptId}: {str(e)}"
            self.LoggingService.LogException(ErrorMsg, e, "QualityTestController", "RequeueAttempt")
            return {"Success": False, "Message": ErrorMsg}

# Flask routes
@QualityTestBlueprint.route('/QualityTest/Start', methods=['POST'])
def StartQualityTest():
    try:
        LoggingService.LogFunctionEntry("StartQualityTest", "QualityTestController")
        
        Controller = QualityTestController()
        Data = request.get_json()
        
        # Check if this is a service start request or individual job start
        if Data and 'MaxConcurrentJobs' in Data:
            # Service start request
            MaxConcurrentJobs = Data.get('MaxConcurrentJobs', 1)
            Result = Controller.StartQualityTestService(MaxConcurrentJobs)
        else:
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

@QualityTestBlueprint.route('/api/QualityTest/RequeueAttempt', methods=['POST'])
def RequeueAttempt():
    Controller = QualityTestController()
    Data = request.get_json()
    
    if not Data:
        return jsonify({"Success": False, "Message": "No data provided"}), 400
    
    TranscodeAttemptId = Data.get('TranscodeAttemptId')
    if not TranscodeAttemptId:
        return jsonify({"Success": False, "Message": "TranscodeAttemptId required"}), 400
    
    Result = Controller.RequeueAttempt(TranscodeAttemptId)
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Skip', methods=['POST'])
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
    from Services.QualityTestingBusinessService import QualityTestingBusinessService
    business_service = QualityTestingBusinessService(Controller.DatabaseManager)
    Result = business_service.SkipQualityTest(TranscodeAttemptId)
    
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/CancelActive', methods=['POST'])
def CancelActiveQualityTest():
    """Cancel the currently running quality test"""
    try:
        LoggingService.LogFunctionEntry("CancelActiveQualityTest", "QualityTestController")
        
        Controller = QualityTestController()
        
        # Use the business service to handle the cancel logic
        from Services.QualityTestingBusinessService import QualityTestingBusinessService
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
