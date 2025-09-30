import subprocess
import re
import os
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from Services.LoggingService import LoggingService


class VideoTranscodingService:
    """Tool-agnostic video transcoding service that executes transcoding commands with progress tracking."""
    
    def __init__(self):
        self.ActiveProcesses = {}
        self.ProcessThreads = {}
    
    def TranscodeVideo(self, JobId: int, TranscodeCommand: str, 
                      ProgressCallback: Optional[Callable] = None, TotalFramesFromMediaFile: int = 0) -> Dict[str, Any]:
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
            
            StartTime = datetime.now()
            
            # Execute transcoding command
            LoggingService.LogInfo(f"Working directory: {os.getcwd()}", "VideoTranscodingService", "TranscodeVideo")
            
            Process = subprocess.Popen(
                TranscodeCommand,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            LoggingService.LogInfo(f"Process started with PID: {Process.pid}", "VideoTranscodingService", "TranscodeVideo")
            
            # Store process reference
            self.ActiveProcesses[JobId] = Process
            
            # Set TotalFrames from MediaFile if provided
            if TotalFramesFromMediaFile > 0:
                self._TotalFrameCount = TotalFramesFromMediaFile
                LoggingService.LogInfo(f"Using TotalFrames from MediaFile: {TotalFramesFromMediaFile} frames", 
                                     "VideoTranscodingService", "TranscodeVideo")
            
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
            EndTime = datetime.now()
            Duration = (EndTime - StartTime).total_seconds()
            
            LoggingService.LogInfo(f"Process completed with return code: {ReturnCode}", "VideoTranscodingService", "TranscodeVideo")
            LoggingService.LogInfo(f"Duration: {Duration} seconds", "VideoTranscodingService", "TranscodeVideo")
            
            # Capture any error output if the process failed
            if ReturnCode != 0:
                try:
                    # Read any remaining output
                    Output, ErrorOutput = Process.communicate()
                    if Output:
                        LoggingService.LogError(f"FFmpeg stdout: {Output}", "VideoTranscodingService", "TranscodeVideo")
                    if ErrorOutput:
                        LoggingService.LogError(f"FFmpeg stderr: {ErrorOutput}", "VideoTranscodingService", "TranscodeVideo")
                except Exception as e:
                    LoggingService.LogException("Exception reading FFmpeg output", e, "VideoTranscodingService", "TranscodeVideo")
            
            # Clean up process references
            if JobId in self.ActiveProcesses:
                del self.ActiveProcesses[JobId]
            if JobId in self.ProcessThreads:
                del self.ProcessThreads[JobId]
            
            # Check if transcoding was successful
            if ReturnCode == 0:
                LoggingService.LogInfo(f"Transcoding completed successfully for job {JobId}", 
                                     "VideoTranscodingService", "TranscodeVideo")
                
                return {
                    "Success": True,
                    "OutputFilePath": "Success",  # We don't need to track the actual path
                    "StartTime": StartTime.isoformat(),
                    "EndTime": EndTime.isoformat(),
                    "Duration": Duration,
                    "ErrorMessage": None
                }
            else:
                ErrorMessage = f"Transcoding failed with return code {ReturnCode}"
                LoggingService.LogError(f"Transcoding failed for job {JobId}: {ErrorMessage}", 
                                      "VideoTranscodingService", "TranscodeVideo")
                
                return {
                    "Success": False,
                    "OutputFilePath": None,
                    "StartTime": StartTime.isoformat(),
                    "EndTime": EndTime.isoformat(),
                    "Duration": Duration,
                    "ErrorMessage": ErrorMessage
                }
                
        except Exception as e:
            ErrorMessage = f"Exception during transcoding: {str(e)}"
            LoggingService.LogException(ErrorMessage, e, "VideoTranscodingService", "TranscodeVideo")
            
            # Clean up process references
            if JobId in self.ActiveProcesses:
                del self.ActiveProcesses[JobId]
            if JobId in self.ProcessThreads:
                del self.ProcessThreads[JobId]
            
            return {
                "Success": False,
                "OutputFilePath": None,
                "StartTime": datetime.now().isoformat(),
                "EndTime": datetime.now().isoformat(),
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
        try:
            while Process.poll() is None:
                # Read output line by line
                Line = Process.stdout.readline()
                if Line:
                    ProgressData = self.ParseProgressLine(Line.strip())
                    if ProgressData:
                        ProgressCallback(ProgressData)
                
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            
            # Read any remaining output (only if process is still running)
            try:
                if Process.poll() is None:
                    RemainingOutput = Process.stdout.read()
                    if RemainingOutput:
                        Lines = RemainingOutput.split('\n')
                        for Line in Lines:
                            if Line.strip():
                                ProgressData = self.ParseProgressLine(Line.strip())
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
            FPSMatch = re.search(r'fps=([\d.]+)', Line)
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
            
            # Don't calculate progress percentage here - let the database/frontend handle it
            # Just ensure we have the basic frame data
            if 'CurrentFrame' in ProgressData:
                # Set default values for fields that will be calculated elsewhere
                ProgressData['TotalFrames'] = 0  # Will be populated from MediaFiles table
                ProgressData['ProgressPercent'] = 0  # Will be calculated in database/frontend
                ProgressData['ETA'] = "Calculating..."  # Will be calculated in database/frontend
            
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
