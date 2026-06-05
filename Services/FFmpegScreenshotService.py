import os
from typing import List, Optional
from pathlib import Path
from Models.FFmpegScreenshotModel import FFmpegScreenshotModel, FFmpegScreenshotBatchModel
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService
# directive: path-schema-migration | # see path.S8
from Core.Path.LocalPath import LocalBasename, LocalDirname


class FFmpegScreenshotService:
    """Business service for FFmpeg screenshot generation operations."""
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService()
    
    # directive: path-schema-migration | # see path.S8
    def GenerateScreenshot(self, SourceFilePath: str, TimestampSeconds: float,
                          OutputPath: str = None, Width: int = None, Height: int = None,
                          Format: str = "jpg") -> FFmpegScreenshotModel:
        """Generate a single screenshot from a video file."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshot", 'FFmpegScreenshotService',
                                          f"Source: {SourceFilePath}, Timestamp: {TimestampSeconds}")

            # Create screenshot model
            ScreenshotModel = FFmpegScreenshotModel()
            ScreenshotModel.SourceFilePath = SourceFilePath
            ScreenshotModel.SourceFileName = LocalBasename(SourceFilePath)
            ScreenshotModel.TimestampSeconds = TimestampSeconds
            ScreenshotModel.Format = Format

            # Generate output path if not provided
            if not OutputPath:
                SourceDir = LocalDirname(SourceFilePath)
                SourceName = Path(SourceFilePath).stem
                OutputPath = os.path.join(SourceDir, f"{SourceName}_screenshot_{TimestampSeconds:.1f}s.{Format}")

            ScreenshotModel.ScreenshotPath = OutputPath
            ScreenshotModel.ScreenshotFileName = LocalBasename(OutputPath)
            
            # Build FFmpeg arguments
            Arguments = [
                '-ss', str(TimestampSeconds),  # Seek to timestamp
                '-i', SourceFilePath,          # Input file
                '-vframes', '1',               # Extract only 1 frame
                '-q:v', '2'                    # High quality
            ]
            
            # Add size constraints if specified
            if Width and Height:
                Arguments.extend(['-s', f"{Width}x{Height}"])
                ScreenshotModel.Width = Width
                ScreenshotModel.Height = Height
            elif Width:
                Arguments.extend(['-vf', f"scale={Width}:-1"])
                ScreenshotModel.Width = Width
            elif Height:
                Arguments.extend(['-vf', f"scale=-1:{Height}"])
                ScreenshotModel.Height = Height
            
            # Execute FFmpeg command
            Result = self.FFmpegService.ExecuteFFmpeg(Arguments, OutputFile=OutputPath)
            
            if Result['Success']:
                ScreenshotModel.Success = True
                LoggingService.LogInfo(f"Successfully generated screenshot: {OutputPath}", 'GenerateScreenshot', 'FFmpegScreenshotService')
            else:
                ScreenshotModel.Success = False
                ScreenshotModel.ErrorMessage = Result.get('ErrorMessage', 'Screenshot generation failed')
                LoggingService.LogWarning(f"Failed to generate screenshot: {ScreenshotModel.ErrorMessage}", 'GenerateScreenshot', 'FFmpegScreenshotService')
            
            return ScreenshotModel
            
        except Exception as e:
            LoggingService.LogException("Error generating screenshot", e, 'GenerateScreenshot', 'FFmpegScreenshotService')
            ScreenshotModel = FFmpegScreenshotModel()
            ScreenshotModel.SourceFilePath = SourceFilePath
            ScreenshotModel.Success = False
            ScreenshotModel.ErrorMessage = f"Screenshot generation error: {str(e)}"
            return ScreenshotModel
    
    # directive: path-schema-migration | # see path.S8
    def GenerateScreenshotsAtIntervals(self, SourceFilePath: str, IntervalSeconds: float = 60.0,
                                     MaxScreenshots: int = 10, OutputDirectory: str = None,
                                     Width: int = None, Height: int = None, Format: str = "jpg") -> FFmpegScreenshotBatchModel:
        """Generate multiple screenshots at regular intervals."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshotsAtIntervals", 'FFmpegScreenshotService',
                                          f"Source: {SourceFilePath}, Interval: {IntervalSeconds}s, Max: {MaxScreenshots}")

            # Create batch model
            BatchModel = FFmpegScreenshotBatchModel()
            BatchModel.SourceFilePath = SourceFilePath
            BatchModel.SourceFileName = LocalBasename(SourceFilePath)

            # Get video duration first
            DurationResult = self.GetVideoDuration(SourceFilePath)
            if not DurationResult['Success']:
                BatchModel.ErrorMessage = f"Failed to get video duration: {DurationResult.get('ErrorMessage', 'Unknown error')}"
                return BatchModel

            DurationSeconds = DurationResult['Duration']

            # Calculate screenshot timestamps
            Timestamps = []
            CurrentTime = IntervalSeconds
            while CurrentTime < DurationSeconds and len(Timestamps) < MaxScreenshots:
                Timestamps.append(CurrentTime)
                CurrentTime += IntervalSeconds

            # Generate output directory if not provided
            if not OutputDirectory:
                SourceDir = LocalDirname(SourceFilePath)
                SourceName = Path(SourceFilePath).stem
                OutputDirectory = os.path.join(SourceDir, f"{SourceName}_screenshots")
                os.makedirs(OutputDirectory, exist_ok=True)

            # Generate screenshots
            for i, Timestamp in enumerate(Timestamps):
                OutputPath = os.path.join(OutputDirectory, f"screenshot_{i+1:03d}_{Timestamp:.1f}s.{Format}")

                Screenshot = self.GenerateScreenshot(
                    SourceFilePath, Timestamp, OutputPath, Width, Height, Format
                )

                BatchModel.AddScreenshot(Screenshot)

            BatchModel.Success = True
            LoggingService.LogInfo(f"Generated {BatchModel.SuccessfulScreenshots} screenshots for {SourceFilePath}", 'GenerateScreenshotsAtIntervals', 'FFmpegScreenshotService')
            
            return BatchModel
            
        except Exception as e:
            LoggingService.LogException("Error generating screenshots at intervals", e, 'GenerateScreenshotsAtIntervals', 'FFmpegScreenshotService')
            BatchModel = FFmpegScreenshotBatchModel()
            BatchModel.SourceFilePath = SourceFilePath
            BatchModel.Success = False
            BatchModel.ErrorMessage = f"Screenshot batch generation error: {str(e)}"
            return BatchModel
    
    # directive: path-schema-migration | # see path.S8
    def GenerateScreenshotsAtSpecificTimes(self, SourceFilePath: str, Timestamps: List[float],
                                         OutputDirectory: str = None, Width: int = None,
                                         Height: int = None, Format: str = "jpg") -> FFmpegScreenshotBatchModel:
        """Generate screenshots at specific timestamps."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshotsAtSpecificTimes", 'FFmpegScreenshotService',
                                          f"Source: {SourceFilePath}, Timestamps: {len(Timestamps)}")

            # Create batch model
            BatchModel = FFmpegScreenshotBatchModel()
            BatchModel.SourceFilePath = SourceFilePath
            BatchModel.SourceFileName = LocalBasename(SourceFilePath)

            # Generate output directory if not provided
            if not OutputDirectory:
                SourceDir = LocalDirname(SourceFilePath)
                SourceName = Path(SourceFilePath).stem
                OutputDirectory = os.path.join(SourceDir, f"{SourceName}_screenshots")
                os.makedirs(OutputDirectory, exist_ok=True)
            
            # Generate screenshots
            for i, Timestamp in enumerate(Timestamps):
                OutputPath = os.path.join(OutputDirectory, f"screenshot_{i+1:03d}_{Timestamp:.1f}s.{Format}")
                
                Screenshot = self.GenerateScreenshot(
                    SourceFilePath, Timestamp, OutputPath, Width, Height, Format
                )
                
                BatchModel.AddScreenshot(Screenshot)
            
            BatchModel.Success = True
            LoggingService.LogInfo(f"Generated {BatchModel.SuccessfulScreenshots} screenshots for {SourceFilePath}", 'GenerateScreenshotsAtSpecificTimes', 'FFmpegScreenshotService')
            
            return BatchModel
            
        except Exception as e:
            LoggingService.LogException("Error generating screenshots at specific times", e, 'GenerateScreenshotsAtSpecificTimes', 'FFmpegScreenshotService')
            BatchModel = FFmpegScreenshotBatchModel()
            BatchModel.SourceFilePath = SourceFilePath
            BatchModel.Success = False
            BatchModel.ErrorMessage = f"Screenshot batch generation error: {str(e)}"
            return BatchModel
    
    def GetVideoDuration(self, SourceFilePath: str) -> dict:
        """Get video duration in seconds."""
        try:
            Arguments = ['-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0']
            Result = self.FFmpegService.ExecuteFFprobe(SourceFilePath, Arguments)
            
            if Result['Success']:
                try:
                    Duration = float(Result['Output'].strip())
                    return {'Success': True, 'Duration': Duration}
                except (ValueError, TypeError):
                    return {'Success': False, 'ErrorMessage': 'Invalid duration format'}
            else:
                return {'Success': False, 'ErrorMessage': Result.get('ErrorMessage', 'Failed to get duration')}
                
        except Exception as e:
            LoggingService.LogException("Error getting video duration", e, 'GetVideoDuration', 'FFmpegScreenshotService')
            return {'Success': False, 'ErrorMessage': f"Duration error: {str(e)}"}
    
    def IsAvailable(self) -> bool:
        """Check if FFmpeg is available for screenshot generation."""
        return self.FFmpegService.IsFFmpegAvailable()
