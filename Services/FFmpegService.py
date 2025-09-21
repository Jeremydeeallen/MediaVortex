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
    
    def ExecuteFFmpegCommand(self, Arguments: List[str], ProgressCallback=None, WorkingDirectory: str = None) -> Dict[str, Any]:
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
                return self._ExecuteFFmpegWithProgress(Command, ProgressCallback, WorkingDirectory)
            else:
                Result = subprocess.run(
                    Command,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout for FFmpeg operations
                    encoding='utf-8',
                    errors='replace',
                    cwd=WorkingDirectory
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

    def _ExecuteFFmpegWithProgress(self, Command: List[str], ProgressCallback, WorkingDirectory: str = None) -> Dict[str, Any]:
        """Execute FFmpeg command with real-time progress monitoring using simple direct stdout reading."""
        try:
            # Start FFmpeg process with progress output to stdout (redirect stderr to stdout like TestFfmpeg.py)
            Process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Redirect stderr to stdout like TestFfmpeg.py
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=WorkingDirectory
            )
            
            # Store all FFmpeg output
            AllOutput = []
            
            # Progress data tracking
            ProgressData = {'frame': 0, 'fps': 0, 'bitrate': 0, 'time': 0, 'speed': 0, 'duration': 0, 'total_frames': 0}
            LineCount = 0
            
            LoggingService.LogInfo("Starting direct FFmpeg progress reading", '_ExecuteFFmpegWithProgress', 'FFmpegService')
            
            # Read FFmpeg output directly - no threading, simple approach from TestFfmpeg.py
            while True:
                Line = Process.stdout.readline()
                if not Line:
                    break
                
                Line = Line.strip()
                LineCount += 1
                
                # Store all output
                AllOutput.append(f"STDOUT: {Line}")
                
                # Parse progress lines using simple approach from TestFfmpeg.py
                if Line.startswith("frame=") or Line.startswith("fps=") or Line.startswith("bitrate=") or Line.startswith("time="):
                    LoggingService.LogInfo(f"FFmpeg progress line #{LineCount}: {Line}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                    
                    # Simple parsing - extract key=value pairs
                    if '=' in Line:
                        Key, Value = Line.split('=', 1)
                        Key = Key.strip()
                        Value = Value.strip()
                        
                        # Update progress data
                        if Key == 'frame':
                            ProgressData['frame'] = int(Value) if Value.isdigit() else 0
                        elif Key == 'fps':
                            ProgressData['fps'] = float(Value) if Value.replace('.', '').isdigit() else 0
                        elif Key == 'bitrate':
                            ProgressData['bitrate'] = Value
                        elif Key == 'time':
                            ProgressData['time'] = Value
                        elif Key == 'speed':
                            ProgressData['speed'] = Value
                        elif Key == 'duration':
                            # Parse duration in seconds
                            try:
                                if ':' in Value:
                                    # Format: HH:MM:SS.mmm
                                    Parts = Value.split(':')
                                    if len(Parts) == 3:
                                        Hours = int(Parts[0])
                                        Minutes = int(Parts[1])
                                        Seconds = float(Parts[2])
                                        ProgressData['duration'] = Hours * 3600 + Minutes * 60 + Seconds
                                else:
                                    # Format: seconds
                                    ProgressData['duration'] = float(Value)
                            except:
                                ProgressData['duration'] = 0
                        
                        # Call progress callback immediately for each progress line
                        if ProgressCallback:
                            ProgressDataWithOutput = ProgressData.copy()
                            ProgressDataWithOutput['FFmpegOutput'] = '\n'.join(AllOutput)
                            LoggingService.LogInfo(f"CALLING PROGRESS CALLBACK: {ProgressDataWithOutput}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                            ProgressCallback(ProgressDataWithOutput)
                            LoggingService.LogInfo("PROGRESS CALLBACK COMPLETED", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                
                # Extract total frame count from FFmpeg metadata (only once)
                elif 'NUMBER_OF_FRAMES-eng:' in Line and ProgressData['total_frames'] == 0:
                    try:
                        # Extract frame count from line like "NUMBER_OF_FRAMES-eng: 85481"
                        FrameCountStr = Line.split('NUMBER_OF_FRAMES-eng:')[1].strip()
                        ProgressData['total_frames'] = int(FrameCountStr)
                        LoggingService.LogInfo(f"Extracted total frame count: {ProgressData['total_frames']}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                    except:
                        LoggingService.LogWarning(f"Failed to parse total frame count from line: {Line}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                else:
                    # Log non-progress lines for debugging
                    LoggingService.LogDebug(f"FFmpeg line #{LineCount}: {Line}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
            
            # Get any remaining output
            Stdout, Stderr = Process.communicate()
            
            # Add stderr to output collection
            if Stderr:
                AllOutput.append(f"STDERR: {Stderr}")
            
            # Send final progress update
            if ProgressCallback:
                FinalProgressData = ProgressData.copy()
                FinalProgressData['FFmpegOutput'] = '\n'.join(AllOutput)
                LoggingService.LogInfo(f"FINAL PROGRESS UPDATE: {FinalProgressData}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
                ProgressCallback(FinalProgressData)
            
            # Combine all output
            CombinedOutput = '\n'.join(AllOutput)
            
            LoggingService.LogInfo(f"FFmpeg process completed. Total lines read: {LineCount}, Return code: {Process.returncode}", '_ExecuteFFmpegWithProgress', 'FFmpegService')
            
            return {
                'Success': Process.returncode == 0,
                'Output': Stdout,
                'Error': Stderr,
                'ReturnCode': Process.returncode,
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
