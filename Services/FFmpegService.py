import os
import subprocess
import shutil
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService


class FFmpegService:
    """Core FFmpeg service for executing FFmpeg and FFprobe commands."""
    
    # Static cache for paths to avoid repeated lookups
    _cached_ffmpeg_path = None
    _cached_ffprobe_path = None
    _logged_initialization = False
    
    def __init__(self):
        # Use cached paths if available, otherwise find them
        if FFmpegService._cached_ffmpeg_path is None:
            FFmpegService._cached_ffmpeg_path = self.FindFFmpegPath()
        if FFmpegService._cached_ffprobe_path is None:
            FFmpegService._cached_ffprobe_path = self.FindFFprobePath()
            
        self.FFmpegPath = FFmpegService._cached_ffmpeg_path
        self.FFprobePath = FFmpegService._cached_ffprobe_path
        
        # Only log once when first instance is created
        if not FFmpegService._logged_initialization:
            if not self.FFmpegPath:
                LoggingService.LogWarning("FFmpeg not found. Video processing will not be available.", '__init__', 'FFmpegService')
            else:
                LoggingService.LogInfo(f"FFmpeg found at: {self.FFmpegPath}", '__init__', 'FFmpegService')
                
            if not self.FFprobePath:
                LoggingService.LogWarning("FFprobe not found. Media analysis will not be available.", '__init__', 'FFmpegService')
            else:
                LoggingService.LogInfo(f"FFprobe found at: {self.FFprobePath}", '__init__', 'FFmpegService')
            
            FFmpegService._logged_initialization = True
    
    def FindFFmpegPath(self) -> Optional[str]:
        """Find FFmpeg executable path."""
        try:
            # Check if ffmpeg is in PATH
            FFmpegPath = shutil.which('ffmpeg')
            if FFmpegPath:
                # Only log once per class, not per instance
                if not hasattr(FFmpegService, '_ffmpeg_path_logged'):
                    LoggingService.LogInfo(f"Found FFmpeg in PATH: {FFmpegPath}", 'FindFFmpegPath', 'FFmpegService')
                    FFmpegService._ffmpeg_path_logged = True
                return FFmpegPath
            
            # Check common installation paths
            CommonPaths = [
                'C:\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/ffmpeg/bin/ffmpeg'
            ]
            
            for Path in CommonPaths:
                if os.path.exists(Path):
                    LoggingService.LogInfo(f"Found FFmpeg at: {Path}", 'FindFFmpegPath', 'FFmpegService')
                    return Path
            
            LoggingService.LogWarning("FFmpeg not found in common paths", 'FindFFmpegPath', 'FFmpegService')
            return None
            
        except Exception as e:
            LoggingService.LogException("Error finding FFmpeg path", e, 'FindFFmpegPath', 'FFmpegService')
            return None
    
    def FindFFprobePath(self) -> Optional[str]:
        """Find FFprobe executable path."""
        try:
            # Check if ffprobe is in PATH
            FFprobePath = shutil.which('ffprobe')
            if FFprobePath:
                # Only log once per class, not per instance
                if not hasattr(FFmpegService, '_ffprobe_path_logged'):
                    LoggingService.LogInfo(f"Found FFprobe in PATH: {FFprobePath}", 'FindFFprobePath', 'FFmpegService')
                    FFmpegService._ffprobe_path_logged = True
                return FFprobePath
            
            # Check common installation paths
            CommonPaths = [
                'C:\\ffmpeg\\bin\\ffprobe.exe',
                'C:\\Program Files\\ffmpeg\\bin\\ffprobe.exe',
                'C:\\Program Files (x86)\\ffmpeg\\bin\\ffprobe.exe',
                '/usr/bin/ffprobe',
                '/usr/local/bin/ffprobe',
                '/opt/ffmpeg/bin/ffprobe'
            ]
            
            for Path in CommonPaths:
                if os.path.exists(Path):
                    LoggingService.LogInfo(f"Found FFprobe at: {Path}", 'FindFFprobePath', 'FFmpegService')
                    return Path
            
            LoggingService.LogWarning("FFprobe not found in common paths", 'FindFFprobePath', 'FFmpegService')
            return None
            
        except Exception as e:
            LoggingService.LogException("Error finding FFprobe path", e, 'FindFFprobePath', 'FFmpegService')
            return None
    
    def ExecuteFFprobe(self, FilePath: str, Arguments: List[str] = None) -> Dict[str, Any]:
        """Execute FFprobe command and return results."""
        try:
            if not self.FFprobePath:
                return {
                    'Success': False,
                    'ErrorMessage': 'FFprobe not available',
                    'Output': '',
                    'Error': ''
                }
            
            if Arguments is None:
                Arguments = ['-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams']
            
            # Use the original file path with proper quoting for special characters
            # Use just 'ffprobe' since it's in PATH, and only quote the file path
            CommandString = 'ffprobe'
            for Arg in Arguments:
                CommandString += f' {Arg}'
            CommandString += f' "{FilePath}"'
            
            LoggingService.LogInfo(f"Executing FFprobe command: {CommandString}", 'ExecuteFFprobe', 'FFmpegService')
            
            Result = subprocess.run(
                CommandString,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace',
                shell=True  # Use shell=True with properly quoted command
            )
            
            ResultDict = {
                'Success': Result.returncode == 0,
                'ReturnCode': Result.returncode,
                'Output': Result.stdout,
                'Error': Result.stderr,
                'Command': CommandString
            }
            
            if not ResultDict['Success']:
                ResultDict['ErrorMessage'] = f"FFprobe failed: ReturnCode={Result.returncode}, Error={Result.stderr}"
                LoggingService.LogError(f"FFprobe failed for {FilePath}: ReturnCode={Result.returncode}, Error={Result.stderr}", 'FFmpegService', 'ExecuteFFprobe')
            else:
                LoggingService.LogInfo(f"FFprobe succeeded for {FilePath}", 'ExecuteFFprobe', 'FFmpegService')
            
            return ResultDict
            
        except subprocess.TimeoutExpired:
            ErrorMessage = f"FFprobe timeout for file: {FilePath}"
            LoggingService.LogError(f"{ErrorMessage}", 'ExecuteFFprobe', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': 'Timeout',
                'Command': CommandString
            }
        except Exception as e:
            ErrorMessage = f"FFprobe execution error: {str(e)}"
            LoggingService.LogError(f"{ErrorMessage}", 'ExecuteFFprobe', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': str(e),
                'Command': CommandString
            }
    
    def ExecuteFFmpegCommand(self, Arguments: List[str], ProgressCallback=None) -> Dict[str, Any]:
        """Execute FFmpeg command with optional real-time progress monitoring."""
        try:
            if not self.FFmpegPath:
                return {
                    'Success': False,
                    'ErrorMessage': 'FFmpeg not available',
                    'Output': '',
                    'Error': ''
                }
            
            # Add progress reporting if callback is provided
            if ProgressCallback:
                # Insert -progress pipe:1 before the output file
                Command = [self.FFmpegPath] + Arguments[:-1] + ['-progress', 'pipe:1'] + Arguments[-1:]
            else:
                Command = [self.FFmpegPath] + Arguments
            
            LoggingService.LogInfo(f"Executing FFmpeg command: {' '.join(Command)}", 'ExecuteFFmpegCommand', 'FFmpegService')
            
            if ProgressCallback:
                return self._ExecuteFFmpegWithProgress(Command, ProgressCallback)
            else:
                Result = subprocess.run(
                    Command,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout for FFmpeg operations
                    encoding='utf-8',
                    errors='replace'
                )
                
                return {
                    'Success': Result.returncode == 0,
                    'Output': Result.stdout,
                    'Error': Result.stderr,
                    'ReturnCode': Result.returncode
                }
                
        except subprocess.TimeoutExpired as e:
            LoggingService.LogError(f"FFmpeg command timed out: {str(e)}", 'ExecuteFFmpegCommand', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f'FFmpeg command timed out: {str(e)}',
                'Output': '',
                'Error': str(e)
            }
        except Exception as e:
            LoggingService.LogException("Exception executing FFmpeg command", e, 'ExecuteFFmpegCommand', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f'Exception executing FFmpeg: {str(e)}',
                'Output': '',
                'Error': str(e)
            }

    def _ExecuteFFmpegWithProgress(self, Command: List[str], ProgressCallback) -> Dict[str, Any]:
        """Execute FFmpeg command with real-time progress monitoring."""
        import threading
        import time
        
        try:
            # Start FFmpeg process with progress output to stdout
            process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # Store all FFmpeg output for debugging
            AllOutput = []
            
            # Get input file duration first
            InputDuration = self.GetInputFileDuration(Command)
            
            # Thread to read progress updates
            ProgressData = {'frame': 0, 'fps': 0, 'bitrate': 0, 'time': 0, 'speed': 0, 'duration': InputDuration}
            
            def progress_reader():
                import time
                
                LoggingService.LogInfo("Progress reader thread started", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                lineCount = 0
                
                while True:
                    if process.poll() is not None:
                        LoggingService.LogInfo(f"Process finished, exiting progress reader. Total lines read: {lineCount}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                        break
                    
                    line = process.stdout.readline()
                    if not line:
                        LoggingService.LogDebug("No more lines from stdout, breaking", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                        break
                    
                    line = line.strip()
                    lineCount += 1
                    
                    # Store all output for debugging
                    AllOutput.append(f"STDOUT: {line}")
                    
                    # Log raw FFmpeg output for debugging
                    LoggingService.LogInfo(f"Raw FFmpeg line #{lineCount}: '{line}'", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Log each key-value pair for debugging
                        LoggingService.LogDebug(f"FFmpeg progress: {key} = {value}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                        
                        if key == 'frame':
                            ProgressData['frame'] = int(value) if value.isdigit() else 0
                        elif key == 'fps':
                            ProgressData['fps'] = float(value) if value.replace('.', '').isdigit() else 0
                        elif key == 'bitrate':
                            ProgressData['bitrate'] = value
                        elif key == 'time' or key == 'out_time':
                            ProgressData['time'] = value
                        elif key == 'speed':
                            ProgressData['speed'] = value
                        elif key == 'duration':
                            # Parse duration in seconds
                            try:
                                if ':' in value:
                                    # Format: HH:MM:SS.mmm
                                    parts = value.split(':')
                                    if len(parts) == 3:
                                        hours = int(parts[0])
                                        minutes = int(parts[1])
                                        seconds = float(parts[2])
                                        ProgressData['duration'] = hours * 3600 + minutes * 60 + seconds
                                else:
                                    # Format: seconds
                                    ProgressData['duration'] = float(value)
                            except:
                                ProgressData['duration'] = 0
                        
                        # Call progress callback immediately for debugging - no delays
                        if ProgressCallback:
                            # Include current FFmpeg output in progress data
                            ProgressDataWithOutput = ProgressData.copy()
                            ProgressDataWithOutput['FFmpegOutput'] = '\n'.join(AllOutput)
                            LoggingService.LogInfo(f"CALLING PROGRESS CALLBACK with data: {ProgressDataWithOutput}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                            ProgressCallback(ProgressDataWithOutput)
                            LoggingService.LogInfo("PROGRESS CALLBACK COMPLETED", '_ExecuteFFmpegWithProgress', 'FFmpegService')
            
            # Start progress reader thread
            ProgressThread = threading.Thread(target=progress_reader)
            ProgressThread.daemon = True
            ProgressThread.start()
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            # Add stderr to output collection
            if stderr:
                AllOutput.append(f"STDERR: {stderr}")
            
            # Wait for progress thread to finish
            ProgressThread.join(timeout=1)
            
            # Send final progress update
            if ProgressCallback:
                LoggingService.LogDebug(f"Sending final progress update: {ProgressData}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                FinalProgressData = ProgressData.copy()
                FinalProgressData['FFmpegOutput'] = '\n'.join(AllOutput)
                ProgressCallback(FinalProgressData)
            
            # Combine all output for debugging
            CombinedOutput = '\n'.join(AllOutput)
            
            return {
                'Success': process.returncode == 0,
                'Output': stdout,
                'Error': stderr,
                'ReturnCode': process.returncode,
                'AllOutput': CombinedOutput
            }
            
        except Exception as e:
            LoggingService.LogException("Exception executing FFmpeg with progress", e, '_ExecuteFFmpegWithProgress', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f'Exception executing FFmpeg with progress: {str(e)}',
                'Output': '',
                'Error': str(e)
            }
    
    def GetInputFileDuration(self, Command: List[str]) -> float:
        """Get the duration of the input file in seconds."""
        try:
            # Find the input file (usually after -i)
            InputFile = None
            for i, arg in enumerate(Command):
                if arg == '-i' and i + 1 < len(Command):
                    InputFile = Command[i + 1]
                    break
            
            if not InputFile:
                LoggingService.LogWarning("No input file found in FFmpeg command", 'GetInputFileDuration', 'FFmpegService')
                return 0.0
            
            # Use ffprobe to get duration
            ProbeCommand = [
                self.FFprobePath,
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                InputFile
            ]
            
            Result = subprocess.run(ProbeCommand, capture_output=True, text=True, timeout=30)
            if Result.returncode == 0 and Result.stdout.strip():
                Duration = float(Result.stdout.strip())
                LoggingService.LogInfo(f"Input file duration: {Duration} seconds", 'GetInputFileDuration', 'FFmpegService')
                return Duration
            else:
                LoggingService.LogWarning(f"Failed to get duration for {InputFile}: {Result.stderr}", 'GetInputFileDuration', 'FFmpegService')
                return 0.0
                
        except Exception as e:
            LoggingService.LogException("Exception getting input file duration", e, 'GetInputFileDuration', 'FFmpegService')
            return 0.0
    
    def ExecuteFFmpeg(self, Arguments: List[str], InputFile: str = None, OutputFile: str = None) -> Dict[str, Any]:
        """Execute FFmpeg command and return results."""
        try:
            if not self.FFmpegPath:
                return {
                    'Success': False,
                    'ErrorMessage': 'FFmpeg not available',
                    'Output': '',
                    'Error': ''
                }
            
            Command = [self.FFmpegPath] + Arguments
            if InputFile:
                Command.extend(['-i', InputFile])
            if OutputFile:
                Command.append(OutputFile)
            
            LoggingService.LogDebug(f"Executing FFmpeg command: {' '.join(Command)}", 'ExecuteFFmpeg', 'FFmpegService')
            
            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for FFmpeg operations
                encoding='utf-8',
                errors='replace'
            )
            
            return {
                'Success': Result.returncode == 0,
                'ReturnCode': Result.returncode,
                'Output': Result.stdout,
                'Error': Result.stderr,
                'Command': ' '.join(Command)
            }
            
        except subprocess.TimeoutExpired:
            ErrorMessage = f"FFmpeg timeout for command: {' '.join(Arguments)}"
            LoggingService.LogWarning(ErrorMessage, 'ExecuteFFmpeg', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': 'Timeout'
            }
        except Exception as e:
            ErrorMessage = f"FFmpeg execution error: {str(e)}"
            LoggingService.LogException(ErrorMessage, e, 'ExecuteFFmpeg', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': str(e)
            }
    
    def IsFFmpegAvailable(self) -> bool:
        """Check if FFmpeg is available."""
        return self.FFmpegPath is not None
    
    def IsFFprobeAvailable(self) -> bool:
        """Check if FFprobe is available."""
        return self.FFprobePath is not None
    
    def GetVersion(self) -> Dict[str, str]:
        """Get FFmpeg and FFprobe versions."""
        Versions = {
            'FFmpeg': 'Not available',
            'FFprobe': 'Not available'
        }
        
        try:
            if self.FFmpegPath:
                Result = subprocess.run([self.FFmpegPath, '-version'], capture_output=True, text=True, timeout=10)
                if Result.returncode == 0:
                    # Extract version from first line
                    FirstLine = Result.stdout.split('\n')[0]
                    Versions['FFmpeg'] = FirstLine
            
            if self.FFprobePath:
                Result = subprocess.run([self.FFprobePath, '-version'], capture_output=True, text=True, timeout=10)
                if Result.returncode == 0:
                    # Extract version from first line
                    FirstLine = Result.stdout.split('\n')[0]
                    Versions['FFprobe'] = FirstLine
                    
        except Exception as e:
            LoggingService.LogException("Error getting FFmpeg versions", e, 'GetVersion', 'FFmpegService')
        
        return Versions
    
    def AddMediaVortexTitle(self, InputFilePath: str, OutputFilePath: str, 
                           Title: str = None, ShowTitle: str = None, 
                           EpisodeTitle: str = None) -> Dict[str, Any]:
        """Add MediaVortex title to video metadata."""
        try:
            LoggingService.LogFunctionEntry("AddMediaVortexTitle", 'FFmpegService', 
                                          f"Input: {InputFilePath}, Output: {OutputFilePath}")
            
            # Build the MediaVortex title
            MediaVortexTitle = "MediaVortex"
            if ShowTitle:
                MediaVortexTitle += f" - {ShowTitle}"
            elif Title:
                MediaVortexTitle += f" - {Title}"
            
            if EpisodeTitle:
                MediaVortexTitle += f" - {EpisodeTitle}"
            
            # Build FFmpeg arguments to add metadata
            Arguments = [
                '-i', InputFilePath,                    # Input file
                '-c', 'copy',                          # Copy streams without re-encoding
                '-metadata', f'title={MediaVortexTitle}',  # Add title metadata
                '-metadata', 'comment=Transcoded by MediaVortex',  # Add comment
                '-y'                                   # Overwrite output file
            ]
            
            # Execute FFmpeg command
            Result = self.ExecuteFFmpeg(Arguments, OutputFile=OutputFilePath)
            
            if Result['Success']:
                LoggingService.LogInfo(f"Successfully added MediaVortex title: {MediaVortexTitle}", 'AddMediaVortexTitle', 'FFmpegService')
            else:
                LoggingService.LogWarning(f"Failed to add MediaVortex title: {Result.get('ErrorMessage', '', 'Unknown error')}", 'FFmpegService', 'AddMediaVortexTitle')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error adding MediaVortex title", e, 'AddMediaVortexTitle', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f"Title addition error: {str(e)}",
                'Output': '',
                'Error': str(e)
            }
