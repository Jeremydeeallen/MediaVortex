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
                "-lavfi", "[0:v][1:v]libvmaf=log_path=vmaf_output.xml:log_fmt=xml",
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

# Flask routes
@QualityTestBlueprint.route('/api/QualityTest/Start', methods=['POST'])
def StartQualityTest():
    Controller = QualityTestController()
    Data = request.get_json()
    JobId = Data.get('JobId')
    
    if not JobId:
        return jsonify({"Success": False, "Message": "JobId required"}), 400
    
    Result = Controller.StartQualityTest(JobId)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/Status/<int:JobId>', methods=['GET'])
def GetQualityTestStatus(JobId):
    Controller = QualityTestController()
    Result = Controller.GetQualityTestStatus(JobId)
    return jsonify(Result)

@QualityTestBlueprint.route('/api/QualityTest/Queue', methods=['GET'])
def GetQualityTestQueue():
    Controller = QualityTestController()
    Result = Controller.GetQualityTestQueue()
    return jsonify(Result)
