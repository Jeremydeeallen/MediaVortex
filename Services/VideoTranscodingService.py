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
                      ProgressCallback: Optional[Callable] = None) -> Dict[str, Any]:
        """Execute transcoding command with real-time progress tracking.
        
        Args:
            JobId: ID of the transcoding job
            TranscodeCommand: Complete FFmpeg command string
            ProgressCallback: Optional callback function for progress updates
            
        Returns:
            Dictionary with success status, output file path, duration, and error details
        """
        try:
            LoggingService.LogFunctionEntry("TranscodeVideo", "VideoTranscodingService", JobId)
            
            StartTime = datetime.now()
            
            # Parse command to extract input and output paths
            CommandParts = self._ParseCommand(TranscodeCommand)
            if not CommandParts:
                return {
                    "Success": False,
                    "ErrorMessage": "Failed to parse transcoding command"
                }
            
            InputPath = CommandParts.get('InputPath')
            OutputPath = CommandParts.get('OutputPath')
            
            # Validate input file exists
            if not os.path.exists(InputPath):
                return {
                    "Success": False,
                    "ErrorMessage": f"Input file not found: {InputPath}"
                }
            
            # Create output directory if it doesn't exist
            OutputDir = os.path.dirname(OutputPath)
            if not os.path.exists(OutputDir):
                os.makedirs(OutputDir, exist_ok=True)
            
            # Execute transcoding command
            Process = subprocess.Popen(
                TranscodeCommand,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Store process reference
            self.ActiveProcesses[JobId] = Process
            
            # Start progress monitoring thread
            if ProgressCallback:
                ProgressThread = threading.Thread(
                    target=self._MonitorProgress,
                    args=(JobId, Process, ProgressCallback),
                    daemon=True
                )
                ProgressThread.start()
                self.ProcessThreads[JobId] = ProgressThread
            
            # Wait for process to complete
            ReturnCode = Process.wait()
            EndTime = datetime.now()
            Duration = (EndTime - StartTime).total_seconds()
            
            # Clean up process references
            if JobId in self.ActiveProcesses:
                del self.ActiveProcesses[JobId]
            if JobId in self.ProcessThreads:
                del self.ProcessThreads[JobId]
            
            # Check if transcoding was successful
            if ReturnCode == 0 and os.path.exists(OutputPath):
                LoggingService.LogInfo(f"Transcoding completed successfully for job {JobId}", 
                                     "VideoTranscodingService", "TranscodeVideo")
                
                return {
                    "Success": True,
                    "OutputFilePath": OutputPath,
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
    
    def _ParseCommand(self, TranscodeCommand: str) -> Optional[Dict[str, str]]:
        """Parse FFmpeg command to extract input and output paths."""
        try:
            # Remove quotes and split command
            CleanCommand = TranscodeCommand.replace('"', '')
            Parts = CleanCommand.split()
            
            InputPath = None
            OutputPath = None
            
            # Find input path (after -i)
            for i, part in enumerate(Parts):
                if part == '-i' and i + 1 < len(Parts):
                    InputPath = Parts[i + 1]
                    break
            
            # Find output path (last argument before -y)
            for i in range(len(Parts) - 1, -1, -1):
                if Parts[i] != '-y' and not Parts[i].startswith('-'):
                    OutputPath = Parts[i]
                    break
            
            if InputPath and OutputPath:
                return {
                    'InputPath': InputPath,
                    'OutputPath': OutputPath
                }
            else:
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception parsing command", e, "VideoTranscodingService", "_ParseCommand")
            return None
    
    def _MonitorProgress(self, JobId: int, Process: subprocess.Popen, ProgressCallback: Callable):
        """Monitor transcoding progress and call progress callback."""
        try:
            while Process.poll() is None:
                # Read output line by line
                Line = Process.stdout.readline()
                if Line:
                    ProgressData = self._ParseProgressLine(Line.strip())
                    if ProgressData:
                        ProgressCallback(ProgressData)
                
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            
            # Read any remaining output
            RemainingOutput = Process.stdout.read()
            if RemainingOutput:
                Lines = RemainingOutput.split('\n')
                for Line in Lines:
                    if Line.strip():
                        ProgressData = self._ParseProgressLine(Line.strip())
                        if ProgressData:
                            ProgressCallback(ProgressData)
            
        except Exception as e:
            LoggingService.LogException("Exception monitoring progress", e, "VideoTranscodingService", "_MonitorProgress")
    
    def _ParseProgressLine(self, Line: str) -> Optional[Dict[str, Any]]:
        """Parse FFmpeg progress line to extract progress information."""
        try:
            # FFmpeg progress format: frame=1234 fps=25.0 q=28.0 size=1024kB time=00:01:23.45 bitrate=1000.0kbits/s speed=1.0x
            
            ProgressData = {}
            
            # Extract frame number
            FrameMatch = re.search(r'frame=(\d+)', Line)
            if FrameMatch:
                ProgressData['CurrentFrame'] = int(FrameMatch.group(1))
            
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
            
            # Calculate progress percentage if we have frame and total frames
            if 'CurrentFrame' in ProgressData:
                # This is a simplified calculation - in practice, you'd need total frames
                ProgressData['ProgressPercent'] = min(ProgressData['CurrentFrame'] / 10000 * 100, 100)
            
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
