import subprocess
import re
import os
import threading
import time
from collections import deque
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalGetSize
from Core.DateTimeHelpers import ToUtcIsoZ
from Features.ServiceControl.JobPhase import JobPhase


# directive: transcodejob-uses-path | # see path.S5
class VideoTranscodingService:
    """Tool-agnostic video transcoding service that executes transcoding commands with progress tracking."""

    # directive: transcodejob-uses-path | # see path.S5
    def __init__(self):
        self.ActiveProcesses = {}
        self.ProcessThreads = {}
        # Rolling tail of merged stdout+stderr per JobId; drained by MonitorProgress, read on failure so rc!=0 gets actual FFmpeg error text into Logs.
        self.RecentOutput = {}

    # directive: transcodejob-uses-path | # see path.S5
    def TranscodeVideo(self, JobId: int, TranscodeCommand: str,
                      ProgressCallback: Optional[Callable] = None, TotalFramesFromMediaFile: int = 0,
                      ActiveJobId: int = None, DatabaseManager = None,
                      MaxCpuThreads: int = None) -> Dict[str, Any]:
        """Execute transcoding command with real-time progress tracking.

        Args:
            JobId: ID of the transcoding job
            TranscodeCommand: Complete FFmpeg command string
            ProgressCallback: Optional callback function for progress updates
            TotalFramesFromMediaFile: Total frames from MediaFiles table (preferred over FFmpeg extraction)

        Returns:
            Dictionary with success status, output file path, duration, and error details
        """
        try:
            LoggingService.LogFunctionEntry("TranscodeVideo", "VideoTranscodingService", JobId)
            LoggingService.LogInfo(f"EXECUTING COMMAND: {TranscodeCommand}", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"Command execution mode: shell=True (PID will be shell process)", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"Command type: {type(TranscodeCommand)}", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"Command length: {len(TranscodeCommand) if isinstance(TranscodeCommand, str) else 'N/A'}", "VideoTranscodingService", "TranscodeVideo")

            StartTime = datetime.now(timezone.utc)

            # Execute transcoding command
            LoggingService.LogInfo(f"Working directory: {os.getcwd()}", "VideoTranscodingService", "TranscodeVideo")

            LoggingService.LogInfo(f"About to execute subprocess.Popen with shell=True", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"subprocess.Popen arguments: command={TranscodeCommand}, shell=True, stdout=PIPE, stderr=STDOUT", "VideoTranscodingService", "TranscodeVideo")

            # directive: transcode-flow-canonical
            if ActiveJobId and DatabaseManager:
                DatabaseManager.SetJobPhase(ActiveJobId, JobPhase.Encoding)

            Process = subprocess.Popen(
                TranscodeCommand,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            LoggingService.LogInfo(f"subprocess.Popen completed successfully", "VideoTranscodingService", "TranscodeVideo")

            LoggingService.LogInfo(f"Process started with PID: {Process.pid}", "VideoTranscodingService", "TranscodeVideo")

            # Record FFmpeg subprocess PID into ActiveJobs.FFmpegPid (shell-pid on
            # Windows shell=True, which is the parent of ffmpeg.exe -- the kill
            # path uses taskkill /T to terminate the whole tree). This is the
            # correct kill target for stuck-job cleanup. See
            # stuck-job-detection.feature.md criterion 6.
            if ActiveJobId and DatabaseManager:
                try:
                    DatabaseManager.SetActiveJobFFmpegPid(ActiveJobId, Process.pid)
                except Exception as PidEx:
                    LoggingService.LogException(
                        f"Failed to record FFmpegPid={Process.pid} for ActiveJobId={ActiveJobId}",
                        PidEx, "VideoTranscodingService", "TranscodeVideo"
                    )

            # Set CPU affinity using topology-based core selection (skip in Docker — cpuset handles pinning)
            FFmpegPID = None
            if not os.path.exists('/.dockerenv'):
                if MaxCpuThreads:
                    # Per-worker config: use directly (admin already accounted for reserves)
                    CoreCount = MaxCpuThreads
                else:
                    # Global fallback: read from SystemSettings, subtract 2 for system headroom
                    CoreCount = max(1, self.GetMaxCpuThreads() - 2)

                try:
                    from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                    CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()

                    AffinityResult = CpuAffinityServiceInstance.SetFFmpegProcessAffinity(
                        ShellProcessPID=Process.pid,
                        CoreCount=CoreCount,
                        JobId=JobId,
                        JobType="Transcode",
                        ServiceName="VideoTranscodingService"
                    )

                    if AffinityResult["Success"]:
                        FFmpegPID = AffinityResult["FFmpegPID"]
                        if AffinityResult.get("ErrorMessage"):
                            LoggingService.LogWarning(f"CPU affinity set but with warning: {AffinityResult['ErrorMessage']}",
                                                     "VideoTranscodingService", "TranscodeVideo")
                    else:
                        LoggingService.LogWarning(f"Failed to set CPU affinity: {AffinityResult.get('ErrorMessage', 'Unknown error')}",
                                                 "VideoTranscodingService", "TranscodeVideo")
                except Exception as AffinityError:
                    LoggingService.LogWarning(f"Failed to set CPU affinity: {AffinityError}", "VideoTranscodingService", "TranscodeVideo")

            # Update ActiveJob with FFmpeg PID if provided (use FFmpeg PID if available, otherwise shell PID)
            ProcessPIDToUse = FFmpegPID if FFmpegPID else Process.pid
            if ActiveJobId and DatabaseManager:
                DatabaseManager.UpdateActiveJobProcessId(ActiveJobId, ProcessPIDToUse)
                LoggingService.LogInfo(f"Updated ActiveJob {ActiveJobId} with PID {ProcessPIDToUse} (FFmpeg: {FFmpegPID is not None})",
                                      "VideoTranscodingService", "TranscodeVideo")

            # Store process reference
            self.ActiveProcesses[JobId] = Process

            # Set TotalFrames from MediaFile if provided
            if TotalFramesFromMediaFile > 0:
                self._TotalFrameCount = TotalFramesFromMediaFile
                LoggingService.LogInfo(f"Using TotalFrames from MediaFile: {TotalFramesFromMediaFile} frames",
                                     "VideoTranscodingService", "TranscodeVideo")
            else:
                LoggingService.LogWarning(f"TotalFramesFromMediaFile is 0 or not provided for JobId {JobId}. " +
                                        "Progress percentage calculation will be limited. Will attempt to extract from FFmpeg output.",
                                        "VideoTranscodingService", "TranscodeVideo")
                self._TotalFrameCount = 0

            # Start progress monitoring thread
            if ProgressCallback:
                ProgressThread = threading.Thread(
                    target=self.MonitorProgress,
                    args=(JobId, Process, ProgressCallback),
                    daemon=True
                )
                ProgressThread.start()
                self.ProcessThreads[JobId] = ProgressThread

            # Wait for process to complete
            LoggingService.LogInfo(f"Waiting for process to complete...", "VideoTranscodingService", "TranscodeVideo")
            ReturnCode = Process.wait()
            EndTime = datetime.now(timezone.utc)
            Duration = (EndTime - StartTime).total_seconds()

            # directive: transcode-flow-canonical
            if ActiveJobId and DatabaseManager:
                DatabaseManager.SetJobPhase(ActiveJobId, JobPhase.PostEncode)

            LoggingService.LogInfo(f"Process completed with return code: {ReturnCode}", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"Duration: {Duration} seconds", "VideoTranscodingService", "TranscodeVideo")

            # Capture any error output if the process failed. MonitorProgress tees into self.RecentOutput; wait up to 2s for that thread to drain post-exit, then fall back to a direct pipe read (fast-fail case where the thread never ran).
            FFmpegTail = ""
            if ReturnCode != 0:
                MonitorThread = self.ProcessThreads.get(JobId)
                if MonitorThread is not None:
                    MonitorThread.join(timeout=2.0)
                Tail = self.RecentOutput.get(JobId)
                if not Tail:
                    try:
                        Raw = Process.stdout.read() if Process.stdout else ''
                        if Raw:
                            Tail = deque([L.strip() for L in Raw.split('\n') if L.strip()][-60:], maxlen=60)
                            self.RecentOutput[JobId] = Tail
                    except (ValueError, OSError):
                        pass
                if Tail:
                    FFmpegTail = "\n".join(Tail)[-4096:]
                    LoggingService.LogError(
                        f"FFmpeg failed rc={ReturnCode}. Output tail (last {len(Tail)} lines):\n{FFmpegTail}",
                        "VideoTranscodingService", "TranscodeVideo"
                    )
                else:
                    LoggingService.LogError(
                        f"FFmpeg failed rc={ReturnCode}. No output captured (pipe drained empty).",
                        "VideoTranscodingService", "TranscodeVideo"
                    )

            # Clean up process references
            if JobId in self.ActiveProcesses:
                del self.ActiveProcesses[JobId]
            if JobId in self.ProcessThreads:
                del self.ProcessThreads[JobId]
            # Drop the rolling-tail buffer for this JobId; tail already logged/embedded above on failure path.
            if JobId in self.RecentOutput:
                del self.RecentOutput[JobId]

            # Release job from CpuAffinityService (with cooling wait enabled)
            try:
                from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                CpuAffinityServiceInstance.ReleaseJob(JobId, WaitForCooling=True)
            except Exception as ReleaseError:
                LoggingService.LogWarning(f"Failed to release job from CpuAffinityService: {ReleaseError}", "VideoTranscodingService", "TranscodeVideo")

            # Check if transcoding was successful
            if ReturnCode == 0:
                LoggingService.LogInfo(f"Transcoding completed successfully for job {JobId}",
                                     "VideoTranscodingService", "TranscodeVideo")

                # Extract output file path from command and calculate file size
                OutputFilePath = self.ExtractOutputPathFromCommand(TranscodeCommand)
                NewSizeBytes = 0

                if OutputFilePath and LocalExists(OutputFilePath):
                    NewSizeBytes = LocalGetSize(OutputFilePath)
                    LoggingService.LogInfo(f"Captured file size immediately after transcode: {NewSizeBytes} bytes",
                                         "VideoTranscodingService", "TranscodeVideo")
                else:
                    # Add retry logic for file system flushing delays
                    import time
                    LoggingService.LogInfo(f"Output file not found immediately, retrying for file system flush: {OutputFilePath}",
                                         "VideoTranscodingService", "TranscodeVideo")

                    for attempt in range(3):  # Try 3 times
                        time.sleep(0.1)  # Wait 100ms between attempts
                        if OutputFilePath and LocalExists(OutputFilePath):
                            NewSizeBytes = LocalGetSize(OutputFilePath)
                            LoggingService.LogInfo(f"Captured file size after retry {attempt + 1}: {NewSizeBytes} bytes",
                                                 "VideoTranscodingService", "TranscodeVideo")
                            break
                    else:
                        LoggingService.LogWarning(f"Output file still not found after 3 retries: {OutputFilePath}",
                                               "VideoTranscodingService", "TranscodeVideo")

                return {
                    "Success": True,
                    "OutputFilePath": OutputFilePath,
                    "NewSizeBytes": NewSizeBytes,
                    "StartTime": ToUtcIsoZ(StartTime),
                    "EndTime": ToUtcIsoZ(EndTime),
                    "Duration": Duration,
                    "ErrorMessage": None
                }
            else:
                ErrorMessage = f"Transcoding failed with return code {ReturnCode}"
                if FFmpegTail:
                    ErrorMessage = f"{ErrorMessage}\nFFmpeg output tail:\n{FFmpegTail}"
                LoggingService.LogError(f"Transcoding failed for job {JobId}: {ErrorMessage}",
                                      "VideoTranscodingService", "TranscodeVideo")

                return {
                    "Success": False,
                    "OutputFilePath": None,
                    "StartTime": ToUtcIsoZ(StartTime),
                    "EndTime": ToUtcIsoZ(EndTime),
                    "Duration": Duration,
                    "ErrorMessage": ErrorMessage
                }

        except Exception as e:
            ErrorMessage = f"Exception during transcoding: {str(e)}"
            LoggingService.LogException(ErrorMessage, e, "VideoTranscodingService", "TranscodeVideo")

            # Release job from CpuAffinityService (with cooling wait enabled)
            try:
                from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                CpuAffinityServiceInstance.ReleaseJob(JobId, WaitForCooling=True)
            except Exception as ReleaseError:
                LoggingService.LogWarning(f"Failed to release job from CpuAffinityService: {ReleaseError}", "VideoTranscodingService", "TranscodeVideo")

            # Clean up process references
            if JobId in self.ActiveProcesses:
                del self.ActiveProcesses[JobId]
            if JobId in self.ProcessThreads:
                del self.ProcessThreads[JobId]

            return {
                "Success": False,
                "OutputFilePath": None,
                "StartTime": ToUtcIsoZ(datetime.now(timezone.utc)),
                "EndTime": ToUtcIsoZ(datetime.now(timezone.utc)),
                "Duration": 0,
                "ErrorMessage": ErrorMessage
            }

    def StopTranscoding(self, JobId: int) -> Dict[str, Any]:
        """Stop transcoding for a specific job."""
        try:
            LoggingService.LogFunctionEntry("StopTranscoding", "VideoTranscodingService", JobId)

            if JobId in self.ActiveProcesses:
                Process = self.ActiveProcesses[JobId]
                Process.terminate()

                # Wait for process to terminate
                try:
                    Process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    Process.kill()
                    Process.wait()

                # Clean up references
                del self.ActiveProcesses[JobId]
                if JobId in self.ProcessThreads:
                    del self.ProcessThreads[JobId]

                LoggingService.LogInfo(f"Stopped transcoding for job {JobId}",
                                     "VideoTranscodingService", "StopTranscoding")

                return {
                    "Success": True,
                    "Message": f"Stopped transcoding for job {JobId}"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"No active transcoding process found for job {JobId}"
                }

        except Exception as e:
            ErrorMessage = f"Exception stopping transcoding: {str(e)}"
            LoggingService.LogException(ErrorMessage, e, "VideoTranscodingService", "StopTranscoding")
            return {
                "Success": False,
                "ErrorMessage": ErrorMessage
            }

    def GetActiveJobs(self) -> list:
        """Get list of currently active transcoding job IDs."""
        return list(self.ActiveProcesses.keys())


    def MonitorProgress(self, JobId: int, Process: subprocess.Popen, ProgressCallback: Callable):
        """Monitor transcoding progress and call progress callback."""
        Tail = self.RecentOutput.setdefault(JobId, deque(maxlen=60))
        try:
            while Process.poll() is None:
                # Read output line by line
                Line = Process.stdout.readline()
                if Line:
                    Stripped = Line.strip()
                    if Stripped:
                        Tail.append(Stripped)
                    ProgressData = self.ParseProgressLine(Stripped)
                    if ProgressData:
                        ProgressCallback(ProgressData)

                time.sleep(0.1)  # Small delay to prevent excessive CPU usage

            # Drain kernel pipe buffer after process exit (fast-fail case: loop above never entered).
            try:
                RemainingOutput = Process.stdout.read()
                if RemainingOutput:
                    Lines = RemainingOutput.split('\n')
                    for Line in Lines:
                        Stripped = Line.strip()
                        if Stripped:
                            Tail.append(Stripped)
                            ProgressData = self.ParseProgressLine(Stripped)
                            if ProgressData:
                                ProgressCallback(ProgressData)
            except (ValueError, OSError):
                # Process stdout is closed, ignore
                pass

        except Exception as e:
            LoggingService.LogException("Exception monitoring progress", e, "VideoTranscodingService", "MonitorProgress")

    def ParseProgressLine(self, Line: str) -> Optional[Dict[str, Any]]:
        """Parse FFmpeg progress line to extract progress information."""
        try:
            # FFmpeg progress format: frame=1234 fps=25.0 q=28.0 size=1024kB time=00:01:23.45 bitrate=1000.0kbits/s speed=1.0x

            ProgressData = {}

            # First, check if this line contains the total frame count from FFmpeg metadata
            # Only use FFmpeg extraction if we don't already have TotalFrames from MediaFile
            if "NUMBER_OF_FRAMES" in Line and not hasattr(self, '_TotalFrameCount'):
                FrameCountMatch = re.search(r'NUMBER_OF_FRAMES[^:]*:\s*(\d+)', Line)
                if FrameCountMatch:
                    TotalFrames = int(FrameCountMatch.group(1))
                    # Store the total frame count for use in progress calculation
                    self._TotalFrameCount = TotalFrames
                    LoggingService.LogInfo(f"Extracted total frame count from FFmpeg metadata: {TotalFrames} frames",
                                         "VideoTranscodingService", "ParseProgressLine")
                    return None  # This is metadata, not a progress line

            # Extract frame number
            FrameMatch = re.search(r'frame=\s*(\d+)', Line)
            if FrameMatch:
                CurrentFrame = int(FrameMatch.group(1))

                # Ignore frame 0 or null values to prevent UI flashing
                if CurrentFrame <= 0:
                    return None  # Skip this progress update

                ProgressData['CurrentFrame'] = CurrentFrame

            # Extract FPS
            FPSMatch = re.search(r'fps=\s*([\d.]+)', Line)
            if FPSMatch:
                ProgressData['CurrentFPS'] = float(FPSMatch.group(1))

            # Extract bitrate
            BitrateMatch = re.search(r'bitrate=([\d.]+)kbits/s', Line)
            if BitrateMatch:
                ProgressData['CurrentBitrate'] = float(BitrateMatch.group(1))

            # Extract time
            TimeMatch = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', Line)
            if TimeMatch:
                ProgressData['CurrentTime'] = TimeMatch.group(1)

            # Extract speed
            SpeedMatch = re.search(r'speed=([\d.]+)x', Line)
            if SpeedMatch:
                ProgressData['CurrentSpeed'] = f"{SpeedMatch.group(1)}x"

            # Only proceed if we have valid frame data
            if 'CurrentFrame' not in ProgressData:
                return None  # No valid frame data, skip this update

            # Calculate progress percentage if we have TotalFrames available
            if 'CurrentFrame' in ProgressData:
                CurrentFrame = ProgressData['CurrentFrame']
                TotalFrames = getattr(self, '_TotalFrameCount', 0)

                if TotalFrames > 0 and CurrentFrame > 0:
                    # Calculate progress percentage (cap at 95% to avoid showing 100% before completion)
                    ProgressPercent = min((CurrentFrame / TotalFrames) * 100, 95.0)
                    ProgressData['ProgressPercent'] = ProgressPercent
                    ProgressData['TotalFrames'] = TotalFrames

                    # Calculate ETA if we have FPS data
                    if 'CurrentFPS' in ProgressData and ProgressData['CurrentFPS'] > 0:
                        RemainingFrames = TotalFrames - CurrentFrame
                        EtaSeconds = RemainingFrames / ProgressData['CurrentFPS']
                        ProgressData['ETA'] = self.FormatTime(round(EtaSeconds))
                    else:
                        ProgressData['ETA'] = "Calculating..."
                else:
                    # No TotalFrames available, set defaults
                    ProgressData['TotalFrames'] = TotalFrames
                    ProgressData['ProgressPercent'] = 0
                    ProgressData['ETA'] = "Calculating..."

            # Set current phase
            ProgressData['CurrentPhase'] = 'Transcoding'

            # Set default values for missing fields
            ProgressData.setdefault('TotalFrames', 0)
            ProgressData.setdefault('ETA', '')
            ProgressData.setdefault('AverageFPS', ProgressData.get('CurrentFPS', 0))

            return ProgressData if ProgressData else None

        except Exception as e:
            # Don't log parsing errors as they're frequent and not critical
            return None
    def ExtractOutputPathFromCommand(self, TranscodeCommand: str) -> Optional[str]:
        """Extract the output file path from the FFmpeg command string."""
        try:
            # FFmpeg commands typically end with the output file path
            # Look for the last quoted string in the command
            import re

            # Find all quoted strings in the command
            QuotedStrings = re.findall(r'"([^"]*)"', TranscodeCommand)

            if QuotedStrings:
                # The last quoted string should be the output file
                OutputPath = QuotedStrings[-1]
                LoggingService.LogInfo(f"Extracted output path from command: {OutputPath}",
                                     "VideoTranscodingService", "ExtractOutputPathFromCommand")
                return OutputPath
            else:
                LoggingService.LogWarning("No quoted strings found in command, cannot extract output path",
                                       "VideoTranscodingService", "ExtractOutputPathFromCommand")
                return None

        except Exception as e:
            LoggingService.LogException("Exception extracting output path from command", e,
                                      "VideoTranscodingService", "ExtractOutputPathFromCommand")
            return None

    def GetMaxCpuThreads(self) -> int:
        """Get maximum CPU threads from system settings.

        Raises:
            ValueError: If setting is missing, invalid, or out of range (1-32)
            Exception: If database access fails
        """
        from Repositories.DatabaseManager import DatabaseManager
        DatabaseManagerInstance = DatabaseManager()

        # Get CPU thread limit from system settings
        MaxCpuThreads = DatabaseManagerInstance.GetSystemSetting('MaxCpuThreads')
        if not MaxCpuThreads:
            raise ValueError("MaxCpuThreads setting is missing from SystemSettings. Please add it to the database.")

        if not MaxCpuThreads.isdigit():
            raise ValueError(f"MaxCpuThreads setting has invalid value: '{MaxCpuThreads}'. Must be a number between 1-32.")

        ThreadCount = int(MaxCpuThreads)
        # Validate thread count (1-32 for safety)
        if not (1 <= ThreadCount <= 32):
            raise ValueError(f"MaxCpuThreads setting value {ThreadCount} is out of valid range (1-32).")

        return ThreadCount

    def FormatTime(self, Seconds: int) -> str:
        """Format seconds into HH:MM:SS format."""
        try:
            Hours = Seconds // 3600
            Minutes = (Seconds % 3600) // 60
            Seconds = Seconds % 60
            return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d}"
        except Exception:
            return "00:00:00"
