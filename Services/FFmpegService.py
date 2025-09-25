import os
import subprocess
import shutil
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class FFmpegService:
    """Core FFmpeg service for executing FFmpeg and FFprobe commands."""
    
    # Static cache for paths to avoid repeated lookups
    _cached_ffmpeg_path = None
    _cached_ffprobe_path = None
    _logged_initialization = False
    
    def __init__(self):
        # Use cached paths if available, otherwise find them
        if FFmpegService._cached_ffmpeg_path is None:
            FFmpegService._cached_ffmpeg_path = self.GetFFmpegPathFromSettings()
        if FFmpegService._cached_ffprobe_path is None:
            FFmpegService._cached_ffprobe_path = self.GetFFprobePathFromSettings()
            
        self.FFmpegPath = FFmpegService._cached_ffmpeg_path
        self.FFprobePath = FFmpegService._cached_ffprobe_path
        
        # Only log once when first instance is created
        if not FFmpegService._logged_initialization:
            if not self.FFmpegPath:
                LoggingService.LogWarning("FFmpeg not found. Video processing will not be available.", '__init__', 'FFmpegService')
            
            if not self.FFprobePath:
                LoggingService.LogWarning("FFprobe not found. Media analysis will not be available.", '__init__', 'FFmpegService')
            
            FFmpegService._logged_initialization = True
    
    def FindFFmpegPath(self) -> Optional[str]:
        """Find FFmpeg executable path."""
        try:
            # Use local project FFmpeg from FFmpegMaster\bin folder
            ProjectFFmpegPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'FFmpegMaster', 'bin', 'ffmpeg.exe')
            if os.path.exists(ProjectFFmpegPath):
                return ProjectFFmpegPath
            else:
                LoggingService.LogError(f"Project FFmpeg not found at: {ProjectFFmpegPath}", 'FindFFmpegPath', 'FFmpegService')
                return None
            
        except Exception as e:
            LoggingService.LogException("Error finding FFmpeg path", e, 'FindFFmpegPath', 'FFmpegService')
            return None
    
    def FindFFprobePath(self) -> Optional[str]:
        """Find FFprobe executable path."""
        try:
            # Use local project FFprobe from FFmpegMaster\bin folder
            ProjectFFprobePath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'FFmpegMaster', 'bin', 'ffprobe.exe')
            if os.path.exists(ProjectFFprobePath):
                return ProjectFFprobePath
            else:
                LoggingService.LogError(f"Project FFprobe not found at: {ProjectFFprobePath}", 'FindFFprobePath', 'FFmpegService')
                return None
            
        except Exception as e:
            LoggingService.LogException("Error finding FFprobe path", e, 'FindFFprobePath', 'FFmpegService')
            return None
    
    def GetFFmpegPathFromSettings(self) -> Optional[str]:
        """Get FFmpeg path from database settings."""
        try:
            DatabaseManagerInstance = DatabaseManager()
            SettingValue = DatabaseManagerInstance.GetSystemSetting('FFmpegPath')
            
            if SettingValue:
                # Convert relative path to absolute path
                RelativePath = SettingValue
                ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                AbsolutePath = os.path.join(ProjectRoot, RelativePath)
                
                if os.path.exists(AbsolutePath):
                    return AbsolutePath
                else:
                    LoggingService.LogError(f"FFmpeg path from settings not found: {AbsolutePath}", 'GetFFmpegPathFromSettings', 'FFmpegService')
                    return None
            else:
                LoggingService.LogWarning("No FFmpeg path found in settings, falling back to FindFFmpegPath", 'GetFFmpegPathFromSettings', 'FFmpegService')
                return self.FindFFmpegPath()
                
        except Exception as e:
            LoggingService.LogException("Error getting FFmpeg path from settings", e, 'GetFFmpegPathFromSettings', 'FFmpegService')
            return self.FindFFmpegPath()
    
    def GetFFprobePathFromSettings(self) -> Optional[str]:
        """Get FFprobe path from database settings."""
        try:
            DatabaseManagerInstance = DatabaseManager()
            SettingValue = DatabaseManagerInstance.GetSystemSetting('FFprobePath')
            
            if SettingValue:
                # Convert relative path to absolute path
                RelativePath = SettingValue
                ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                AbsolutePath = os.path.join(ProjectRoot, RelativePath)
                
                if os.path.exists(AbsolutePath):
                    return AbsolutePath
                else:
                    LoggingService.LogError(f"FFprobe path from settings not found: {AbsolutePath}", 'GetFFprobePathFromSettings', 'FFmpegService')
                    return None
            else:
                LoggingService.LogWarning("No FFprobe path found in settings, falling back to FindFFprobePath", 'GetFFprobePathFromSettings', 'FFmpegService')
                return self.FindFFprobePath()
                
        except Exception as e:
            LoggingService.LogException("Error getting FFprobe path from settings", e, 'GetFFprobePathFromSettings', 'FFmpegService')
            return self.FindFFprobePath()
    
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
            
            # Use the project-bundled FFprobe path with proper quoting for special characters
            CommandString = f'"{self.FFprobePath}"'
            for Arg in Arguments:
                CommandString += f' {Arg}'
            # Ensure file path is properly quoted and normalized
            NormalizedPath = os.path.normpath(FilePath)
            CommandString += f' "{NormalizedPath}"'
            
            
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
                # Insert -progress pipe:2 before the output file (send to stderr)
                Command = [self.FFmpegPath] + Arguments[:-1] + ['-progress', 'pipe:2'] + Arguments[-1:]
            else:
                Command = [self.FFmpegPath] + Arguments
            
            
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
                
                lineCount = 0
                
                while True:
                    if process.poll() is not None:
                        break
                    
                    line = process.stderr.readline()
                    if not line:
                        LoggingService.LogDebug(f"No more lines from stderr, breaking. Total lines read: {lineCount}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                        break
                    
                    line = line.strip()
                    lineCount += 1
                    
                    # Store all output for debugging
                    AllOutput.append(f"STDERR: {line}")
                    
                    # Log raw FFmpeg output for debugging (only at debug level)
                    LoggingService.LogDebug(f"Raw FFmpeg line #{lineCount}: '{line}'", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                    
                    # Parse FFmpeg progress line - it contains multiple key=value pairs
                    # Example: frame=41923 fps=173 q=32.3 Lsize=98359KiB time=00:23:17.43 bitrate=576.6kbits/s speed=5.76x
                    if '=' in line and ('frame=' in line or 'fps=' in line or 'time=' in line):
                        # Split by spaces and parse each key=value pair
                        parts = line.split()
                        for part in parts:
                            if '=' in part:
                                key, value = part.split('=', 1)
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
                                elif key == 'total_size' or key == 'Lsize':
                                    ProgressData['total_size'] = value
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
                        
                        # Calculate progress percentage and ETA
                        ProgressData['ProgressPercent'] = 0.0
                        ProgressData['ETA'] = "Unknown"
                        
                        if ProgressData['time'] and ProgressData['duration'] and ProgressData['duration'] > 0:
                            try:
                                # Parse current time (format: HH:MM:SS.mmm)
                                current_time_seconds = self.ParseTimeToSeconds(ProgressData['time'])
                                if current_time_seconds > 0:
                                    ProgressData['ProgressPercent'] = min(100.0, (current_time_seconds / ProgressData['duration']) * 100.0)
                                    
                                    # Calculate ETA
                                    if ProgressData['speed'] and 'x' in ProgressData['speed']:
                                        try:
                                            speed_multiplier = float(ProgressData['speed'].replace('x', ''))
                                            if speed_multiplier > 0:
                                                remaining_seconds = (ProgressData['duration'] - current_time_seconds) / speed_multiplier
                                                ProgressData['ETA'] = self.FormatSecondsToTime(remaining_seconds)
                                        except:
                                            pass
                            except:
                                pass
                        
                        # Call progress callback with calculated data
                        if ProgressCallback:
                            ProgressCallback(ProgressData)
            
            # Start progress reader thread
            ProgressThread = threading.Thread(target=progress_reader)
            ProgressThread.daemon = True
            ProgressThread.start()
            
            # Wait for process to complete without consuming stdout (let progress reader handle it)
            process.wait()
            
            # Wait for progress thread to finish
            ProgressThread.join(timeout=5)
            
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
                'Output': CombinedOutput,  # Use the collected output instead of stdout
                'Error': '',  # stderr is captured in AllOutput
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
                return Duration
            else:
                LoggingService.LogWarning(f"Failed to get duration for {InputFile}: {Result.stderr}", 'GetInputFileDuration', 'FFmpegService')
                return 0.0
                
        except Exception as e:
            LoggingService.LogException("Exception getting input file duration", e, 'GetInputFileDuration', 'FFmpegService')
            return 0.0
    
    def ParseTimeToSeconds(self, TimeString: str) -> float:
        """Parse time string (HH:MM:SS.mmm) to seconds."""
        try:
            if ':' in TimeString:
                parts = TimeString.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
            return float(TimeString)
        except:
            return 0.0
    
    def FormatSecondsToTime(self, Seconds: float) -> str:
        """Format seconds to HH:MM:SS time string."""
        try:
            hours = int(Seconds // 3600)
            minutes = int((Seconds % 3600) // 60)
            seconds = int(Seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except:
            return "00:00:00"
    
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
            
            if not Result['Success']:
                LoggingService.LogWarning(f"Failed to add MediaVortex title: {Result.get('ErrorMessage', 'Unknown error')}", 'FFmpegService', 'AddMediaVortexTitle')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error adding MediaVortex title", e, 'AddMediaVortexTitle', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f"Title addition error: {str(e)}",
                'Output': '',
                'Error': str(e)
            }