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
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService


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
        result_id = None
        active_job_id = None

        try:
            # Get job details from QualityTestingQueue
            job_details = self.DatabaseManager.GetQualityTestJob(JobId)
            if not job_details:
                return {"Success": False, "Message": "Job not found"}

            # Create QualityTestResult record immediately (Status="Running")
            result_id = self.DatabaseManager.CreateQualityTestResult(
                TranscodeAttemptId=job_details['TranscodeAttemptId'],
                Status="Running",
                TestDate=datetime.now(timezone.utc)
            )

            if result_id == 0:
                error_msg = f"Failed to create quality test result for TranscodeAttempt {job_details['TranscodeAttemptId']}"
                LoggingService.LogError(error_msg, "QualityTestingBusinessService", "StartQualityTest")
                return {"Success": False, "Message": "Failed to create quality test result"}

            # Create active job record
            active_job_id = self.DatabaseManager.CreateActiveJob(
                ServiceName="QualityTestService",
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
                # Pass active_job_id and result_id so we can track the FFmpeg child process
                job_details['active_job_id'] = active_job_id
                job_details['result_id'] = result_id
                result = self.BuildVMAFCommand(job_details, progress_id)

                # Update QualityTestResult with completion details
                if result["Success"]:
                    # VMAF score and Status='Success' are already updated by UpdateQualityTestResultsWithScore
                    # Update TranscodeAttempt
                    self.DatabaseManager.UpdateTranscodeAttempt(
                        job_details['TranscodeAttemptId'],
                        {"QualityTestCompleted": 1, "VMAF": result["VMAFScore"]}
                    )
                    self.UpdateProgressRecord(progress_id, "Completed", 100, "VMAF analysis completed successfully", result["VMAFScore"])
                    self.DatabaseManager.CompleteActiveJob(active_job_id, True)
                    return {"Success": True, "VMAFScore": result["VMAFScore"]}
                else:
                    # Update result with failure
                    self.DatabaseManager.UpdateQualityTestResultFailure(
                        result_id,
                        result.get("Error", "Unknown error")
                    )
                    self.UpdateProgressRecord(progress_id, "Failed", 0, result.get("Error", "Unknown error"))
                    self.DatabaseManager.CompleteActiveJob(active_job_id, False, result.get("Error", "Unknown error"))
                    return {"Success": False, "Message": result.get("Error", "Unknown error")}

            except Exception as e:
                # Update result with exception
                if result_id:
                    self.DatabaseManager.UpdateQualityTestResultFailure(
                        result_id,
                        str(e)
                    )
                if 'progress_id' in locals():
                    self.UpdateProgressRecord(progress_id, "Failed", 0, str(e))
                self.DatabaseManager.CompleteActiveJob(active_job_id, False, str(e))
                raise

        except Exception as e:
            LoggingService.LogException(f"Error starting quality test for job {JobId}", e, "QualityTestingBusinessService", "StartQualityTest")
            return {"Success": False, "Message": str(e)}
        finally:
            # Delete from queue (regardless of success/failure)
            self.DatabaseManager.DeleteQualityTestQueueItem(JobId)

    def BuildVMAFCommand(self, JobDetails: dict, ProgressId: int = None) -> dict:
        """Run FFmpeg VMAF comparison with resolution scaling."""
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

            # Get video resolutions to check if scaling is needed
            original_resolution = self.GetVideoResolution(original_file, ffmpeg_path)
            transcoded_resolution = self.GetVideoResolution(transcoded_file, ffmpeg_path)

            # Check if resolutions match
            if original_resolution == transcoded_resolution:
                # Resolutions match - use direct VMAF comparison without scaling
                vmaf_filter = "[0:v]format=yuv420p[dist];[1:v]format=yuv420p[ref];[dist][ref]libvmaf=log_path=vmaf_output.xml:n_subsample=10"
                LoggingService.LogInfo(f"Resolutions match ({original_resolution[0]}x{original_resolution[1]}) - using direct VMAF comparison", "QualityTestingBusinessService", "BuildVMAFCommand")
            else:
                # Resolutions don't match - determine target resolution and scale both videos
                target_width, target_height = self.DetermineVMAFTargetResolution(original_resolution, transcoded_resolution)
                vmaf_filter = f"[0:v]scale={target_width}:{target_height},format=yuv420p[dist];[1:v]scale={target_width}:{target_height},format=yuv420p[ref];[dist][ref]libvmaf=log_path=vmaf_output.xml:n_subsample=10"
                LoggingService.LogInfo(f"Resolutions don't match (Original: {original_resolution[0]}x{original_resolution[1]}, Transcoded: {transcoded_resolution[0]}x{transcoded_resolution[1]}) - scaling to {target_width}x{target_height}", "QualityTestingBusinessService", "BuildVMAFCommand")

            # Get StartTime from TranscodeAttempts table if available
            StartTime = None
            if JobDetails.get('TranscodeAttemptId'):
                try:
                    # Query TranscodeAttempts table for StartTime
                    StartTimeResult = self.DatabaseManager.DatabaseService.ExecuteQuery(
                        "SELECT StartTime FROM TranscodeAttempts WHERE Id = %s",
                        (JobDetails['TranscodeAttemptId'],)
                    )
                    if StartTimeResult and StartTimeResult[0]['StartTime']:
                        StartTime = StartTimeResult[0]['StartTime']
                        LoggingService.LogInfo(f"Retrieved StartTime {StartTime} for TranscodeAttempt {JobDetails['TranscodeAttemptId']}",
                                             "QualityTestingBusinessService", "BuildVMAFCommand")
                except Exception as e:
                    LoggingService.LogException("Error retrieving StartTime from TranscodeAttempts", e,
                                             "QualityTestingBusinessService", "BuildVMAFCommand")

            # Build command as string (like TranscodeService)
            # VMAF structure: ffmpeg -i original_file -i transcoded_file -lavfi [vmaf filter]
            command_parts = [ffmpeg_path]

            # Add start time parameter to original file input if specified
            if StartTime and StartTime.strip():
                command_parts.extend(["-ss", StartTime.strip()])

            # Add input files (no CUDA acceleration) - quote paths to handle spaces
            command_parts.extend(["-i", f'"{original_file}"', "-i", f'"{transcoded_file}"'])

            # Add VMAF filter and output options
            command_parts.extend(["-lavfi", vmaf_filter, "-f", "null", "-"])

            # Build final command string
            command = " ".join(command_parts)

            LoggingService.LogInfo(f"Quality Test FFmpeg command: {command}", "QualityTestingBusinessService", "BuildVMAFCommand")
            LoggingService.LogInfo(f"Command type: {type(command)}", "QualityTestingBusinessService", "BuildVMAFCommand")
            LoggingService.LogInfo(f"Command length: {len(command)}", "QualityTestingBusinessService", "BuildVMAFCommand")

            # Store command string for database
            FFmpegCommandString = command

            # Update the existing QualityTestResults record with FFmpeg command
            result_id = JobDetails.get('result_id')
            if result_id:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    "UPDATE QualityTestResults SET FFmpegCommand = %s WHERE Id = %s",
                    (FFmpegCommandString, result_id)
                )


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
                # Parse VMAF score from XML file (FFmpeg creates vmaf_output.xml)
                vmaf_score = self.ParseVMAFScore("")


                # Update QualityTestResults table with VMAF score
                result_id = JobDetails.get('result_id')
                if ProgressId and result_id:
                    self.UpdateQualityTestResultsWithScore(result_id, vmaf_score, result)

                # Check if auto-replace should be triggered based on VMAF score
                auto_replace_result = self.CheckAndTriggerAutoReplace(JobDetails, vmaf_score)

                return {"Success": True, "VMAFScore": vmaf_score, "FFmpegCommand": FFmpegCommandString, "AutoReplaceTriggered": auto_replace_result.get('Triggered', False)}
            else:
                error_msg = f"FFmpeg failed with return code {result.returncode}"
                return {"Success": False, "Error": error_msg}

        except subprocess.TimeoutExpired:
            return {"Success": False, "Error": "FFmpeg timeout (this should not happen as timeout was removed)"}
        except Exception as e:
            return {"Success": False, "Error": str(e)}

    def GetVideoResolution(self, VideoFilePath: str, FFmpegPath: str) -> tuple:
        """Get video resolution (width, height) from video file."""
        try:
            import subprocess
            import re

            # Guard: FFmpegPath.replace() crashes with AttributeError if FFmpegPath is None.
            # Fail loudly so the actual misconfiguration shows in logs instead of a NoneType error.
            if not FFmpegPath:
                LoggingService.LogError(
                    f"GetVideoResolution called with FFmpegPath=None for {VideoFilePath}. "
                    f"Caller must resolve FFmpegPath before calling this method.",
                    "GetVideoResolution", "QualityTestingBusinessService"
                )
                return None, None

            # Use FFprobe to get video resolution -- derive ffprobe path from ffmpeg path
            FFprobePath = FFmpegPath.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
            probe_command = [
                FFprobePath,
                "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                VideoFilePath
            ]

            result = subprocess.run(probe_command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                # Parse width,height from output
                resolution_line = result.stdout.strip()
                if ',' in resolution_line:
                    width, height = resolution_line.split(',')
                    return (int(width), int(height))

            # Fallback: try to parse from ffmpeg info
            info_command = [FFmpegPath, "-i", VideoFilePath, "-f", "null", "-"]
            result = subprocess.run(info_command, capture_output=True, text=True, timeout=30)

            if result.stderr:
                # Look for resolution in stderr output
                resolution_match = re.search(r'(\d+)x(\d+)', result.stderr)
                if resolution_match:
                    width = int(resolution_match.group(1))
                    height = int(resolution_match.group(2))
                    return (width, height)

            # Default fallback
            LoggingService.LogWarning(f"Could not determine resolution for {VideoFilePath}, using default 1920x1080", "QualityTestingBusinessService", "GetVideoResolution")
            return (1920, 1080)

        except Exception as e:
            LoggingService.LogException(f"Error getting video resolution for {VideoFilePath}", e, "QualityTestingBusinessService", "GetVideoResolution")
            return (1920, 1080)  # Default fallback

    def DetermineVMAFTargetResolution(self, OriginalResolution: tuple, TranscodedResolution: tuple) -> tuple:
        """Determine target resolution for VMAF comparison (use smaller resolution)."""
        try:
            original_width, original_height = OriginalResolution
            transcoded_width, transcoded_height = TranscodedResolution

            # Use the smaller resolution to avoid upscaling
            if (transcoded_width * transcoded_height) <= (original_width * original_height):
                target_width = transcoded_width
                target_height = transcoded_height
                LoggingService.LogInfo(f"Using transcoded resolution for VMAF: {target_width}x{target_height}", "QualityTestingBusinessService", "DetermineVMAFTargetResolution")
            else:
                target_width = original_width
                target_height = original_height
                LoggingService.LogInfo(f"Using original resolution for VMAF: {target_width}x{target_height}", "QualityTestingBusinessService", "DetermineVMAFTargetResolution")

            # Ensure dimensions are even numbers (required by some codecs)
            if target_width % 2 != 0:
                target_width -= 1
            if target_height % 2 != 0:
                target_height -= 1

            return (target_width, target_height)

        except Exception as e:
            LoggingService.LogException("Error determining VMAF target resolution", e, "QualityTestingBusinessService", "DetermineVMAFTargetResolution")
            return (1920, 1080)  # Default fallback

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
            active_jobs = self.DatabaseManager.GetActiveJobs("QualityTestService")

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

    def GetQualityTestMaxCores(self) -> int:
        """Get maximum CPU cores for quality testing from system settings.

        Raises:
            ValueError: If setting is missing, invalid, or out of range (1-32)
            Exception: If database access fails
        """
        # Get QualityTestMaxCores setting
        QualityTestMaxCores = self.DatabaseManager.GetSystemSetting('QualityTestMaxCores')
        if not QualityTestMaxCores:
            raise ValueError("QualityTestMaxCores setting is missing from SystemSettings. Please add it to the database.")

        if not QualityTestMaxCores.isdigit():
            raise ValueError(f"QualityTestMaxCores setting has invalid value: '{QualityTestMaxCores}'. Must be a number between 1-32.")

        CoreCount = int(QualityTestMaxCores)
        # Validate core count (1-32 for safety)
        if not (1 <= CoreCount <= 32):
            raise ValueError(f"QualityTestMaxCores setting value {CoreCount} is out of valid range (1-32).")

        return CoreCount

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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
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

            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

            # Update progress record (VMAF scores go to QualityTestResults, not here)
            query = """
                UPDATE QualityTestProgress
                SET Status = %s, ProgressPercentage = %s, CurrentStep = %s, UpdatedAt = %s,
                    ETA = %s, CurrentFrame = %s, CurrentTime = %s, ProcessingSpeed = %s
                WHERE Id = %s
            """
            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (Status, ProgressPercentage, CurrentStep, current_time, ETA, CurrentFrame, CurrentTime, ProcessingSpeed, ProgressId))

        except Exception as e:
            LoggingService.LogException(f"Error updating progress record {ProgressId}", e, "QualityTestingBusinessService", "UpdateProgressRecord")

    def ExecuteFFmpegWithProgress(self, command: str, ProgressId: int = None, JobDetails: dict = None):
        """Execute FFmpeg with real-time progress monitoring (using same pattern as TranscodeService)."""
        try:
            import subprocess
            import threading
            import time
            from datetime import datetime

            LoggingService.LogInfo(f"Final command string: {command}", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Start timing
            StartTime = datetime.now(timezone.utc)

            # Execute FFmpeg command (same pattern as TranscodeService)
            Process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            LoggingService.LogInfo(f"subprocess.Popen completed successfully", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            LoggingService.LogInfo(f"Process started with PID: {Process.pid}", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Set CPU affinity using topology-based core selection (E-cores for quality test)
            FFmpegPID = None
            TranscodeAttemptId = JobDetails.get('TranscodeAttemptId') if JobDetails else None
            JobIdForAffinity = TranscodeAttemptId if TranscodeAttemptId else Process.pid

            try:
                from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                CoreCount = self.GetQualityTestMaxCores()

                AffinityResult = CpuAffinityServiceInstance.SetFFmpegProcessAffinity(
                    ShellProcessPID=Process.pid,
                    CoreCount=CoreCount,
                    JobId=JobIdForAffinity,
                    JobType="QualityTest",
                    ServiceName="QualityTestingBusinessService"
                )

                if AffinityResult["Success"]:
                    FFmpegPID = AffinityResult["FFmpegPID"]
                    if AffinityResult.get("ErrorMessage"):
                        LoggingService.LogWarning(f"CPU affinity set but with warning: {AffinityResult['ErrorMessage']}",
                                                 "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
                else:
                    LoggingService.LogWarning(f"Failed to set CPU affinity: {AffinityResult.get('ErrorMessage', 'Unknown error')}",
                                             "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            except Exception as AffinityError:
                LoggingService.LogWarning(f"Failed to set CPU affinity: {AffinityError}",
                                         "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Update ActiveJob with FFmpeg child process PID (use FFmpeg PID if available, otherwise shell PID)
            ProcessPIDToUse = FFmpegPID if FFmpegPID else Process.pid
            if JobDetails and 'active_job_id' in JobDetails and JobDetails['active_job_id']:
                self.DatabaseManager.UpdateActiveJobProcessId(
                    JobDetails['active_job_id'],
                    ProcessPIDToUse
                )
                LoggingService.LogInfo(f"Updated ActiveJob {JobDetails['active_job_id']} with PID {ProcessPIDToUse} (FFmpeg: {FFmpegPID is not None})",
                                      "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Start progress monitoring thread (same pattern as TranscodeService)
            if ProgressId:
                ProgressThread = threading.Thread(
                    target=self.MonitorVMAFProgress,
                    args=(ProgressId, Process, JobDetails),
                    daemon=True
                )
                ProgressThread.start()

            # Wait for process to complete (same pattern as TranscodeService)
            LoggingService.LogInfo(f"Waiting for process to complete...", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            ReturnCode = Process.wait()
            EndTime = datetime.now(timezone.utc)
            Duration = (EndTime - StartTime).total_seconds()

            # Release job from CpuAffinityService (with cooling wait enabled)
            # Use same JobId that was used for registration (JobIdForAffinity)
            if JobIdForAffinity:
                try:
                    from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                    CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                    CpuAffinityServiceInstance.ReleaseJob(JobIdForAffinity, WaitForCooling=True)
                except Exception as ReleaseError:
                    LoggingService.LogWarning(f"Failed to release quality test job {JobIdForAffinity} from CpuAffinityService: {ReleaseError}",
                                            "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            LoggingService.LogInfo(f"Process completed with return code: {ReturnCode}", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            LoggingService.LogInfo(f"Duration: {Duration} seconds", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Capture any error output if the process failed (same pattern as TranscodeService)
            if ReturnCode != 0:
                try:
                    # Read any remaining output
                    Output, ErrorOutput = Process.communicate()
                    if Output:
                        LoggingService.LogError(f"FFmpeg stdout: {Output}", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
                    if ErrorOutput:
                        LoggingService.LogError(f"FFmpeg stderr: {ErrorOutput}", "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
                except Exception as e:
                    LoggingService.LogException("Exception reading FFmpeg output", e, "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")

            # Create a result object similar to subprocess.run
            class FFmpegResult:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            return FFmpegResult(ReturnCode, "", "")

        except Exception as e:
            # Release job from CpuAffinityService on error
            TranscodeAttemptId = JobDetails.get('TranscodeAttemptId') if JobDetails else None
            if TranscodeAttemptId:
                try:
                    from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                    CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                    CpuAffinityServiceInstance.ReleaseJob(TranscodeAttemptId)
                except Exception:
                    pass  # Ignore errors during cleanup

            LoggingService.LogException("Error executing FFmpeg with progress monitoring", e, "QualityTestingBusinessService", "ExecuteFFmpegWithProgress")
            # Let it fail - don't run a second FFmpeg process
            raise

    def MonitorVMAFProgress(self, ProgressId: int, Process: subprocess.Popen, JobDetails: dict = None):
        """Monitor VMAF progress and update database (using same pattern as TranscodeService)."""
        try:
            import time

            while Process.poll() is None:
                # Read output line by line
                Line = Process.stdout.readline()
                if Line:
                    ProgressData = self.ParseFFmpegProgressLine(Line.strip(), JobDetails)
                    if ProgressData and ProgressId:
                        progress_percent = ProgressData.get('progress_percent', 0)
                        current_time = ProgressData.get('current_time', '')
                        current_frame = ProgressData.get('current_frame', 0)
                        fps = ProgressData.get('fps', 0.0)
                        speed = ProgressData.get('speed', 0.0)
                        eta = ProgressData.get('eta', '')

                        # Debug logging for ETA calculation
                        if current_frame % 100 == 0:  # Log every 100 frames to avoid spam
                            LoggingService.LogInfo(f"VMAF Progress - Frame: {current_frame}, Progress: {progress_percent:.1f}%, ETA: {eta}, Speed: {speed:.2f}x", "QualityTestingBusinessService", "MonitorVMAFProgress")

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

                time.sleep(0.1)  # Small delay to prevent excessive CPU usage

            # Read any remaining output (only if process is still running)
            try:
                if Process.poll() is None:
                    RemainingOutput = Process.stdout.read()
                    if RemainingOutput:
                        Lines = RemainingOutput.split('\n')
                        for Line in Lines:
                            if Line.strip():
                                ProgressData = self.ParseFFmpegProgressLine(Line.strip(), JobDetails)
                                if ProgressData and ProgressId:
                                    progress_percent = ProgressData.get('progress_percent', 0)
                                    current_time = ProgressData.get('current_time', '')
                                    current_frame = ProgressData.get('current_frame', 0)
                                    fps = ProgressData.get('fps', 0.0)
                                    speed = ProgressData.get('speed', 0.0)
                                    eta = ProgressData.get('eta', '')

                                    if current_frame > 0:
                                        current_step = f"Processing VMAF analysis - {fps:.1f} fps"
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
            except (ValueError, OSError):
                # Process stdout is closed, ignore
                pass

        except Exception as e:
            LoggingService.LogException("Exception monitoring VMAF progress", e, "QualityTestingBusinessService", "MonitorVMAFProgress")

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

                                # Calculate ETA based on processing speed and remaining time
                                if speed > 0 and total_seconds > 0:
                                    # For VMAF processing, estimate based on current progress and speed
                                    # VMAF typically processes at a fraction of real-time speed
                                    if progress_percent > 0:
                                        # Estimate total time based on current progress and speed
                                        estimated_total_time = total_seconds / (progress_percent / 100.0)
                                        remaining_time = estimated_total_time - total_seconds

                                        if remaining_time > 0:
                                            eta_hours = int(remaining_time // 3600)
                                            eta_minutes = int((remaining_time % 3600) // 60)
                                            eta_seconds = int(remaining_time % 60)
                                            eta = f"{eta_hours:02d}:{eta_minutes:02d}:{eta_seconds:02d}"
                                            LoggingService.LogDebug(f"ETA calculated: {eta} (remaining_time: {remaining_time:.1f}s, total_time: {estimated_total_time:.1f}s)", "QualityTestingBusinessService", "ParseFFmpegProgressLine")
                                        else:
                                            eta = "00:00:01"  # Almost done
                                    else:
                                        # Very early in processing, use a rough estimate
                                        eta = "Calculating..."
                                else:
                                    # Fallback ETA calculation
                                    if total_seconds > 0:
                                        # Rough estimate: assume VMAF takes 2-3x video duration
                                        estimated_remaining = max(30, video_duration * 2 - total_seconds)
                                        eta_hours = int(estimated_remaining // 3600)
                                        eta_minutes = int((estimated_remaining % 3600) // 60)
                                        eta_seconds = int(estimated_remaining % 60)
                                        eta = f"{eta_hours:02d}:{eta_minutes:02d}:{eta_seconds:02d}"
                                    else:
                                        eta = "Calculating..."
                            else:
                                # Fallback: rough estimate based on time elapsed
                                progress_percent = min(90, (total_seconds / 30) * 10)
                                eta = "Calculating..."

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

    def UpdateQualityTestResultsWithScore(self, ResultId: int, VMAFScore: float, FFmpegResult):
        """Update QualityTestResults record with VMAF score and test results."""
        try:
            CurrentTime = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

            # Calculate test duration from FFmpegResult if available
            TestDuration = 0.0  # Could extract from FFmpegResult if needed

            # Determine if it passes threshold
            PassesThreshold = VMAFScore >= 80.0
            Rank = 1 if PassesThreshold else 0

            Query = """
                UPDATE QualityTestResults
                SET VMAFScore = %s,
                    TestDuration = %s,
                    PassesThreshold = %s,
                    Rank = %s,
                    DateTested = %s,
                    Status = 'Success'
                WHERE Id = %s
            """

            Result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (
                VMAFScore,
                TestDuration,
                PassesThreshold,
                Rank,
                CurrentTime,
                ResultId
            ))

            if not Result:
                LoggingService.LogError(f"Failed to update QualityTestResults for record {ResultId}",
                                      "QualityTestingBusinessService", "UpdateQualityTestResultsWithScore")
            else:
                LoggingService.LogInfo(f"Successfully updated QualityTestResults record {ResultId} with VMAF score {VMAFScore}",
                                     "QualityTestingBusinessService", "UpdateQualityTestResultsWithScore")

        except Exception as e:
            LoggingService.LogException(f"Error updating QualityTestResults for record {ResultId}", e,
                                       "QualityTestingBusinessService", "UpdateQualityTestResultsWithScore")

    def CheckAndTriggerAutoReplace(self, JobDetails: dict, VMAFScore: float) -> dict:
        """Check VMAF score against thresholds and trigger auto-replace if within range."""
        try:
            LoggingService.LogFunctionEntry("CheckAndTriggerAutoReplace", "QualityTestingBusinessService", VMAFScore)

            # Get VMAF thresholds from database
            thresholds = self.DatabaseManager.GetVMAFThresholds()
            min_threshold = thresholds.get('MinThreshold')
            max_threshold = thresholds.get('MaxThreshold')

            if min_threshold is None or max_threshold is None:
                LoggingService.LogError("VMAF thresholds not properly retrieved from database", "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
                return {"Triggered": False, "Error": "VMAF thresholds not found in database"}

            LoggingService.LogInfo(f"Checking VMAF score {VMAFScore} against thresholds: Min={min_threshold}, Max={max_threshold}",
                                 "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")

            # Check if VMAF score is within auto-replace range
            if min_threshold <= VMAFScore <= max_threshold:
                LoggingService.LogInfo(f"VMAF score {VMAFScore} is within auto-replace range, triggering file replacement",
                                     "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")

                # Get transcode attempt ID
                transcode_attempt_id = JobDetails.get('TranscodeAttemptId')
                if not transcode_attempt_id:
                    LoggingService.LogError("No TranscodeAttemptId found in job details for auto-replace",
                                           "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
                    return {"Triggered": False, "Error": "No TranscodeAttemptId found"}

                # Trigger file replacement
                from Services.FileReplacementBusinessService import FileReplacementBusinessService
                file_replacement_service = FileReplacementBusinessService(self.DatabaseManager)

                # Pass the VMAF score directly to avoid race condition with database update
                replacement_result = file_replacement_service.ProcessFileReplacementWithVMAF(transcode_attempt_id, VMAFScore, BypassVMAFCheck=False)

                if replacement_result.get('Success', False):
                    # Update TranscodeAttempts table with replacement info
                    self.UpdateTranscodeAttemptReplacementStatus(transcode_attempt_id, True, "Auto")

                    LoggingService.LogInfo(f"Auto-replace completed successfully for TranscodeAttempt {transcode_attempt_id}",
                                         "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
                    return {"Triggered": True, "Success": True}
                else:
                    LoggingService.LogError(f"Auto-replace failed for TranscodeAttempt {transcode_attempt_id}: {replacement_result.get('ErrorMessage', 'Unknown error')}",
                                           "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
                    return {"Triggered": True, "Success": False, "Error": replacement_result.get('ErrorMessage', 'Unknown error')}
            else:
                LoggingService.LogInfo(f"VMAF score {VMAFScore} is outside auto-replace range (Min={min_threshold}, Max={max_threshold}), manual review required",
                                     "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
                return {"Triggered": False, "Reason": "VMAF score outside auto-replace range"}

        except Exception as e:
            LoggingService.LogException("Error checking and triggering auto-replace", e, "QualityTestingBusinessService", "CheckAndTriggerAutoReplace")
            return {"Triggered": False, "Error": str(e)}

    def UpdateTranscodeAttemptReplacementStatus(self, TranscodeAttemptId: int, FileReplaced: bool, ReplacementType: str) -> bool:
        """Update TranscodeAttempts table with file replacement status."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeAttemptReplacementStatus", "QualityTestingBusinessService", TranscodeAttemptId, FileReplaced, ReplacementType)

            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

            query = """
                UPDATE TranscodeAttempts
                SET FileReplaced = %s, FileReplacedDate = %s, ReplacementType = %s
                WHERE Id = %s
            """

            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (
                FileReplaced,
                current_time if FileReplaced else None,
                ReplacementType,
                TranscodeAttemptId
            ))

            if result:
                LoggingService.LogInfo(f"Updated replacement status for TranscodeAttempt {TranscodeAttemptId}: FileReplaced={FileReplaced}, Type={ReplacementType}",
                                     "QualityTestingBusinessService", "UpdateTranscodeAttemptReplacementStatus")
                return True
            else:
                LoggingService.LogError(f"Failed to update replacement status for TranscodeAttempt {TranscodeAttemptId}",
                                       "QualityTestingBusinessService", "UpdateTranscodeAttemptReplacementStatus")
                return False

        except Exception as e:
            LoggingService.LogException("Error updating transcode attempt replacement status", e, "QualityTestingBusinessService", "UpdateTranscodeAttemptReplacementStatus")
            return False

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

    def SkipQualityTest(self, TranscodeAttemptId: int) -> dict:
        """Skip quality test for a transcode attempt and replace file immediately - handles both queued and running tests"""
        try:
            LoggingService.LogFunctionEntry("SkipQualityTest", "QualityTestingBusinessService", TranscodeAttemptId)

            # Check if there's an active quality test for this attempt
            active_job = self.DatabaseManager.GetActiveQualityTestJob()
            is_running = False

            if active_job and active_job.get('TranscodeAttemptId') == TranscodeAttemptId:
                is_running = True
                LoggingService.LogInfo(f"Active quality test found for TranscodeAttempt {TranscodeAttemptId}, will cancel it",
                                     "QualityTestingBusinessService", "SkipQualityTest")

            # If running, kill the FFmpeg process first
            if is_running:
                kill_success = self.DatabaseManager.KillActiveQualityTestProcess(active_job['Id'])
                if not kill_success:
                    LoggingService.LogWarning(f"Failed to kill FFmpeg process for active job {active_job['Id']}",
                                            "QualityTestingBusinessService", "SkipQualityTest")

            # Delete from QualityTestingQueue (if exists)
            queue_deleted = self.DatabaseManager.DeleteQualityTestQueueItem(active_job['QueueId'] if is_running else None)

            # Update TranscodeAttempts to skip quality test
            skip_success = self.DatabaseManager.SkipQualityTest(TranscodeAttemptId)

            if not skip_success:
                return {"Success": False, "Message": "Failed to update TranscodeAttempts record"}

            # Clean up progress and active job records if it was running
            if is_running:
                # Clean up QualityTestProgress
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId = %s",
                    (TranscodeAttemptId,)
                )

                # Complete the active job
                self.DatabaseManager.CompleteActiveJob(active_job['Id'], False, "Cancelled by user skip request")

            # Now trigger file replacement immediately since quality test is being skipped
            LoggingService.LogInfo(f"Quality test skipped for TranscodeAttempt {TranscodeAttemptId}, triggering immediate file replacement",
                                 "QualityTestingBusinessService", "SkipQualityTest")
            from Services.FileReplacementBusinessService import FileReplacementBusinessService
            file_replacement_service = FileReplacementBusinessService(self.DatabaseManager)
            replacement_result = file_replacement_service.ProcessFileReplacement(TranscodeAttemptId, BypassVMAFCheck=True)

            if replacement_result.get("Success", False):
                # Create quality test result record showing test was skipped but file was replaced successfully
                CurrentTime = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                Query = """
                    INSERT INTO QualityTestResults
                    (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                    VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                """

                params = (
                    TranscodeAttemptId,
                    0.0,  # TestDuration
                    True,  # PassesThreshold (file was replaced successfully)
                    1,  # Rank (1 = successful)
                    "Quality test skipped by user - file replaced automatically",  # ErrorMessage field used for note
                    "",  # FFmpegCommand
                    "Success",  # Status
                    95.0  # VMAFScore (use high score to indicate auto-replacement)
                )

                result_id = self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, params)

                LoggingService.LogInfo(f"Successfully replaced file for TranscodeAttempt {TranscodeAttemptId} after skip and created quality test result record",
                                     "QualityTestingBusinessService", "SkipQualityTest")
                return {"Success": True, "Message": "Quality test skipped and file replaced successfully"}
            else:
                LoggingService.LogWarning(f"Quality test skipped but file replacement failed for TranscodeAttempt {TranscodeAttemptId}: {replacement_result.get('ErrorMessage', 'Unknown error')}",
                                        "QualityTestingBusinessService", "SkipQualityTest")
                return {"Success": False, "Message": f"Quality test skipped but file replacement failed: {replacement_result.get('ErrorMessage', 'Unknown error')}"}

        except Exception as e:
            LoggingService.LogException(f"Error skipping quality test for TranscodeAttempt {TranscodeAttemptId}", e,
                                      "QualityTestingBusinessService", "SkipQualityTest")
            return {"Success": False, "Message": str(e)}

    def CancelActiveQualityTest(self) -> dict:
        """Cancel the currently running quality test and trigger next job"""
        try:
            LoggingService.LogFunctionEntry("CancelActiveQualityTest", "QualityTestingBusinessService")

            # Get active quality test job
            active_job = self.DatabaseManager.GetActiveQualityTestJob()
            if not active_job:
                return {"Success": False, "Message": "No active quality test found"}

            transcode_attempt_id = active_job.get('TranscodeAttemptId')
            if not transcode_attempt_id:
                return {"Success": False, "Message": "No TranscodeAttemptId found in active job"}

            LoggingService.LogInfo(f"Cancelling active quality test for TranscodeAttempt {transcode_attempt_id}",
                                 "QualityTestingBusinessService", "CancelActiveQualityTest")

            # Kill FFmpeg process
            kill_success = self.DatabaseManager.KillActiveQualityTestProcess(active_job['Id'])
            if not kill_success:
                LoggingService.LogWarning(f"Failed to kill FFmpeg process for active job {active_job['Id']}",
                                        "QualityTestingBusinessService", "CancelActiveQualityTest")

            # Delete from QualityTestingQueue
            queue_deleted = self.DatabaseManager.DeleteQualityTestQueueItem(active_job['QueueId'])

            # Update TranscodeAttempts to skip quality test
            skip_success = self.DatabaseManager.SkipQualityTest(transcode_attempt_id)
            if not skip_success:
                return {"Success": False, "Message": "Failed to update TranscodeAttempts record"}

            # Update QualityTestResults to mark as cancelled
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "UPDATE QualityTestResults SET Status = 'Cancelled', ErrorMessage = 'Cancelled by user' WHERE TranscodeAttemptId = %s AND Status = 'Running'",
                (transcode_attempt_id,)
            )

            # Clean up progress and active job records
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId = %s",
                (transcode_attempt_id,)
            )

            # Complete the active job
            self.DatabaseManager.CompleteActiveJob(active_job['Id'], False, "Cancelled by user")

            LoggingService.LogInfo(f"Successfully cancelled quality test for TranscodeAttempt {transcode_attempt_id}",
                                 "QualityTestingBusinessService", "CancelActiveQualityTest")

            return {"Success": True, "Message": "Active quality test cancelled successfully"}

        except Exception as e:
            LoggingService.LogException("Error cancelling active quality test", e,
                                      "QualityTestingBusinessService", "CancelActiveQualityTest")
            return {"Success": False, "Message": str(e)}
