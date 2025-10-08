#!/usr/bin/env python3
"""
Quality Testing Business Service
Business logic layer for quality testing using VMAF analysis
Implements MVVM pattern using MVVM architecture
"""

import os
import subprocess
import time
import threading
from datetime import datetime
from Services.LoggingService import LoggingService


class QualityTestingBusinessService:
    """Quality Testing Business Service - Business logic layer."""
    
    def __init__(self, DatabaseManagerInstance=None):
        """Initialize the business service with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance
        self.ActiveFFmpegProcess = None
        self.ActiveFFmpegThread = None
        
    
    def ProcessQualityTestQueue(self) -> dict:
        """Process the quality testing queue."""
        try:
            LoggingService.LogDebug("Processing quality testing queue", "QualityTestingBusinessService", "ProcessQualityTestQueue")
            
            # Get pending jobs from queue
            pending_jobs = self.DatabaseManager.GetQualityTestQueue()
            
            if not pending_jobs:
                return {"Success": True, "Message": "No pending jobs", "JobsProcessed": 0}
            
            jobs_processed = 0
            for job in pending_jobs:
                try:
                    # Process each job
                    result = self.StartQualityTest(job['Id'])
                    if result.get('Success'):
                        jobs_processed += 1
                    else:
                        LoggingService.LogError(f"Failed to process job {job['Id']}: {result.get('Message', 'Unknown error')}", "QualityTestingBusinessService", "ProcessQualityTestQueue")
                        
                except Exception as e:
                    LoggingService.LogException(f"Error processing job {job['Id']}", e, "QualityTestingBusinessService", "ProcessQualityTestQueue")
            
            return {"Success": True, "Message": f"Processed {jobs_processed} jobs", "JobsProcessed": jobs_processed}
            
        except Exception as e:
            LoggingService.LogException("Error processing quality test queue", e, "QualityTestingBusinessService", "ProcessQualityTestQueue")
            return {"Success": False, "Message": str(e)}
    
    def ProcessClaimedJob(self, job: dict) -> dict:
        """Process a claimed quality test job."""
        try:
            
            # Start quality test for the claimed job
            result = self.StartQualityTest(job['Id'])
            
            LoggingService.LogDebug(f"Job {job['Id']} processing result: {result}", "QualityTestingBusinessService", "ProcessClaimedJob")
            return result
            
        except Exception as e:
            LoggingService.LogException(f"Error processing claimed job {job['Id']}", e, "QualityTestingBusinessService", "ProcessClaimedJob")
            return {"Success": False, "Message": str(e)}
    
    def StartQualityTest(self, JobId: int) -> dict:
        """Start a quality test for the specified job."""
        try:
            
            # Get job details from QualityTestingQueue
            job_details = self.DatabaseManager.GetQualityTestJob(JobId)
            if not job_details:
                return {"Success": False, "Message": "Job not found"}
            
            # Create active job record
            active_job_id = self.DatabaseManager.CreateActiveJob(
                ServiceName="QualityTestingService",
                JobType="QualityTest", 
                QueueId=JobId,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident()
            )
            
            if active_job_id == 0:
                return {"Success": False, "Message": "Failed to create active job"}
            
            try:
                # Create single progress tracking record
                progress_id = self.CreateProgressRecord(JobId, job_details)
                
                # Run FFmpeg VMAF comparison with progress tracking
                result = self.RunFFmpegVMAF(job_details, progress_id)
                
                # Update job status
                if result["Success"]:
                    self.DatabaseManager.UpdateQualityTestStatus(JobId, "Completed", result["VMAFScore"])
                    self.UpdateProgressRecord(progress_id, "Completed", 100, "VMAF analysis completed successfully", result["VMAFScore"])
                    self.DatabaseManager.CompleteActiveJob(active_job_id, True)
                    return {"Success": True, "VMAFScore": result["VMAFScore"]}
                else:
                    self.DatabaseManager.UpdateQualityTestStatus(JobId, "Failed", None)
                    self.UpdateProgressRecord(progress_id, "Failed", 0, result.get("Error", "Unknown error"))
                    self.DatabaseManager.CompleteActiveJob(active_job_id, False, result.get("Error", "Unknown error"))
                    return {"Success": False, "Message": result.get("Error", "Unknown error")}
                    
            except Exception as e:
                # Clean up on error
                self.DatabaseManager.UpdateQualityTestStatus(JobId, "Failed", None)
                if 'progress_id' in locals():
                    self.UpdateProgressRecord(progress_id, "Failed", 0, str(e))
                self.DatabaseManager.CompleteActiveJob(active_job_id, False, str(e))
                raise
                
        except Exception as e:
            LoggingService.LogException(f"Error starting quality test for job {JobId}", e, "QualityTestingBusinessService", "StartQualityTest")
            return {"Success": False, "Message": str(e)}
    
    def RunFFmpegVMAF(self, JobDetails: dict, ProgressId: int = None) -> dict:
        """Run FFmpeg VMAF comparison."""
        try:
            original_file = JobDetails["LocalSourcePath"]
            transcoded_file = JobDetails["TranscodedFilePath"]
            
            # Verify files exist
            if not os.path.exists(original_file):
                return {"Success": False, "Error": f"Original file not found: {original_file}"}
            
            if not os.path.exists(transcoded_file):
                return {"Success": False, "Error": f"Transcoded file not found: {transcoded_file}"}
            
            # Get the full path to FFmpeg executable
            ffmpeg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FFmpegMaster", "bin", "ffmpeg.exe")
            
            # Verify FFmpeg exists
            if not os.path.exists(ffmpeg_path):
                return {"Success": False, "Error": f"FFmpeg executable not found: {ffmpeg_path}"}
            
            # Build FFmpeg command for VMAF comparison with threading
            command = [
                ffmpeg_path,
                "-threads", "6",  # Use 6 threads for faster processing
                "-i", transcoded_file,
                "-i", original_file,
                "-lavfi", "[0:v][1:v]libvmaf=log_path=vmaf_output.xml:log_fmt=xml:n_threads=6",
                "-f", "null",
                "-"
            ]
            
            
            # Update progress - starting VMAF analysis
            if ProgressId:
                self.UpdateProgressRecord(ProgressId, "Processing", 0, "Starting VMAF analysis")
            
            # Update progress - FFmpeg is running
            if ProgressId:
                self.UpdateProgressRecord(ProgressId, "Processing", 50, "FFmpeg VMAF analysis in progress...")
            
            # Execute FFmpeg with real-time progress monitoring
            result = self.ExecuteFFmpegWithProgress(command, ProgressId, JobDetails)
            
            # Update progress - VMAF analysis completed
            if ProgressId:
                self.UpdateProgressRecord(ProgressId, "Processing", 95, "VMAF analysis completed, parsing results")
            
            if result.returncode == 0:
                # Parse VMAF score from output (check both stdout and stderr)
                vmaf_score = self.ParseVMAFScore(result.stderr)
                
                # If not found in stderr, try stdout
                if vmaf_score == 0.0:
                    vmaf_score = self.ParseVMAFScore(result.stdout)
                
                
                # Update QualityTestResults table
                if ProgressId:
                    self.UpdateQualityTestResults(JobDetails, vmaf_score, result)
                
                return {"Success": True, "VMAFScore": vmaf_score}
            else:
                error_msg = result.stderr if result.stderr else "FFmpeg failed with no error output"
                return {"Success": False, "Error": error_msg}
                
        except subprocess.TimeoutExpired:
            return {"Success": False, "Error": "FFmpeg timeout (this should not happen as timeout was removed)"}
        except Exception as e:
            return {"Success": False, "Error": str(e)}
    
    def ParseVMAFScore(self, Output: str) -> float:
        """Parse VMAF score from FFmpeg output."""
        try:
            
            # Look for VMAF score in output
            lines = Output.split('\n')
            for line in lines:
                if 'VMAF score:' in line:
                    score = float(line.split('VMAF score:')[1].strip())
                    return score
                elif 'VMAF' in line and 'score' in line:
                    # Alternative parsing for different output formats
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'VMAF' in part and i + 1 < len(parts):
                            try:
                                score = float(parts[i + 1])
                                return score
                            except ValueError:
                                continue
            
            # Try to parse from XML output file if it exists
            try:
                import xml.etree.ElementTree as ET
                if os.path.exists('vmaf_output.xml'):
                    tree = ET.parse('vmaf_output.xml')
                    root = tree.getroot()
                    
                    # Look for VMAF score in the pooled_metrics section
                    for metric in root.findall('.//metric[@name="vmaf"]'):
                        mean_score = metric.get('mean')
                        if mean_score:
                            return float(mean_score)
                    
            except Exception as xml_error:
                LoggingService.LogException("Error parsing VMAF XML file", xml_error, "QualityTestingBusinessService", "ParseVMAFScore")
            
            return 0.0
            
        except Exception as e:
            LoggingService.LogException("Error parsing VMAF score", e, "QualityTestingBusinessService", "ParseVMAFScore")
            return 0.0
    
    def GetActiveJobs(self) -> dict:
        """Get list of active quality testing jobs."""
        try:
            LoggingService.LogDebug("Getting active quality testing jobs", "QualityTestingBusinessService", "GetActiveJobs")
            
            # Get active jobs from database
            active_jobs = self.DatabaseManager.GetActiveJobs("QualityTestingService")
            
            return {"Success": True, "ActiveJobs": active_jobs}
            
        except Exception as e:
            LoggingService.LogException("Error getting active jobs", e, "QualityTestingBusinessService", "GetActiveJobs")
            return {"Success": False, "Message": str(e)}
    
    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a specific quality test."""
        try:
            LoggingService.LogDebug(f"Getting quality test status for job {JobId}", "QualityTestingBusinessService", "GetQualityTestStatus")
            
            # Get job details from database
            job_details = self.DatabaseManager.GetQualityTestJob(JobId)
            
            if job_details:
                return {
                    "Success": True, 
                    "Status": job_details["Status"], 
                    "VMAFScore": job_details.get("VMAFScore"),
                    "JobId": JobId
                }
            else:
                return {"Success": False, "Message": "Job not found"}
                
        except Exception as e:
            LoggingService.LogException(f"Error getting quality test status for job {JobId}", e, "QualityTestingBusinessService", "GetQualityTestStatus")
            return {"Success": False, "Message": str(e)}
    
    def CheckConcurrencyLimit(self) -> bool:
        """Check if we're within the MaxConcurrentJobs limit."""
        try:
            # Get current active jobs count
            active_jobs_result = self.GetActiveJobs()
            if not active_jobs_result.get("Success"):
                return False
            
            current_jobs = len(active_jobs_result.get("ActiveJobs", []))
            
            # Get MaxConcurrentJobs from settings
            max_jobs_result = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'MaxConcurrentJobs'"
            )
            
            max_jobs = 1  # Default
            if max_jobs_result and max_jobs_result[0]['SettingValue']:
                max_jobs = int(max_jobs_result[0]['SettingValue'])
            
            return current_jobs < max_jobs
            
        except Exception as e:
            LoggingService.LogException("Error checking concurrency limit", e, "QualityTestingBusinessService", "CheckConcurrencyLimit")
            return False
    
    def TerminateActiveFFmpegProcess(self):
        """Terminate any active FFmpeg process."""
        try:
            if self.ActiveFFmpegProcess and self.ActiveFFmpegProcess.poll() is None:
                self.ActiveFFmpegProcess.terminate()
                
                # Wait for graceful termination
                try:
                    self.ActiveFFmpegProcess.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.ActiveFFmpegProcess.kill()
                    self.ActiveFFmpegProcess.wait()
                
                self.ActiveFFmpegProcess = None
                
        except Exception as e:
            LoggingService.LogException("Error terminating FFmpeg process", e, "QualityTestingBusinessService", "TerminateActiveFFmpegProcess")
    
    def MonitorProgress(self, Process, JobId: int):
        """Monitor FFmpeg progress and update database."""
        try:
            
            # This would be implemented for real-time progress tracking
            # For now, we'll just wait for the process to complete
            while Process.poll() is None:
                time.sleep(1)
            
            
        except Exception as e:
            LoggingService.LogException(f"Error monitoring progress for job {JobId}", e, "QualityTestingBusinessService", "MonitorProgress")
    
    def CreateProgressRecord(self, JobId: int, JobDetails: dict) -> int:
        """Create a progress tracking record for the quality test."""
        try:
            # Insert progress record
            query = """
                INSERT INTO QualityTestProgress (
                    TranscodeAttemptId, Status, ProgressPercentage, CurrentStep,
                    StartTime, UpdatedAt, CreatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            transcode_attempt_id = JobDetails.get('TranscodeAttemptId', 0)
            
            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (
                transcode_attempt_id,
                "Started",
                0,
                "Initializing VMAF analysis",
                current_time,
                current_time,
                current_time
            ))
            
            if result:
                progress_id = self.DatabaseManager.DatabaseService.GetLastInsertId()
            else:
                progress_id = 0
            
            return progress_id
            
        except Exception as e:
            LoggingService.LogException(f"Error creating progress record for job {JobId}", e, "QualityTestingBusinessService", "CreateProgressRecord")
            return 0
    
    def UpdateProgressRecord(self, ProgressId: int, Status: str, ProgressPercentage: int, CurrentStep: str, ETA: str = None, CurrentFrame: int = None, CurrentTime: str = None, ProcessingSpeed: str = None):
        """Update a progress tracking record."""
        try:
            
            if ProgressId == 0:
                return
                
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Update progress record (VMAF scores go to QualityTestResults, not here)
            query = """
                UPDATE QualityTestProgress 
                SET Status = ?, ProgressPercentage = ?, CurrentStep = ?, UpdatedAt = ?, 
                    ETA = ?, CurrentFrame = ?, CurrentTime = ?, ProcessingSpeed = ?
                WHERE Id = ?
            """
            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (Status, ProgressPercentage, CurrentStep, current_time, ETA, CurrentFrame, CurrentTime, ProcessingSpeed, ProgressId))
            
        except Exception as e:
            LoggingService.LogException(f"Error updating progress record {ProgressId}", e, "QualityTestingBusinessService", "UpdateProgressRecord")
    
    def ExecuteFFmpegWithProgress(self, command: list, ProgressId: int = None, JobDetails: dict = None):
        """Execute FFmpeg with real-time progress monitoring."""
        try:
            import subprocess
            import re
            import time
            
            # Start FFmpeg process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Monitor progress in real-time
            last_frame_count = 0
            last_progress_percent = 0
            start_time = time.time()
            
            # Debug: Capture raw FFmpeg output to file
            debug_file = open('ffmpeg_debug_output.txt', 'w')
            
            while True:
                # Read a line from stderr (where FFmpeg outputs progress)
                line = process.stderr.readline()
                if not line:
                    break
                
                # Debug: Write raw output to file
                debug_file.write(line)
                debug_file.flush()
                
                # Parse progress from FFmpeg output
                if 'frame=' in line and 'fps=' in line:
                    progress_info = self.ParseFFmpegProgressLine(line, JobDetails)
                    if progress_info and ProgressId:
                        progress_percent = progress_info.get('progress_percent', 0)
                        current_time = progress_info.get('current_time', '')
                        current_frame = progress_info.get('current_frame', 0)
                        fps = progress_info.get('fps', 0.0)
                        speed = progress_info.get('speed', 0.0)
                        eta = progress_info.get('eta', '')
                        
                        # Update progress for every frame - real-time updates
                        if current_frame > 0:
                            # Create a simple current step description
                            current_step = f"Processing VMAF analysis - {fps:.1f} fps"
                            
                            # Format processing speed as string
                            processing_speed = f"{speed:.2f}x"
                            
                            self.UpdateProgressRecord(
                                ProgressId, 
                                "Processing", 
                                int(progress_percent), 
                                current_step, 
                                ETA=eta,
                                CurrentFrame=current_frame,
                                CurrentTime=current_time,
                                ProcessingSpeed=processing_speed
                            )
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            # Write any remaining output to debug file
            if stderr:
                debug_file.write("=== FINAL STDERR ===\n")
                debug_file.write(stderr)
                debug_file.write("\n")
            if stdout:
                debug_file.write("=== FINAL STDOUT ===\n")
                debug_file.write(stdout)
                debug_file.write("\n")
            
            # Close debug file
            debug_file.close()
            
            # Create a result object similar to subprocess.run
            class FFmpegResult:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr
            
            return FFmpegResult(process.returncode, stdout, stderr)
            
        except Exception as e:
            LoggingService.LogException("Error executing FFmpeg with progress monitoring", e, "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            # Let it fail - don't run a second FFmpeg process
            raise
    
    def ParseFFmpegProgressLine(self, line: str, JobDetails: dict = None) -> dict:
        """Parse progress information from FFmpeg output line."""
        try:
            import re
            
            # More flexible regex pattern that handles various FFmpeg output formats
            PROGRESS_RE = re.compile(
                # frame=    34
                r'frame=\s*(?P<frame>\S+)\s+'
                # fps= 22
                r'fps=\s*(?P<fps>\S+)\s+'
                # q=-0.0
                r'q=\s*(?P<q>\S+)\s+'
                # size=N/A (using [^\s]+ to capture N/A or a byte size)
                r'size=\s*(?P<size>[^\s]+)\s+'
                # time=00:00:02.90
                r'time=\s*(?P<time>\S+)\s+'
                # bitrate=N/A
                r'bitrate=\s*(?P<bitrate>\S+)\s+'
                # speed=1.87x
                r'speed=\s*(?P<speed>\S+)\s*'
                # elapsed=0:00:01.55 (MAKE THIS WHOLE SECTION OPTIONAL)
                r'(?:elapsed=\s*(?P<elapsed>\S+)\s*)?'
                # Handles potential extra characters at the end
                r'.*'
            )
            
            match = PROGRESS_RE.search(line)
            if match:
                current_frame = int(match.group('frame'))
                fps = float(match.group('fps'))
                quality = float(match.group('q'))
                
                # Handle N/A values for size and bitrate
                size_str = match.group('size')
                size_kb = 0 if size_str == 'N/A' else int(size_str)
                
                current_time = match.group('time')
                
                bitrate_str = match.group('bitrate')
                bitrate = 0.0 if bitrate_str == 'N/A' else float(bitrate_str)
                
                speed_str = match.group('speed')
                # Remove 'x' from speed if present
                speed = float(speed_str.rstrip('x'))
                
                # Calculate progress percentage based on time elapsed
                # This is an approximation since VMAF doesn't give us total duration
                progress_percent = 0
                eta = ""
                
                # Try to parse time format (HH:MM:SS.mmm)
                time_parts = current_time.split(':')
                if len(time_parts) >= 3:
                    try:
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1])
                        seconds = float(time_parts[2])
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        
                        # Calculate progress percentage based on video duration
                        if JobDetails:
                            video_duration = self.GetVideoDuration(JobDetails)
                            if video_duration > 0:
                                progress_percent = min(95, (total_seconds / video_duration) * 100)
                                
                                # Calculate ETA based on actual video duration and processing speed
                                if speed > 0:
                                    # Total processing time = video duration / speed
                                    total_processing_time = video_duration / speed
                                    remaining_time = total_processing_time - total_seconds
                                    
                                    if remaining_time > 0:
                                        eta_hours = int(remaining_time // 3600)
                                        eta_minutes = int((remaining_time % 3600) // 60)
                                        eta_seconds = int(remaining_time % 60)
                                        eta = f"{eta_hours:02d}:{eta_minutes:02d}:{eta_seconds:02d}"
                            else:
                                # Fallback: rough estimate based on time elapsed
                                progress_percent = min(90, (total_seconds / 30) * 10)
                            
                    except (ValueError, IndexError):
                        pass
                
                return {
                    'current_frame': current_frame,
                    'fps': fps,
                    'current_time': current_time,
                    'progress_percent': progress_percent,
                    'eta': eta,
                    'quality': quality,
                    'size_kb': size_kb,
                    'bitrate': bitrate,
                    'speed': speed
                }
            
            return None
            
        except Exception as e:
            LoggingService.LogException("Error parsing FFmpeg progress line", e, "QualityTestingBusinessService", "ParseFFmpegProgressLine")
            return None
    
    def UpdateQualityTestResults(self, JobDetails: dict, VMAFScore: float, FFmpegResult):
        """Update QualityTestResults table with VMAF analysis results."""
        try:
            query = """
                INSERT INTO QualityTestResults (
                    VMAFQueueId, TranscodeAttemptId, VMAFScore, ProfileId, ProfileName,
                    FileSize, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            queue_id = JobDetails.get('Id', 0)
            transcode_attempt_id = JobDetails.get('TranscodeAttemptId', 0)
            profile_id = JobDetails.get('ProfileId', 0)
            profile_name = JobDetails.get('ProfileName', 'Unknown')
            
            # Get file size
            file_size = 0
            transcoded_file = JobDetails.get('TranscodedFilePath', '')
            if transcoded_file and os.path.exists(transcoded_file):
                file_size = os.path.getsize(transcoded_file)
            
            # Calculate test duration (rough estimate)
            test_duration = 0.0  # We could track this if needed
            
            # Determine if it passes threshold (assuming 80 is the threshold)
            passes_threshold = VMAFScore >= 80.0
            
            # Set rank (could be based on VMAF score)
            rank = 1 if passes_threshold else 0
            
            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (
                queue_id,
                transcode_attempt_id,
                VMAFScore,
                profile_id,
                profile_name,
                file_size,
                test_duration,
                passes_threshold,
                rank,
                None,  # No error message for successful tests
                current_time
            ))
            
            if not result:
                LoggingService.LogError(f"Failed to update QualityTestResults for queue {queue_id}", "QualityTestingBusinessService", "UpdateQualityTestResults")
                
        except Exception as e:
            LoggingService.LogException(f"Error updating QualityTestResults for queue {JobDetails.get('Id', 0)}", e, "QualityTestingBusinessService", "UpdateQualityTestResults")
    
    def GetVideoDuration(self, JobDetails: dict) -> float:
        """Get video duration in seconds from the transcoded file."""
        try:
            import subprocess
            
            transcoded_file = JobDetails.get('TranscodedFilePath', '')
            if not transcoded_file or not os.path.exists(transcoded_file):
                return 0.0
            
            # Get the full path to FFprobe executable
            ffprobe_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FFmpegMaster", "bin", "ffprobe.exe")
            
            if not os.path.exists(ffprobe_path):
                return 0.0
            
            # Use FFprobe to get video duration
            command = [
                ffprobe_path,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                transcoded_file
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                return duration
            
            return 0.0
            
        except Exception as e:
            LoggingService.LogException(f"Error getting video duration for {JobDetails.get('TranscodedFilePath', '')}", e, "QualityTestingBusinessService", "GetVideoDuration")
            return 0.0
