import os
import subprocess
import shutil
import psutil
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Core.Path.LocalPath import LocalExists


class FFmpegService:
    """Core FFmpeg service for executing FFmpeg and FFprobe commands."""
    
    # Static cache for paths to avoid repeated lookups
    _cached_ffmpeg_path = None
    _cached_ffprobe_path = None
    _logged_initialization = False
    
    def __init__(self, FFprobePath: str = None):
        # Initialize DatabaseManager
        self.DatabaseManager = DatabaseManager()

        # Resolve FFprobe path: explicit arg > WorkerContext > cached > SystemSettings
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        if FFprobePath:
            self.FFprobePath = FFprobePath
        elif Ctx and Ctx.FFprobePath:
            self.FFprobePath = Ctx.FFprobePath
        elif FFmpegService._cached_ffprobe_path is not None:
            self.FFprobePath = FFmpegService._cached_ffprobe_path
        else:
            FFmpegService._cached_ffprobe_path = self.GetFFprobePathFromSettings()
            self.FFprobePath = FFmpegService._cached_ffprobe_path

        # Resolve FFmpeg path: WorkerContext > cached > SystemSettings
        if Ctx and Ctx.FFmpegPath:
            self.FFmpegPath = Ctx.FFmpegPath
        elif FFmpegService._cached_ffmpeg_path is not None:
            self.FFmpegPath = FFmpegService._cached_ffmpeg_path
        else:
            FFmpegService._cached_ffmpeg_path = self.GetFFmpegPathFromSettings()
            self.FFmpegPath = FFmpegService._cached_ffmpeg_path
        
        # Only log once when first instance is created
        if not FFmpegService._logged_initialization:
            if not self.FFmpegPath:
                LoggingService.LogWarning("FFmpeg not found. Video processing will not be available.", '__init__', 'FFmpegService')
            
            if not self.FFprobePath:
                LoggingService.LogWarning("FFprobe not found. Media analysis will not be available.", '__init__', 'FFmpegService')
            
            FFmpegService._logged_initialization = True
    
    # directive: path-schema-migration | # see path.S8
    def FindFFmpegPath(self) -> Optional[str]:
        """Find FFmpeg executable path."""
        try:
            # Use local project FFmpeg from FFmpegMaster\bin folder
            ProjectFFmpegPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'FFmpegMaster', 'bin', 'ffmpeg.exe')
            if LocalExists(ProjectFFmpegPath):
                return ProjectFFmpegPath
            # Fallback: check system PATH (Linux containers, etc.)
            SystemPath = shutil.which('ffmpeg')
            if SystemPath:
                return SystemPath
            LoggingService.LogError(f"FFmpeg not found (project: {ProjectFFmpegPath}, system PATH: not found)", 'FindFFmpegPath', 'FFmpegService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding FFmpeg path", e, 'FindFFmpegPath', 'FFmpegService')
            return None
    
    # directive: path-schema-migration | # see path.S8
    def FindFFprobePath(self) -> Optional[str]:
        """Find FFprobe executable path."""
        try:
            # Use local project FFprobe from FFmpegMaster\bin folder
            ProjectFFprobePath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'FFmpegMaster', 'bin', 'ffprobe.exe')
            if LocalExists(ProjectFFprobePath):
                return ProjectFFprobePath
            # Fallback: check system PATH (Linux containers, etc.)
            SystemPath = shutil.which('ffprobe')
            if SystemPath:
                return SystemPath
            LoggingService.LogError(f"FFprobe not found (project: {ProjectFFprobePath}, system PATH: not found)", 'FindFFprobePath', 'FFmpegService')
            return None

        except Exception as e:
            LoggingService.LogException("Error finding FFprobe path", e, 'FindFFprobePath', 'FFmpegService')
            return None
    
    # directive: path-schema-migration | # see path.S8
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

                if LocalExists(AbsolutePath):
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
    
    # directive: path-schema-migration | # see path.S8
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

                if LocalExists(AbsolutePath):
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
    
    # directive: path-schema-migration | # see path.S8
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
                Arguments = ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams']

            # No shell=True: $/%/_ in paths pass verbatim. FilePath is already worker-native (Path.Resolve output).
            CommandList = [self.FFprobePath] + Arguments + [FilePath or ""]
            # Keep a display string for logging / error messages
            CommandString = ' '.join(f'"{A}"' if ' ' in A or '$' in A else A for A in CommandList)
            
            Result = subprocess.run(
                CommandList,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace',
            )
            
            ResultDict = {
                'Success': Result.returncode == 0,
                'ReturnCode': Result.returncode,
                'Output': Result.stdout,
                'Error': Result.stderr,
                'Command': CommandString
            }
            
            if not ResultDict['Success']:
                # Truncate stderr to a sensible size for the DB column but keep enough
                # to diagnose. Captures stdout too in case FFprobe wrote useful info there.
                StderrSnippet = (Result.stderr or '').strip()[:1500]
                StdoutSnippet = (Result.stdout or '').strip()[:500]
                ResultDict['ErrorMessage'] = f"FFprobe failed: ReturnCode={Result.returncode}, Error={StderrSnippet}"
                LoggingService.LogError(
                    f"FFprobe failed for {FilePath}\n"
                    f"  ReturnCode: {Result.returncode}\n"
                    f"  Stderr: {StderrSnippet or '(empty)'}\n"
                    f"  Stdout: {StdoutSnippet or '(empty)'}\n"
                    f"  Command: {CommandString}",
                    'ExecuteFFprobe', 'FFmpegService'
                )

            return ResultDict

        except subprocess.TimeoutExpired as e:
            ErrorMessage = f"FFprobe timeout for file: {FilePath}"
            LoggingService.LogException(ErrorMessage, e, 'ExecuteFFprobe', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': 'Timeout',
                'Command': CommandString
            }
        except Exception as e:
            ErrorMessage = f"FFprobe execution error for file: {FilePath}"
            LoggingService.LogException(ErrorMessage, e, 'ExecuteFFprobe', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': f"{ErrorMessage}: {str(e)}",
                'Output': '',
                'Error': str(e),
                'Command': CommandString
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

            # Guard: subprocess.run([None, ...]) crashes with a confusing TypeError.
            # Fail loudly with a clear message instead.
            if not self.FFprobePath:
                LoggingService.LogError(
                    "Cannot probe duration: FFprobePath is not set on this FFmpegService instance.",
                    'GetInputFileDuration', 'FFmpegService'
                )
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
            
            # Change subprocess.run to Popen so we can set affinity before execution
            Process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Set CPU affinity based on MaxCpuThreads setting (skip in Docker — cpuset handles pinning)
            if not os.path.exists('/.dockerenv'):
                try:
                    CurrentProcess = psutil.Process(Process.pid)
                    MaxCpuThreads = self.GetMaxCpuThreads()
                    AffinityCores = list(range(MaxCpuThreads))
                    CurrentProcess.cpu_affinity(AffinityCores)
                    LoggingService.LogDebug(f"Set FFmpeg CPU affinity to cores: {AffinityCores} (MaxCpuThreads: {MaxCpuThreads})", 'ExecuteFFmpeg', 'FFmpegService')
                except Exception as AffinityError:
                    LoggingService.LogWarning(f"Failed to set CPU affinity: {AffinityError}", 'ExecuteFFmpeg', 'FFmpegService')
            
            # Wait for process with timeout
            try:
                Stdout, Stderr = Process.communicate(timeout=300)  # 5 minute timeout
                ReturnCode = Process.returncode
            except subprocess.TimeoutExpired:
                Process.kill()
                Process.wait()
                ErrorMessage = "FFmpeg timeout"
                LoggingService.LogWarning(ErrorMessage, 'ExecuteFFmpeg', 'FFmpegService')
                return {
                    'Success': False,
                    'ErrorMessage': ErrorMessage,
                    'Output': '',
                    'Error': 'Timeout'
                }
            
            return {
                'Success': ReturnCode == 0,
                'ReturnCode': ReturnCode,
                'Output': Stdout,
                'Error': Stderr,
                'Command': ' '.join(Command)
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
    
    def GetMaxCpuThreads(self) -> int:
        """Get maximum CPU threads from system settings or use default."""
        try:
            # Get CPU thread limit from system settings
            MaxCpuThreads = self.DatabaseManager.GetSystemSetting('MaxCpuThreads')
            if MaxCpuThreads and MaxCpuThreads.isdigit():
                ThreadCount = int(MaxCpuThreads)
                # Validate thread count (1-32 for safety)
                if 1 <= ThreadCount <= 32:
                    return ThreadCount
            
            # Default to 16 threads for i9-14900KF (half of 32 cores to prevent overload)
            return 16
            
        except Exception:
            # If system settings fail, use safe default
            return 16
    
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