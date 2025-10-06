#!/usr/bin/env python3
"""
Quality Testing Business Service
Business logic layer for quality testing using MVVM architecture
"""

import sys
import os
import subprocess
import threading
import re
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.LoggingService import LoggingService


class QualityTestingBusinessService:
    """Quality Testing Business Service - Business logic layer."""
    
    def __init__(self, DatabaseManagerInstance=None):
        """Initialize the business service with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance
        self.ActiveFFmpegProcess = None  # Track active FFmpeg process
        
        LoggingService.LogInfo("QualityTestingBusinessService initialized", "QualityTestingBusinessService", "__init__")
    
    def ProcessQualityTestQueue(self) -> dict:
        """Process pending quality test jobs from the queue."""
        try:
            LoggingService.LogInfo("Processing quality test queue", "QualityTestingBusinessService", "ProcessQualityTestQueue")
            
            # Get pending jobs
            pending_jobs = self.DatabaseManager.GetQualityTestQueue()
            if not pending_jobs:
                LoggingService.LogInfo("No pending quality test jobs found", "QualityTestingBusinessService", "ProcessQualityTestQueue")
                return {"Success": True, "Message": "No pending jobs", "JobsProcessed": 0}
            
            # Check concurrency limit
            max_concurrent = self.CheckConcurrencyLimit()
            active_jobs = self.GetActiveJobs()
            
            if len(active_jobs) >= max_concurrent:
                LoggingService.LogInfo(f"At concurrency limit ({max_concurrent}), waiting", "QualityTestingBusinessService", "ProcessQualityTestQueue")
                return {"Success": True, "Message": "At concurrency limit", "JobsProcessed": 0}
            
            # Process jobs up to the limit
            jobs_to_process = max_concurrent - len(active_jobs)
            processed_count = 0
            
            for job in pending_jobs[:jobs_to_process]:
                if job.get('Status') == 'Pending':
                    LoggingService.LogInfo(f"Processing quality test job {job['Id']}", "QualityTestingBusinessService", "ProcessQualityTestQueue")
                    result = self.StartQualityTest(job['Id'])
                    if result.get('Success'):
                        processed_count += 1
                    LoggingService.LogInfo(f"Job {job['Id']} result: {result}", "QualityTestingBusinessService", "ProcessQualityTestQueue")
            
            LoggingService.LogInfo(f"Processed {processed_count} quality test jobs", "QualityTestingBusinessService", "ProcessQualityTestQueue")
            return {"Success": True, "Message": f"Processed {processed_count} jobs", "JobsProcessed": processed_count}
            
        except Exception as e:
            LoggingService.LogException("Error processing quality test queue", e, "QualityTestingBusinessService", "ProcessQualityTestQueue")
            return {"Success": False, "Message": str(e)}
    
    def StartQualityTest(self, JobId: int) -> dict:
        """Start a quality test for the specified job."""
        try:
            LoggingService.LogInfo(f"Starting quality test for job {JobId}", "QualityTestingBusinessService", "StartQualityTest")
            
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
            
            # Update job status and store results
            if Result["Success"]:
                LoggingService.LogInfo(f"Quality test completed successfully for job {JobId}, VMAF score: {Result['VMAFScore']}", "QualityTestingBusinessService", "StartQualityTest")
                
                # Store VMAF score in QualityTestResults table
                store_result = self.DatabaseManager.StoreQualityTestResult(JobId, JobDetails, Result["VMAFScore"])
                if not store_result:
                    LoggingService.LogError(f"Failed to store quality test result for job {JobId}", "QualityTestingBusinessService", "StartQualityTest")
                    return {"Success": False, "Message": "Failed to store quality test result"}
                
                # Remove from queue (revolving door)
                remove_result = self.DatabaseManager.RemoveFromQualityTestQueue(JobId)
                if not remove_result:
                    LoggingService.LogError(f"Failed to remove job {JobId} from quality test queue", "QualityTestingBusinessService", "StartQualityTest")
                    return {"Success": False, "Message": "Failed to remove job from queue"}
                
                # Complete active job
                complete_result = self.DatabaseManager.CompleteActiveJob(ActiveJobId)
                if not complete_result:
                    LoggingService.LogError(f"Failed to complete active job {ActiveJobId} for job {JobId}", "QualityTestingBusinessService", "StartQualityTest")
                    return {"Success": False, "Message": "Failed to complete active job"}
                
                LoggingService.LogInfo(f"Quality test job {JobId} fully completed and cleaned up", "QualityTestingBusinessService", "StartQualityTest")
                return {"Success": True, "VMAFScore": Result["VMAFScore"]}
            else:
                # Check if this is a process termination vs actual failure
                error_message = Result.get("Error", "")
                if "process terminated" in error_message.lower() or "interrupted" in error_message.lower():
                    # Don't remove from queue if process was terminated - leave for retry
                    LoggingService.LogInfo(f"Job {JobId} interrupted, leaving in queue for retry", "QualityTestingBusinessService", "StartQualityTest")
                    self.DatabaseManager.CompleteActiveJob(ActiveJobId, success=False, error_message="Process interrupted")
                    return {"Success": False, "Message": "Process interrupted, job left in queue for retry"}
                else:
                    # Remove failed job from queue only for actual FFmpeg failures
                    self.DatabaseManager.RemoveFromQualityTestQueue(JobId)
                    self.DatabaseManager.CompleteActiveJob(ActiveJobId, success=False, error_message=Result["Error"])
                    return {"Success": False, "Message": Result["Error"]}
                
        except Exception as e:
            LoggingService.LogException("Error starting quality test", e, "QualityTestingBusinessService", "StartQualityTest")
            return {"Success": False, "Message": str(e)}
    
    def RunFFmpegVMAF(self, JobDetails: dict) -> dict:
        """Run FFmpeg VMAF comparison asynchronously with progress tracking."""
        try:
            OriginalFile = JobDetails["OriginalFilePath"]
            TranscodedFile = JobDetails["TranscodedFilePath"]
            JobId = JobDetails["Id"]
            
            # Get FFmpeg path
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ffmpeg_path = os.path.join(project_root, "FFmpegMaster", "bin", "ffmpeg.exe")
            
            # Build FFmpeg command for VMAF comparison (using working format)
            Command = [
                ffmpeg_path,
                "-i", TranscodedFile,
                "-i", OriginalFile,
                "-lavfi", "[1:v]scale=1280x720[ref];[0:v][ref]libvmaf=log_fmt=xml:log_path=vmaf_results.xml",
                "-f", "null",
                "-"
            ]
            
            LoggingService.LogInfo(f"Running FFmpeg VMAF: {' '.join(Command)}", "QualityTestingBusinessService", "RunFFmpegVMAF")
            
            # Start FFmpeg process asynchronously
            Process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Track the active process for shutdown handling
            self.ActiveFFmpegProcess = Process
            
            # Start progress monitoring thread
            ProgressThread = threading.Thread(
                target=self.MonitorFFmpegProgress,
                args=(Process, JobId, JobDetails),
                daemon=True
            )
            ProgressThread.start()
            
            # Wait for process to complete with timeout checks
            while Process.poll() is None:
                time.sleep(0.1)  # Check every 100ms instead of blocking
            
            # Clear the active process reference
            self.ActiveFFmpegProcess = None
            
            # Check if process was terminated during shutdown
            if Process.returncode == 0:
                # Parse VMAF score from XML output
                VMAFScore = self.ParseVMAFScoreFromXML()
                return {"Success": True, "VMAFScore": VMAFScore}
            else:
                # Check if this was a process termination
                if Process.returncode == 255 or Process.returncode < 0:
                    return {"Success": False, "Error": f"Process terminated with return code {Process.returncode}"}
                else:
                    return {"Success": False, "Error": f"FFmpeg failed with return code {Process.returncode}"}
                
        except KeyboardInterrupt:
            return {"Success": False, "Error": "Process interrupted by user"}
        except Exception as e:
            return {"Success": False, "Error": str(e)}
    
    def MonitorFFmpegProgress(self, Process, JobId: int, JobDetails: dict):
        """Monitor FFmpeg progress and update database."""
        try:
            # Get total frames from MediaFiles table
            total_frames = self.GetTotalFramesFromMediaFiles(JobDetails)
            
            # Initial progress record
            current_time = datetime.now().isoformat()
            progress_data = {
                'TranscodeAttemptId': 0,  # We don't have this in the test
                'Status': 'Running',
                'CurrentStep': 'VMAF analysis starting',
                'StartTime': current_time,
                'ProgressPercentage': 0,
                'CurrentFrame': 0,
                'TotalFrames': total_frames,
                'FramesPerSecond': 0.0,
                'EstimatedTimeRemaining': 0,
                'ErrorMessage': None,
                'SubprocessPID': Process.pid,
                'SubprocessStartTime': current_time
            }
            self.DatabaseManager.SaveQualityTestProgress(JobId, progress_data)
            
            # Store duration when we first see it
            total_duration_seconds = None
            
            # Monitor stderr for progress updates
            while Process.poll() is None:
                line = Process.stderr.readline()
                if line:
                    # Parse frame information
                    frame_match = re.search(r'frame=\s*(\d+)', line)
                    fps_match = re.search(r'fps=\s*([\d.]+)', line)
                    time_match = re.search(r'time=(\d{1,2}:\d{2}:\d{2}\.\d{2})', line)
                    duration_match = re.search(r'Duration: (\d{1,2}:\d{2}:\d{2}\.\d{2})', line)
                    speed_match = re.search(r'speed=\s*([\d.]+)x', line)
                    
                    # Capture duration when we first see it
                    if duration_match and total_duration_seconds is None:
                        try:
                            duration_str = duration_match.group(1)
                            total_duration_seconds = self._time_to_seconds(duration_str)
                        except:
                            pass
                    
                    if frame_match:
                        current_frame = int(frame_match.group(1))
                        fps = float(fps_match.group(1)) if fps_match else 0.0
                        speed = float(speed_match.group(1)) if speed_match else 0.0
                        
                        # Calculate progress percentage (prefer frame-based if available, fallback to time-based)
                        progress_percentage = 0
                        eta_seconds = 0
                        
                        if total_frames > 0:
                            # Frame-based progress (more accurate)
                            progress_percentage = min(95, int((current_frame / total_frames) * 100))
                            
                            # Calculate ETA based on frames
                            if fps > 0:
                                remaining_frames = total_frames - current_frame
                                eta_seconds = remaining_frames / fps
                        elif time_match and total_duration_seconds is not None:
                            # Time-based progress (fallback)
                            try:
                                current_time_str = time_match.group(1)
                                current_seconds = self._time_to_seconds(current_time_str)
                                
                                if total_duration_seconds > 0:
                                    progress_percentage = min(95, int((current_seconds / total_duration_seconds) * 100))
                                    eta_seconds = total_duration_seconds - current_seconds
                            except:
                                progress_percentage = 0
                        
                        # Format ETA
                        eta_formatted = self._format_eta(eta_seconds) if eta_seconds > 0 else None
                        
                        # Update progress
                        progress_data.update({
                            'Status': 'Running',
                            'CurrentStep': f'VMAF analysis in progress - Frame {current_frame}',
                            'CurrentFrame': current_frame,
                            'TotalFrames': total_frames,
                            'FramesPerSecond': fps,
                            'ProcessingSpeed': f"{speed}x" if speed > 0 else None,
                            'ProgressPercentage': progress_percentage,
                            'ETA': eta_formatted
                        })
                        self.DatabaseManager.SaveQualityTestProgress(JobId, progress_data)
                        
        except Exception as e:
            LoggingService.LogException("Error monitoring FFmpeg progress", e, "QualityTestingBusinessService", "MonitorFFmpegProgress")
    
    def GetTotalFramesFromMediaFiles(self, JobDetails: dict) -> int:
        """Get total frames from MediaFiles table by joining on file path."""
        try:
            # Try to get total frames from MediaFiles table
            query = """
                SELECT mf.TotalFrames 
                FROM MediaFiles mf 
                WHERE mf.FilePath = ? OR mf.FilePath = ?
            """
            result = self.DatabaseManager.DatabaseService.ExecuteQuery(
                query, (JobDetails.get('OriginalFilePath'), JobDetails.get('TranscodedFilePath'))
            )
            
            if result and len(result) > 0:
                return result[0][0] or 0
            
            return 0
        except Exception as e:
            LoggingService.LogException("Error getting total frames from MediaFiles", e, "QualityTestingBusinessService", "GetTotalFramesFromMediaFiles")
            return 0
    
    def _time_to_seconds(self, time_str: str) -> float:
        """Convert time string (HH:MM:SS.mm) to seconds."""
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except:
            return 0.0
    
    def _format_eta(self, eta_seconds: float) -> str:
        """Format ETA seconds into HH:MM:SS format."""
        try:
            if eta_seconds <= 0:
                return "00:00:00"
            
            hours = int(eta_seconds // 3600)
            minutes = int((eta_seconds % 3600) // 60)
            seconds = int(eta_seconds % 60)
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except:
            return "00:00:00"
    
    def ParseVMAFScoreFromXML(self) -> float:
        """Parse VMAF score from XML output file."""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            xml_file = os.path.join(project_root, "vmaf_results.xml")
            
            if not os.path.exists(xml_file):
                LoggingService.LogError(f"VMAF results XML file not found: {xml_file}", "QualityTestingBusinessService", "ParseVMAFScoreFromXML")
                return 0.0
            
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Look for VMAF score in XML
            for frame in root.findall('.//frame'):
                vmaf_elem = frame.find('metrics/vmaf')
                if vmaf_elem is not None:
                    score = float(vmaf_elem.text)
                    LoggingService.LogInfo(f"Parsed VMAF score from frame data: {score}", "QualityTestingBusinessService", "ParseVMAFScoreFromXML")
                    return score
            
            # If no frame-by-frame, look for overall score
            for metrics in root.findall('.//metrics'):
                vmaf_elem = metrics.find('vmaf')
                if vmaf_elem is not None:
                    score = float(vmaf_elem.text)
                    LoggingService.LogInfo(f"Parsed VMAF score from overall metrics: {score}", "QualityTestingBusinessService", "ParseVMAFScoreFromXML")
                    return score
            
            LoggingService.LogError("No VMAF score found in XML file", "QualityTestingBusinessService", "ParseVMAFScoreFromXML")
            return 0.0
            
        except Exception as e:
            LoggingService.LogException("Error parsing VMAF score from XML", e, "QualityTestingBusinessService", "ParseVMAFScoreFromXML")
            return 0.0
    
    def ParseVMAFScore(self, Output: str) -> float:
        """Parse VMAF score from FFmpeg output (legacy method)."""
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
    
    def GetActiveJobs(self) -> list:
        """Get list of active quality testing jobs."""
        try:
            # Get active jobs from database
            active_jobs = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT * FROM ActiveJobs WHERE ServiceName = ? AND Status = ?", 
                ('QualityTest', 'Running')
            )
            return active_jobs
        except Exception as e:
            LoggingService.LogException("Error getting active jobs", e, "QualityTestingBusinessService", "GetActiveJobs")
            return []
    
    def CheckConcurrencyLimit(self) -> int:
        """Check the maximum concurrent jobs limit."""
        try:
            return self.DatabaseManager.GetMaxConcurrentJobs()
        except Exception as e:
            LoggingService.LogException("Error checking concurrency limit", e, "QualityTestingBusinessService", "CheckConcurrencyLimit")
            return 1  # Default to 1
    
    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a specific quality test."""
        try:
            # Get job details
            job = self.DatabaseManager.GetQualityTestJob(JobId)
            if not job:
                return {"Success": False, "Message": "Job not found"}
            
            # Get progress information
            progress = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT * FROM QualityTestProgress WHERE QualityTestQueueId = ? ORDER BY UpdatedAt DESC LIMIT 1",
                (JobId,)
            )
            
            return {
                "Success": True,
                "Job": job,
                "Progress": progress[0] if progress else None
            }
        except Exception as e:
            LoggingService.LogException("Error getting quality test status", e, "QualityTestingBusinessService", "GetQualityTestStatus")
            return {"Success": False, "Message": str(e)}
    
    def TerminateActiveFFmpegProcess(self):
        """Terminate any active FFmpeg process during shutdown."""
        try:
            if self.ActiveFFmpegProcess and self.ActiveFFmpegProcess.poll() is None:
                LoggingService.LogInfo("Terminating active FFmpeg process during shutdown", "QualityTestingBusinessService", "TerminateActiveFFmpegProcess")
                self.ActiveFFmpegProcess.terminate()
                # Give it a moment to terminate gracefully
                try:
                    self.ActiveFFmpegProcess.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    LoggingService.LogInfo("Force killing FFmpeg process", "QualityTestingBusinessService", "TerminateActiveFFmpegProcess")
                    self.ActiveFFmpegProcess.kill()
                self.ActiveFFmpegProcess = None
        except Exception as e:
            LoggingService.LogException("Error terminating FFmpeg process", e, "QualityTestingBusinessService", "TerminateActiveFFmpegProcess")
    
    def Shutdown(self) -> bool:
        """Graceful shutdown of the business service."""
        try:
            LoggingService.LogInfo("Shutting down QualityTestingBusinessService", "QualityTestingBusinessService", "Shutdown")
            
            # Just log completion - the worker handles FFmpeg termination
            LoggingService.LogInfo("QualityTestingBusinessService shutdown completed", "QualityTestingBusinessService", "Shutdown")
            return True
        except Exception as e:
            LoggingService.LogException("Error during business service shutdown", e, "QualityTestingBusinessService", "Shutdown")
            return False
