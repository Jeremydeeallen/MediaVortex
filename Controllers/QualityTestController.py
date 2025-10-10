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

QualityTestBlueprint = Blueprint('QualityTest', __name__)

class QualityTestController:
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.LoggingService = LoggingService()
    
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
    
    def GetQualityTestHistory(self, Limit: int = 10) -> dict:
        """Get recent quality test results from QualityTestResults table"""
        try:
            Results = self.DatabaseManager.GetQualityTestResults(Limit)
            return {"Success": True, "QualityTestingResults": Results}
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
            
            # Get transcode attempt by ID
            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                return {"Success": False, "Message": "Transcode attempt not found"}
            
            # Verify it was successful
            if not Attempt.Success:
                return {"Success": False, "Message": "Cannot run quality test on failed transcode attempt"}
            
            # Parse FFmpeg command to get file paths
            InputFilePath, OutputFilePath = self.DatabaseManager.ParseFFmpegCommand(Attempt.FfpmpegCommand)
            if not InputFilePath or not OutputFilePath:
                return {"Success": False, "Message": "Could not parse file paths from FFmpeg command"}
            
            # Check if both files exist on disk
            import os
            if not os.path.exists(InputFilePath):
                return {"Success": False, "Message": "Cannot run quality test: Original file path no longer exists"}
            
            if not os.path.exists(OutputFilePath):
                return {"Success": False, "Message": "Cannot run quality test: Transcoded file path no longer exists"}
            
            # Delete existing quality test records for this attempt
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}
            
            # Create new quality test queue entry
            JobId = self.DatabaseManager.CreateQualityTestQueueEntry(
                TranscodeAttemptId, 
                Attempt.FilePath,  # Original file path
                InputFilePath,     # Local source path (from FFmpeg command)
                OutputFilePath     # Transcoded file path (from FFmpeg command)
            )
            
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
    
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Status/<int:JobId>', methods=['GET'])
def GetQualityTestStatus(JobId):
    Controller = QualityTestController()
    Result = Controller.GetQualityTestStatus(JobId)
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Status', methods=['GET'])
def GetQualityTestServiceStatus():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestServiceStatus()
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Queue', methods=['GET'])
def GetQualityTestQueue():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestQueue()
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Stop', methods=['POST'])
def StopQualityTestService():
    Controller = QualityTestController()
    Result = Controller.StopQualityTestService()
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTest/Retry', methods=['POST'])
def RetryQualityTest():
    Controller = QualityTestController()
    Data = request.get_json()
    JobId = Data.get('JobId') if Data else None
    
    if not JobId:
        return jsonify({"Success": False, "Message": "JobId required"}), 400
    
    Result = Controller.RetryQualityTest(JobId)
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTesting/History', methods=['GET'])
def GetQualityTestHistory():
    Controller = QualityTestController()
    Limit = request.args.get('Limit', 10, type=int)
    
    Result = Controller.GetQualityTestHistory(Limit)
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTesting/Progress', methods=['GET'])
def GetQualityTestProgress():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestProgress()
    return jsonify(Result)

@QualityTestBlueprint.route('/QualityTesting/LogError', methods=['POST'])
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

@QualityTestBlueprint.route('/QualityTest/RequeueAttempt', methods=['POST'])
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
