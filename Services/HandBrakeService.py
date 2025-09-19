import os
import subprocess
import json
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService


class HandBrakeService:
    """HandBrake CLI integration for transcoding operations."""
    
    def __init__(self):
        self.HandBrakeExecutable = self.FindHandBrakeExecutable()
        self.IsAvailable = self.HandBrakeExecutable is not None
        
        if self.IsAvailable:
            LoggingService.LogInfo(f"HandBrake found at: {self.HandBrakeExecutable}", "HandBrakeService", "__init__")
        else:
            LoggingService.LogWarning("HandBrake executable not found", "HandBrakeService", "__init__")
    
    def FindHandBrakeExecutable(self) -> Optional[str]:
        """Find HandBrake CLI executable."""
        try:
            LoggingService.LogFunctionEntry("FindHandBrakeExecutable", "HandBrakeService")
            
            # Check common HandBrake locations
            possiblePaths = [
                "HandBrake/HandBrakeCLI.exe",  # Relative to project root (our location)
                "HandBrakeCLI.exe",  # Current directory
                "C:/Program Files/HandBrake/HandBrakeCLI.exe",  # Windows default
                "C:/Program Files (x86)/HandBrake/HandBrakeCLI.exe",  # Windows 32-bit
                "/usr/bin/HandBrakeCLI",  # Linux
                "/usr/local/bin/HandBrakeCLI",  # Linux local
                "/Applications/HandBrakeCLI",  # macOS
            ]
            
            for path in possiblePaths:
                if os.path.exists(path) and os.path.isfile(path):
                    LoggingService.LogInfo(f"Found HandBrake at: {path}", "HandBrakeService", "FindHandBrakeExecutable")
                    return path
            
            # Try to find in PATH
            try:
                result = subprocess.run(["HandBrakeCLI", "--version"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    LoggingService.LogInfo("Found HandBrake in PATH", "HandBrakeService", "FindHandBrakeExecutable")
                    return "HandBrakeCLI"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            LoggingService.LogWarning("HandBrake executable not found in any common location", "HandBrakeService", "FindHandBrakeExecutable")
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception in FindHandBrakeExecutable", e, "HandBrakeService", "FindHandBrakeExecutable")
            return None
    
    def CheckAvailability(self) -> bool:
        """Check if HandBrake is available and working."""
        try:
            LoggingService.LogFunctionEntry("CheckAvailability", "HandBrakeService")
            
            if not self.IsAvailable:
                LoggingService.LogWarning("HandBrake not available", "HandBrakeService", "CheckAvailability")
                return False
            
            # Test HandBrake with version command
            result = self.ExecuteCommand(["--version"], Timeout=10)
            if result["Success"]:
                LoggingService.LogInfo("HandBrake availability check passed", "HandBrakeService", "CheckAvailability")
                return True
            else:
                LoggingService.LogWarning(f"HandBrake availability check failed: {result.get('ErrorMessage', 'Unknown error')}", "HandBrakeService", "CheckAvailability")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception in CheckAvailability", e, "HandBrakeService", "CheckAvailability")
            return False
    
    def ExecuteCommand(self, Arguments: List[str], InputFile: str = None, OutputFile: str = None, 
                      Timeout: int = 300) -> Dict[str, Any]:
        """Execute HandBrake command with error handling."""
        try:
            LoggingService.LogFunctionEntry("ExecuteCommand", "HandBrakeService", Arguments, InputFile, OutputFile, Timeout)
            
            if not self.IsAvailable:
                errorMsg = "HandBrake executable not available"
                LoggingService.LogError(errorMsg, "HandBrakeService", "ExecuteCommand")
                return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1}
            
            # Build command
            command = [self.HandBrakeExecutable] + Arguments
            
            if InputFile:
                command.extend(["-i", InputFile])
            
            if OutputFile:
                command.extend(["-o", OutputFile])
            
            LoggingService.LogInfo(f"Executing HandBrake command: {' '.join(command)}", "HandBrakeService", "ExecuteCommand")
            
            # Execute command
            startTime = time.time()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=Timeout,
                encoding='utf-8',
                errors='replace'
            )
            endTime = time.time()
            duration = endTime - startTime
            
            # Parse result
            success = result.returncode == 0
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            response = {
                "Success": success,
                "ReturnCode": result.returncode,
                "Output": output,
                "Error": error,
                "Duration": duration,
                "Command": ' '.join(command)
            }
            
            if success:
                LoggingService.LogInfo(f"HandBrake command completed successfully in {duration:.2f} seconds", "HandBrakeService", "ExecuteCommand")
            else:
                errorMsg = f"HandBrake command failed with return code {result.returncode}: {error}"
                LoggingService.LogError(errorMsg, "HandBrakeService", "ExecuteCommand")
                response["ErrorMessage"] = errorMsg
            
            return response
            
        except subprocess.TimeoutExpired:
            errorMsg = f"HandBrake command timed out after {Timeout} seconds"
            LoggingService.LogError(errorMsg, "HandBrakeService", "ExecuteCommand")
            return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1, "Duration": Timeout}
            
        except Exception as e:
            errorMsg = f"Exception executing HandBrake command: {str(e)}"
            LoggingService.LogException(errorMsg, e, "HandBrakeService", "ExecuteCommand")
            return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1}
    
    def GetMediaInfo(self, InputFile: str) -> Dict[str, Any]:
        """Get media information from input file."""
        try:
            LoggingService.LogFunctionEntry("GetMediaInfo", "HandBrakeService", InputFile)
            
            if not os.path.exists(InputFile):
                errorMsg = f"Input file does not exist: {InputFile}"
                LoggingService.LogError(errorMsg, "HandBrakeService", "GetMediaInfo")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Use HandBrake scan to get media info
            result = self.ExecuteCommand(["--scan", "--json"], InputFile=InputFile, Timeout=60)
            
            if not result["Success"]:
                return result
            
            try:
                # Parse JSON output
                jsonOutput = result["Output"]
                mediaInfo = json.loads(jsonOutput)
                
                # Extract relevant information
                info = {
                    "Success": True,
                    "FilePath": InputFile,
                    "Title": mediaInfo.get("Title", ""),
                    "Duration": mediaInfo.get("Duration", {}).get("Seconds", 0),
                    "VideoTracks": [],
                    "AudioTracks": [],
                    "SubtitleTracks": []
                }
                
                # Parse video tracks
                for track in mediaInfo.get("VideoList", []):
                    videoTrack = {
                        "Index": track.get("TrackNumber", 0),
                        "Codec": track.get("CodecName", ""),
                        "Width": track.get("Width", 0),
                        "Height": track.get("Height", 0),
                        "FrameRate": track.get("FrameRate", {}).get("Num", 0) / track.get("FrameRate", {}).get("Den", 1) if track.get("FrameRate", {}).get("Den", 1) > 0 else 0,
                        "Bitrate": track.get("BitRate", 0)
                    }
                    info["VideoTracks"].append(videoTrack)
                
                # Parse audio tracks
                for track in mediaInfo.get("AudioList", []):
                    audioTrack = {
                        "Index": track.get("TrackNumber", 0),
                        "Codec": track.get("CodecName", ""),
                        "Channels": track.get("ChannelLayout", ""),
                        "SampleRate": track.get("SampleRate", 0),
                        "Bitrate": track.get("BitRate", 0)
                    }
                    info["AudioTracks"].append(audioTrack)
                
                # Parse subtitle tracks
                for track in mediaInfo.get("SubtitleList", []):
                    subtitleTrack = {
                        "Index": track.get("TrackNumber", 0),
                        "Codec": track.get("CodecName", ""),
                        "Language": track.get("Language", ""),
                        "Type": track.get("Type", "")
                    }
                    info["SubtitleTracks"].append(subtitleTrack)
                
                LoggingService.LogInfo(f"Media info extracted for {InputFile}: {len(info['VideoTracks'])} video, {len(info['AudioTracks'])} audio tracks", "HandBrakeService", "GetMediaInfo")
                return info
                
            except json.JSONDecodeError as e:
                errorMsg = f"Failed to parse HandBrake JSON output: {str(e)}"
                LoggingService.LogError(errorMsg, "HandBrakeService", "GetMediaInfo")
                return {"Success": False, "ErrorMessage": errorMsg}
                
        except Exception as e:
            errorMsg = f"Exception getting media info: {str(e)}"
            LoggingService.LogException(errorMsg, e, "HandBrakeService", "GetMediaInfo")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def TranscodeFile(self, InputFile: str, OutputFile: str, Quality: int = 20, 
                     VideoBitrate: int = None, AudioBitrate: int = None,
                     Profile: str = None) -> Dict[str, Any]:
        """Transcode a file using HandBrake."""
        try:
            LoggingService.LogFunctionEntry("TranscodeFile", "HandBrakeService", InputFile, OutputFile, Quality, VideoBitrate, AudioBitrate, Profile)
            
            if not os.path.exists(InputFile):
                errorMsg = f"Input file does not exist: {InputFile}"
                LoggingService.LogError(errorMsg, "HandBrakeService", "TranscodeFile")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Ensure output directory exists
            outputDir = os.path.dirname(OutputFile)
            if outputDir and not os.path.exists(outputDir):
                os.makedirs(outputDir, exist_ok=True)
                LoggingService.LogInfo(f"Created output directory: {outputDir}", "HandBrakeService", "TranscodeFile")
            
            # Build HandBrake arguments
            arguments = [
                "--input", InputFile,
                "--output", OutputFile,
                "--quality", str(Quality),
                "--format", "mp4",
                "--encoder", "x264",
                "--optimize"
            ]
            
            # Add video bitrate if specified
            if VideoBitrate:
                arguments.extend(["--vb", str(VideoBitrate)])
            
            # Add audio bitrate if specified
            if AudioBitrate:
                arguments.extend(["--ab", str(AudioBitrate)])
            
            # Add profile if specified
            if Profile:
                arguments.extend(["--preset", Profile])
            
            # Execute transcoding
            LoggingService.LogInfo(f"Starting transcoding: {InputFile} -> {OutputFile}", "HandBrakeService", "TranscodeFile")
            result = self.ExecuteCommand(arguments, Timeout=3600)  # 1 hour timeout
            
            if result["Success"]:
                # Check if output file was created
                if os.path.exists(OutputFile):
                    outputSize = os.path.getsize(OutputFile)
                    result["OutputSize"] = outputSize
                    LoggingService.LogInfo(f"Transcoding completed successfully. Output size: {outputSize} bytes", "HandBrakeService", "TranscodeFile")
                else:
                    errorMsg = "Transcoding appeared successful but output file was not created"
                    LoggingService.LogError(errorMsg, "HandBrakeService", "TranscodeFile")
                    result["Success"] = False
                    result["ErrorMessage"] = errorMsg
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception during transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "HandBrakeService", "TranscodeFile")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def ParseProgress(self, Output: str) -> Dict[str, Any]:
        """Parse HandBrake progress output."""
        try:
            LoggingService.LogFunctionEntry("ParseProgress", "HandBrakeService", Output[:100] if Output else "None")
            
            progress = {
                "Percentage": 0.0,
                "FPS": 0.0,
                "ETA": "",
                "TimeRemaining": 0,
                "CurrentFrame": 0,
                "TotalFrames": 0
            }
            
            if not Output:
                return progress
            
            lines = Output.split('\n')
            for line in lines:
                line = line.strip()
                
                # Parse percentage (e.g., "Encoding: task 1 of 1, 45.67% (123.45 fps, avg 120.00 fps, ETA 00h05m30s)")
                if "Encoding:" in line and "%" in line:
                    try:
                        # Extract percentage
                        percentStart = line.find("Encoding:") + len("Encoding:")
                        percentEnd = line.find("%", percentStart)
                        if percentEnd > percentStart:
                            percentStr = line[percentStart:percentEnd].strip()
                            # Find the last number before %
                            parts = percentStr.split()
                            for part in reversed(parts):
                                try:
                                    progress["Percentage"] = float(part)
                                    break
                                except ValueError:
                                    continue
                        
                        # Extract FPS
                        fpsStart = line.find("fps")
                        if fpsStart > 0:
                            fpsStr = line[:fpsStart].strip()
                            fpsParts = fpsStr.split()
                            if fpsParts:
                                try:
                                    progress["FPS"] = float(fpsParts[-1])
                                except ValueError:
                                    pass
                        
                        # Extract ETA
                        etaStart = line.find("ETA")
                        if etaStart > 0:
                            etaStr = line[etaStart:].strip()
                            progress["ETA"] = etaStr
                            
                    except (ValueError, IndexError) as e:
                        LoggingService.LogWarning(f"Error parsing progress line: {line}", "HandBrakeService", "ParseProgress")
                        continue
            
            LoggingService.LogDebug(f"Parsed progress: {progress['Percentage']:.1f}%, {progress['FPS']:.1f} fps", "HandBrakeService", "ParseProgress")
            return progress
            
        except Exception as e:
            LoggingService.LogException("Exception parsing progress", e, "HandBrakeService", "ParseProgress")
            return {"Percentage": 0.0, "FPS": 0.0, "ETA": "", "TimeRemaining": 0, "CurrentFrame": 0, "TotalFrames": 0}
    
    def GetVersion(self) -> str:
        """Get HandBrake version information."""
        try:
            LoggingService.LogFunctionEntry("GetVersion", "HandBrakeService")
            
            if not self.IsAvailable:
                return "HandBrake not available"
            
            result = self.ExecuteCommand(["--version"], Timeout=10)
            if result["Success"]:
                # Extract version from output
                output = result["Output"]
                lines = output.split('\n')
                for line in lines:
                    if "HandBrake" in line and "version" in line.lower():
                        return line.strip()
                
                return output.strip()
            else:
                return f"Error getting version: {result.get('ErrorMessage', 'Unknown error')}"
                
        except Exception as e:
            LoggingService.LogException("Exception getting version", e, "HandBrakeService", "GetVersion")
            return f"Exception getting version: {str(e)}"
