import os
import subprocess
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService


class FFmpegTranscodingService:
    """Service for FFmpeg-based video transcoding with quality settings from MediaFiles table."""
    
    # Static flag to log initialization only once
    _logged_initialization = False
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService()
        self.IsAvailable = self.FFmpegService.FFmpegPath is not None
        
        # Only log initialization once per class
        if not FFmpegTranscodingService._logged_initialization:
            if self.IsAvailable:
                LoggingService.LogInfo(f"FFmpegTranscodingService initialized with FFmpeg at: {self.FFmpegService.FFmpegPath}", "FFmpegTranscodingService", "__init__")
            else:
                LoggingService.LogWarning("FFmpeg not available for transcoding operations", "FFmpegTranscodingService", "__init__")
            FFmpegTranscodingService._logged_initialization = True
    
    def TranscodeVideo(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any], ProgressCallback=None, UseMultiPass: bool = False) -> Dict[str, Any]:
        """Transcode video using FFmpeg with quality settings from MediaFiles table and optional progress monitoring."""
        try:
            LoggingService.LogFunctionEntry("TranscodeVideo", "FFmpegTranscodingService", InputFilePath, OutputFilePath, QualitySettings, UseMultiPass)
            
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
            
            # Choose encoding method
            if UseMultiPass:
                return self._TranscodeVideoMultiPass(InputFilePath, OutputFilePath, QualitySettings, ProgressCallback)
            else:
                return self._TranscodeVideoSinglePass(InputFilePath, OutputFilePath, QualitySettings, ProgressCallback)
            
        except Exception as e:
            LoggingService.LogException("Exception in FFmpeg transcoding", e, "FFmpegTranscodingService", "TranscodeVideo")
            return {
                "Success": False,
                "ErrorMessage": f"Transcoding exception: {str(e)}",
                "ReturnCode": -1
            }
    
    def _TranscodeVideoSinglePass(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any], ProgressCallback=None) -> Dict[str, Any]:
        """Transcode video using single-pass encoding."""
        try:
            # Build FFmpeg command with quality settings
            ffmpegArgs = self.BuildFFmpegCommand(InputFilePath, OutputFilePath, QualitySettings)
            
            if not ffmpegArgs:
                ErrorMsg = "Failed to build FFmpeg command"
                LoggingService.LogError(ErrorMsg, "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
                return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
            
            # Execute FFmpeg command
            CommandString = ' '.join(ffmpegArgs)
            LoggingService.LogInfo(f"Starting single-pass transcode with command: {CommandString}", "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
            StartTime = time.time()
            
            LoggingService.LogInfo(f"CALLING ExecuteFFmpegCommand with {len(ffmpegArgs)} arguments and progress callback: {ProgressCallback is not None}", "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
            result = self.FFmpegService.ExecuteFFmpegCommand(ffmpegArgs, ProgressCallback)
            LoggingService.LogInfo(f"ExecuteFFmpegCommand returned: Success={result.get('Success', False)}", "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
            EndTime = time.time()
            Duration = EndTime - StartTime
            
            # Process result
            if result['Success']:
                LoggingService.LogInfo(f"Single-pass FFmpeg transcoding completed successfully in {Duration:.2f} seconds", "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
                return {
                    "Success": True,
                    "OutputFilePath": OutputFilePath,
                    "Duration": Duration,
                    "ReturnCode": 0,
                    "Command": CommandString,
                    "EncodingMethod": "single-pass",
                    "AllOutput": result.get('AllOutput', '')
                }
            else:
                ErrorMsg = result.get('ErrorMessage', 'FFmpeg transcoding failed')
                LoggingService.LogError(f"Single-pass FFmpeg transcoding failed: {ErrorMsg}", "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
                return {
                    "Success": False,
                    "ErrorMessage": ErrorMsg,
                    "Duration": Duration,
                    "ReturnCode": result.get('ReturnCode', -1),
                    "Command": CommandString,
                    "EncodingMethod": "single-pass",
                    "AllOutput": result.get('AllOutput', '')
                }
            
        except Exception as e:
            LoggingService.LogException("Exception in single-pass FFmpeg transcoding", e, "FFmpegTranscodingService", "_TranscodeVideoSinglePass")
            return {
                "Success": False,
                "ErrorMessage": f"Single-pass transcoding exception: {str(e)}",
                "ReturnCode": -1
            }
    
    def _TranscodeVideoMultiPass(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any], ProgressCallback=None) -> Dict[str, Any]:
        """Transcode video using two-pass encoding for better quality."""
        try:
            LoggingService.LogInfo("Starting two-pass encoding process", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            startTime = time.time()
            
            # Pass 1: Analysis pass (quick)
            LoggingService.LogInfo("Starting Pass 1: Analysis", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            Pass1Args = self.BuildFFmpegMultiPassCommand(InputFilePath, OutputFilePath, QualitySettings, pass_number=1)
            
            if not Pass1Args:
                ErrorMsg = "Failed to build Pass 1 FFmpeg command"
                LoggingService.LogError(ErrorMsg, "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
                return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
            
            Pass1Command = ' '.join(Pass1Args)
            LoggingService.LogInfo(f"Pass 1 command: {Pass1Command}", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            
            # Create progress callback for Pass 1 that includes pass number
            def Pass1ProgressCallback(ProgressData):
                ProgressData['pass'] = 1
                if ProgressCallback:
                    ProgressCallback(ProgressData)
            
            # Execute Pass 1 (with progress callback for analysis pass)
            Pass1Result = self.FFmpegService.ExecuteFFmpegCommand(Pass1Args, Pass1ProgressCallback)
            
            if not Pass1Result['Success']:
                ErrorMsg = f"Pass 1 failed: {Pass1Result.get('ErrorMessage', 'Unknown error')}"
                LoggingService.LogError(ErrorMsg, "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
                return {
                    "Success": False, 
                    "ErrorMessage": ErrorMsg, 
                    "ReturnCode": Pass1Result.get('ReturnCode', -1),
                    "AllOutput": Pass1Result.get('AllOutput', '')
                }
            
            LoggingService.LogInfo("Pass 1 completed successfully", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            
            # Pass 2: Encoding pass (with progress monitoring)
            LoggingService.LogInfo("Starting Pass 2: Encoding", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            Pass2Args = self.BuildFFmpegMultiPassCommand(InputFilePath, OutputFilePath, QualitySettings, pass_number=2)
            
            if not Pass2Args:
                ErrorMsg = "Failed to build Pass 2 FFmpeg command"
                LoggingService.LogError(ErrorMsg, "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
                return {
                    "Success": False, 
                    "ErrorMessage": ErrorMsg, 
                    "ReturnCode": -1,
                    "AllOutput": Pass1Result.get('AllOutput', '')
                }
            
            Pass2Command = ' '.join(Pass2Args)
            LoggingService.LogInfo(f"Pass 2 command: {Pass2Command}", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            
            # Create progress callback for Pass 2 that includes pass number
            def Pass2ProgressCallback(ProgressData):
                ProgressData['pass'] = 2
                if ProgressCallback:
                    ProgressCallback(ProgressData)
            
            # Execute Pass 2 (with progress callback)
            Pass2Result = self.FFmpegService.ExecuteFFmpegCommand(Pass2Args, Pass2ProgressCallback)
            EndTime = time.time()
            TotalDuration = EndTime - startTime
            
            # Process result
            if Pass2Result['Success']:
                LoggingService.LogInfo(f"Two-pass FFmpeg transcoding completed successfully in {TotalDuration:.2f} seconds", "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
                # Combine output from both passes
                CombinedOutput = f"=== PASS 1 OUTPUT ===\n{Pass1Result.get('AllOutput', '')}\n\n=== PASS 2 OUTPUT ===\n{Pass2Result.get('AllOutput', '')}"
                return {
                    "Success": True,
                    "OutputFilePath": OutputFilePath,
                    "Duration": TotalDuration,
                    "ReturnCode": 0,
                    "Command": f"Pass 1: {Pass1Command}\nPass 2: {Pass2Command}",
                    "EncodingMethod": "two-pass",
                    "AllOutput": CombinedOutput
                }
            else:
                ErrorMsg = f"Pass 2 failed: {Pass2Result.get('ErrorMessage', 'Unknown error')}"
                LoggingService.LogError(ErrorMsg, "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
                # Combine output from both passes even on failure
                CombinedOutput = f"=== PASS 1 OUTPUT ===\n{Pass1Result.get('AllOutput', '')}\n\n=== PASS 2 OUTPUT ===\n{Pass2Result.get('AllOutput', '')}"
                return {
                    "Success": False,
                    "ErrorMessage": ErrorMsg,
                    "Duration": TotalDuration,
                    "ReturnCode": Pass2Result.get('ReturnCode', -1),
                    "Command": f"Pass 1: {Pass1Command}\nPass 2: {Pass2Command}",
                    "EncodingMethod": "two-pass",
                    "AllOutput": CombinedOutput
                }
            
        except Exception as e:
            LoggingService.LogException("Exception in two-pass FFmpeg transcoding", e, "FFmpegTranscodingService", "_TranscodeVideoMultiPass")
            return {
                "Success": False,
                "ErrorMessage": f"Two-pass transcoding exception: {str(e)}",
                "ReturnCode": -1
            }
    
    def BuildFFmpegCommand(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any]) -> Optional[List[str]]:
        """Build FFmpeg command with quality settings from ProfileThresholds table. Fails if required settings are missing."""
        try:
            LoggingService.LogFunctionEntry("BuildFFmpegCommand", "FFmpegTranscodingService", InputFilePath, OutputFilePath, QualitySettings)
            
            # Validate required quality settings - NO DEFAULTS ALLOWED
            required_settings = ['VideoBitrateKbps', 'AudioBitrateKbps', 'TargetResolution', 'Codec', 'Quality']
            missing_settings = []
            
            for setting in required_settings:
                if setting not in QualitySettings or QualitySettings[setting] is None:
                    missing_settings.append(setting)
            
            if missing_settings:
                error_msg = f"Missing required transcoding settings from ProfileThresholds: {', '.join(missing_settings)}"
                LoggingService.LogError(error_msg, "FFmpegTranscodingService", "BuildFFmpegCommand")
                return None
            
            # Extract quality settings - all validated to exist
            videoBitrate = QualitySettings['VideoBitrateKbps']
            audioBitrate = QualitySettings['AudioBitrateKbps']
            targetResolution = QualitySettings['TargetResolution']
            codec = QualitySettings['Codec']
            quality = QualitySettings['Quality']
            
            # Build FFmpeg arguments in correct order
            args = [
                '-i', InputFilePath,                    # Input file
                '-c:v', codec,                         # Video codec
                '-crf', str(quality),                  # CRF quality setting
                '-maxrate', f'{videoBitrate}k',        # Maximum bitrate
                '-bufsize', f'{videoBitrate * 2}k',    # Buffer size = 2x bitrate
                '-c:a', 'aac',                         # Audio codec
                '-b:a', f'{audioBitrate}k',            # Audio bitrate
                '-preset', 'medium',                   # Encoding preset
                '-y',                                  # Overwrite output file
                OutputFilePath                         # Output file
            ]
            
            LoggingService.LogInfo(f"Using CRF mode with quality {quality}, maxrate {videoBitrate}k, bufsize {videoBitrate * 2}k", "FFmpegTranscodingService", "BuildFFmpegCommand")
            
            # Note: Removed scaling filter - let FFmpeg handle resolution automatically
            # Note: Removed -movflags +faststart (not needed for MKV)
            
            LoggingService.LogInfo(f"Built FFmpeg command with {len(args)} arguments", "FFmpegTranscodingService", "BuildFFmpegCommand")
            return args
            
        except Exception as e:
            LoggingService.LogException("Error building FFmpeg command", e, "FFmpegTranscodingService", "BuildFFmpegCommand")
            return None
    
    def BuildFFmpegMultiPassCommand(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any], pass_number: int) -> Optional[List[str]]:
        """Build FFmpeg multi-pass command based on the template provided. Fails if required settings are missing."""
        try:
            LoggingService.LogFunctionEntry("BuildFFmpegMultiPassCommand", "FFmpegTranscodingService", InputFilePath, OutputFilePath, QualitySettings, pass_number)
            
            # Validate required quality settings - NO DEFAULTS ALLOWED
            required_settings = ['VideoBitrateKbps', 'AudioBitrateKbps', 'TargetResolution', 'Codec', 'Quality']
            missing_settings = []
            
            for setting in required_settings:
                if setting not in QualitySettings or QualitySettings[setting] is None:
                    missing_settings.append(setting)
            
            if missing_settings:
                error_msg = f"Missing required transcoding settings from ProfileThresholds: {', '.join(missing_settings)}"
                LoggingService.LogError(error_msg, "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
                return None
            
            # Extract quality settings - all validated to exist
            videoBitrate = QualitySettings['VideoBitrateKbps']
            audioBitrate = QualitySettings['AudioBitrateKbps']
            targetResolution = QualitySettings['TargetResolution']
            codec = QualitySettings['Codec']
            quality = QualitySettings['Quality']
            
            # Base arguments
            args = [
                '-i', InputFilePath,                    # Input file
                '-c:v', codec,                         # Video codec (HEVC)
                '-preset', 'faster',                   # Use faster preset for multi-pass
            ]
            
            if pass_number == 1:
                # Pass 1: Analysis pass (no audio, no output file)
                args.extend([
                    '-x265-params', 'pass=1',          # x265 first pass
                    '-an',                             # No audio in pass 1
                    '-f', 'null',                      # No output file
                    '-'                                # Output to null
                ])
                LoggingService.LogInfo(f"Built Pass 1 command for analysis", "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
                
            elif pass_number == 2:
                # Pass 2: Encoding pass (with audio and output file)
                args.extend([
                    '-x265-params', 'pass=2',          # x265 second pass
                    '-c:a', 'aac',                     # Audio codec
                    '-b:a', f'{audioBitrate}k',        # Audio bitrate
                    '-movflags', '+faststart',         # Optimize for streaming
                    '-y',                              # Overwrite output file
                    OutputFilePath                     # Output file
                ])
                
                # Add video quality settings - Multi-pass uses bitrate-based encoding
                # Use bitrate mode for multi-pass encoding (no CRF)
                args.insert(-2, '-b:v')  # Insert before output file
                args.insert(-2, f'{videoBitrate}k')
                args.insert(-2, '-maxrate')  # Insert before output file
                args.insert(-2, f'{videoBitrate}k')
                args.insert(-2, '-bufsize')  # Insert before output file
                args.insert(-2, f'{videoBitrate * 2}k')  # Buffer size = 2x bitrate
                LoggingService.LogInfo(f"Pass 2 using bitrate {videoBitrate}k for multi-pass encoding", "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
                
                # Add resolution scaling if needed
                if targetResolution and targetResolution != 'original':
                    scaleFilter = self.GetScaleFilter(targetResolution)
                    if scaleFilter:
                        args.insert(-2, '-vf')  # Insert before output file
                        args.insert(-2, scaleFilter)
                
                LoggingService.LogInfo(f"Built Pass 2 command for encoding", "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
            else:
                LoggingService.LogError(f"Invalid pass number: {pass_number}. Must be 1 or 2.", "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
                return None
            
            LoggingService.LogInfo(f"Built multi-pass FFmpeg command with {len(args)} arguments for pass {pass_number}", "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
            return args
            
        except Exception as e:
            LoggingService.LogException("Error building multi-pass FFmpeg command", e, "FFmpegTranscodingService", "BuildFFmpegMultiPassCommand")
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
