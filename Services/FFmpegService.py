import os
import subprocess
import shutil
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService


class FFmpegService:
    """Core FFmpeg service for executing FFmpeg and FFprobe commands."""
    
    def __init__(self):
        self.FFmpegPath = self.FindFFmpegPath()
        self.FFprobePath = self.FindFFprobePath()
        
        # Only log once when first instance is created
        if not hasattr(FFmpegService, '_logged_initialization'):
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
                LoggingService.LogInfo(f"Found FFmpeg in PATH: {FFmpegPath}", 'FindFFmpegPath', 'FFmpegService')
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
                LoggingService.LogInfo(f"Found FFprobe in PATH: {FFprobePath}", 'FindFFprobePath', 'FFmpegService')
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
    
    def ExecuteFFmpegCommand(self, Arguments: List[str]) -> Dict[str, Any]:
        """Execute FFmpeg command directly without input/output file handling."""
        try:
            if not self.FFmpegPath:
                return {
                    'Success': False,
                    'ErrorMessage': 'FFmpeg not available',
                    'Output': '',
                    'Error': ''
                }
            
            Command = [self.FFmpegPath] + Arguments
            
            LoggingService.LogDebug(f"Executing FFmpeg command: {' '.join(Command)}", 'ExecuteFFmpegCommand', 'FFmpegService')
            
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
            LoggingService.LogWarning(ErrorMessage, 'ExecuteFFmpegCommand', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
                'Output': '',
                'Error': 'Timeout'
            }
        except Exception as e:
            ErrorMessage = f"FFmpeg execution error: {str(e)}"
            LoggingService.LogException(ErrorMessage, e, 'ExecuteFFmpegCommand', 'FFmpegService')
            return {
                'Success': False,
                'ErrorMessage': ErrorMessage,
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
