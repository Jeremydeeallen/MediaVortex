import os
import subprocess
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService


class FFmpegTranscodingService:
    """Service for FFmpeg-based video transcoding with quality settings from MediaFiles table."""
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService()
        self.IsAvailable = self.FFmpegService.FFmpegPath is not None
        
        if self.IsAvailable:
            LoggingService.LogInfo(f"FFmpegTranscodingService initialized with FFmpeg at: {self.FFmpegService.FFmpegPath}", "FFmpegTranscodingService", "__init__")
        else:
            LoggingService.LogWarning("FFmpeg not available for transcoding operations", "FFmpegTranscodingService", "__init__")
    
    def TranscodeVideo(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any]) -> Dict[str, Any]:
        """Transcode video using FFmpeg with quality settings from MediaFiles table."""
        try:
            LoggingService.LogFunctionEntry("TranscodeVideo", "FFmpegTranscodingService", InputFilePath, OutputFilePath, QualitySettings)
            
            if not self.IsAvailable:
                errorMsg = "FFmpeg not available for transcoding"
                LoggingService.LogError(errorMsg, "FFmpegTranscodingService", "TranscodeVideo")
                return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1}
            
            # Validate input file exists
            if not os.path.exists(InputFilePath):
                errorMsg = f"Input file does not exist: {InputFilePath}"
                LoggingService.LogError(errorMsg, "FFmpegTranscodingService", "TranscodeVideo")
                return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1}
            
            # Ensure output directory exists
            outputDir = os.path.dirname(OutputFilePath)
            if outputDir and not os.path.exists(outputDir):
                os.makedirs(outputDir, exist_ok=True)
                LoggingService.LogInfo(f"Created output directory: {outputDir}", "FFmpegTranscodingService", "TranscodeVideo")
            
            # Build FFmpeg command with quality settings
            ffmpegArgs = self.BuildFFmpegCommand(InputFilePath, OutputFilePath, QualitySettings)
            
            if not ffmpegArgs:
                errorMsg = "Failed to build FFmpeg command"
                LoggingService.LogError(errorMsg, "FFmpegTranscodingService", "TranscodeVideo")
                return {"Success": False, "ErrorMessage": errorMsg, "ReturnCode": -1}
            
            # Execute FFmpeg command
            LoggingService.LogInfo(f"Starting FFmpeg transcoding: {InputFilePath} -> {OutputFilePath}", "FFmpegTranscodingService", "TranscodeVideo")
            startTime = time.time()
            
            result = self.FFmpegService.ExecuteFFmpegCommand(ffmpegArgs)
            endTime = time.time()
            duration = endTime - startTime
            
            # Process result
            if result['Success']:
                LoggingService.LogInfo(f"FFmpeg transcoding completed successfully in {duration:.2f} seconds", "FFmpegTranscodingService", "TranscodeVideo")
                return {
                    "Success": True,
                    "OutputFilePath": OutputFilePath,
                    "Duration": duration,
                    "ReturnCode": 0,
                    "Command": ' '.join(ffmpegArgs)
                }
            else:
                errorMsg = result.get('ErrorMessage', 'FFmpeg transcoding failed')
                LoggingService.LogError(f"FFmpeg transcoding failed: {errorMsg}", "FFmpegTranscodingService", "TranscodeVideo")
                return {
                    "Success": False,
                    "ErrorMessage": errorMsg,
                    "Duration": duration,
                    "ReturnCode": result.get('ReturnCode', -1),
                    "Command": ' '.join(ffmpegArgs)
                }
            
        except Exception as e:
            LoggingService.LogException("Exception in FFmpeg transcoding", e, "FFmpegTranscodingService", "TranscodeVideo")
            return {
                "Success": False,
                "ErrorMessage": f"Transcoding exception: {str(e)}",
                "ReturnCode": -1
            }
    
    def BuildFFmpegCommand(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any]) -> Optional[List[str]]:
        """Build FFmpeg command with quality settings from MediaFiles table."""
        try:
            LoggingService.LogFunctionEntry("BuildFFmpegCommand", "FFmpegTranscodingService", InputFilePath, OutputFilePath, QualitySettings)
            
            # Extract quality settings
            videoBitrate = QualitySettings.get('VideoBitrateKbps', 2000)  # Default 2000 kbps
            audioBitrate = QualitySettings.get('AudioBitrateKbps', 128)   # Default 128 kbps
            targetResolution = QualitySettings.get('TargetResolution', '720p')
            codec = QualitySettings.get('Codec', 'libx264')
            
            # Build FFmpeg arguments
            args = [
                '-i', InputFilePath,                    # Input file
                '-c:v', codec,                         # Video codec
                '-b:v', f'{videoBitrate}k',            # Video bitrate
                '-c:a', 'aac',                         # Audio codec
                '-b:a', f'{audioBitrate}k',            # Audio bitrate
                '-preset', 'medium',                   # Encoding preset
                '-crf', '23',                          # Constant Rate Factor (quality)
                '-movflags', '+faststart',             # Optimize for streaming
                '-y',                                  # Overwrite output file
                OutputFilePath                         # Output file
            ]
            
            # Add resolution scaling if needed
            if targetResolution and targetResolution != 'original':
                scaleFilter = self.GetScaleFilter(targetResolution)
                if scaleFilter:
                    args.insert(-2, '-vf')  # Insert before output file
                    args.insert(-2, scaleFilter)
            
            LoggingService.LogInfo(f"Built FFmpeg command with {len(args)} arguments", "FFmpegTranscodingService", "BuildFFmpegCommand")
            return args
            
        except Exception as e:
            LoggingService.LogException("Error building FFmpeg command", e, "FFmpegTranscodingService", "BuildFFmpegCommand")
            return None
    
    def GetScaleFilter(self, TargetResolution: str) -> Optional[str]:
        """Get FFmpeg scale filter for target resolution while maintaining aspect ratio."""
        try:
            LoggingService.LogFunctionEntry("GetScaleFilter", "FFmpegTranscodingService", TargetResolution)
            
            # Resolution mapping
            resolutionMap = {
                '720p': 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
                '1080p': 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                '480p': 'scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2',
                '360p': 'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2'
            }
            
            scaleFilter = resolutionMap.get(TargetResolution)
            if scaleFilter:
                LoggingService.LogInfo(f"Generated scale filter for {TargetResolution}: {scaleFilter}", "FFmpegTranscodingService", "GetScaleFilter")
            else:
                LoggingService.LogWarning(f"No scale filter defined for resolution: {TargetResolution}", "FFmpegTranscodingService", "GetScaleFilter")
            
            return scaleFilter
            
        except Exception as e:
            LoggingService.LogException("Error getting scale filter", e, "FFmpegTranscodingService", "GetScaleFilter")
            return None
    
    def GetTranscodingProgress(self, ProcessId: int) -> Dict[str, Any]:
        """Get transcoding progress for a running process."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingProgress", "FFmpegTranscodingService", ProcessId)
            
            # This would integrate with FFmpeg progress monitoring
            # For now, return a placeholder implementation
            return {
                "Success": True,
                "ProcessId": ProcessId,
                "ProgressPercent": 0.0,
                "Status": "running",
                "ErrorMessage": None
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting transcoding progress", e, "FFmpegTranscodingService", "GetTranscodingProgress")
            return {
                "Success": False,
                "ProcessId": ProcessId,
                "ProgressPercent": 0.0,
                "Status": "error",
                "ErrorMessage": str(e)
            }
    
    def ValidateTranscodingSettings(self, QualitySettings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate transcoding quality settings."""
        try:
            LoggingService.LogFunctionEntry("ValidateTranscodingSettings", "FFmpegTranscodingService", QualitySettings)
            
            errors = []
            warnings = []
            
            # Validate video bitrate
            videoBitrate = QualitySettings.get('VideoBitrateKbps', 0)
            if not isinstance(videoBitrate, (int, float)) or videoBitrate <= 0:
                errors.append("VideoBitrateKbps must be a positive number")
            elif videoBitrate < 500:
                warnings.append("Video bitrate is very low, quality may be poor")
            elif videoBitrate > 10000:
                warnings.append("Video bitrate is very high, file size may be large")
            
            # Validate audio bitrate
            audioBitrate = QualitySettings.get('AudioBitrateKbps', 0)
            if not isinstance(audioBitrate, (int, float)) or audioBitrate <= 0:
                errors.append("AudioBitrateKbps must be a positive number")
            elif audioBitrate < 64:
                warnings.append("Audio bitrate is very low, quality may be poor")
            elif audioBitrate > 320:
                warnings.append("Audio bitrate is very high, file size may be large")
            
            # Validate target resolution
            targetResolution = QualitySettings.get('TargetResolution', '')
            validResolutions = ['360p', '480p', '720p', '1080p', 'original']
            if targetResolution and targetResolution not in validResolutions:
                errors.append(f"TargetResolution must be one of: {', '.join(validResolutions)}")
            
            # Validate codec
            codec = QualitySettings.get('Codec', '')
            validCodecs = ['libx264', 'libx265', 'libvpx', 'libvpx-vp9']
            if codec and codec not in validCodecs:
                errors.append(f"Codec must be one of: {', '.join(validCodecs)}")
            
            result = {
                "Success": len(errors) == 0,
                "Errors": errors,
                "Warnings": warnings,
                "ValidatedSettings": QualitySettings
            }
            
            if errors:
                LoggingService.LogError(f"Transcoding settings validation failed: {errors}", "FFmpegTranscodingService", "ValidateTranscodingSettings")
            elif warnings:
                LoggingService.LogWarning(f"Transcoding settings validation warnings: {warnings}", "FFmpegTranscodingService", "ValidateTranscodingSettings")
            else:
                LoggingService.LogInfo("Transcoding settings validation passed", "FFmpegTranscodingService", "ValidateTranscodingSettings")
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error validating transcoding settings", e, "FFmpegTranscodingService", "ValidateTranscodingSettings")
            return {
                "Success": False,
                "Errors": [f"Validation error: {str(e)}"],
                "Warnings": [],
                "ValidatedSettings": QualitySettings
            }
    
    def CheckAvailability(self) -> bool:
        """Check if FFmpeg transcoding service is available."""
        return self.IsAvailable and self.FFmpegService.FFmpegPath is not None
