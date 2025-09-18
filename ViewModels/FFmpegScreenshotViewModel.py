from typing import Dict, Any, List
from Models.FFmpegScreenshotModel import FFmpegScreenshotModel, FFmpegScreenshotBatchModel
from Services.FFmpegScreenshotService import FFmpegScreenshotService
from Services.LoggingService import LoggingService


class FFmpegScreenshotViewModel:
    """ViewModel for FFmpeg screenshot operations."""
    
    def __init__(self, ScreenshotService: FFmpegScreenshotService = None):
        self.ScreenshotService = ScreenshotService or FFmpegScreenshotService()
    
    def GenerateScreenshot(self, SourceFilePath: str, TimestampSeconds: float, 
                          OutputPath: str = None, Width: int = None, Height: int = None,
                          Format: str = "jpg") -> Dict[str, Any]:
        """Generate a single screenshot and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshot", 'FFmpegScreenshotViewModel', 
                                          f"Source: {SourceFilePath}, Timestamp: {TimestampSeconds}")
            
            # Generate screenshot
            ScreenshotResult = self.ScreenshotService.GenerateScreenshot(
                SourceFilePath, TimestampSeconds, OutputPath, Width, Height, Format
            )
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': ScreenshotResult.Success,
                'ErrorMessage': ScreenshotResult.ErrorMessage,
                'ScreenshotData': {
                    'SourceFilePath': ScreenshotResult.SourceFilePath,
                    'ScreenshotPath': ScreenshotResult.ScreenshotPath,
                    'TimestampSeconds': ScreenshotResult.TimestampSeconds,
                    'Width': ScreenshotResult.Width,
                    'Height': ScreenshotResult.Height,
                    'Format': ScreenshotResult.Format
                }
            }
            
            if ScreenshotResult.Success:
                LoggingService.LogInfo(f"Successfully generated screenshot: {ScreenshotResult.ScreenshotPath}", 'GenerateScreenshot', 'FFmpegScreenshotViewModel')
            else:
                LoggingService.LogWarning(f"Failed to generate screenshot: {ScreenshotResult.ErrorMessage}", 'GenerateScreenshot', 'FFmpegScreenshotViewModel')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in screenshot view model", e, 'GenerateScreenshot', 'FFmpegScreenshotViewModel')
            return {
                'Success': False,
                'ErrorMessage': f"Screenshot generation error: {str(e)}",
                'ScreenshotData': None
            }
    
    def GenerateScreenshotsAtIntervals(self, SourceFilePath: str, IntervalSeconds: float = 60.0,
                                     MaxScreenshots: int = 10, OutputDirectory: str = None,
                                     Width: int = None, Height: int = None, Format: str = "jpg") -> Dict[str, Any]:
        """Generate multiple screenshots at intervals and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshotsAtIntervals", 'FFmpegScreenshotViewModel', 
                                          f"Source: {SourceFilePath}, Interval: {IntervalSeconds}s")
            
            # Generate screenshots
            BatchResult = self.ScreenshotService.GenerateScreenshotsAtIntervals(
                SourceFilePath, IntervalSeconds, MaxScreenshots, OutputDirectory, Width, Height, Format
            )
            
            # Convert to dictionary for JSON response
            ScreenshotData = []
            for Screenshot in BatchResult.Screenshots:
                ScreenshotData.append({
                    'SourceFilePath': Screenshot.SourceFilePath,
                    'ScreenshotPath': Screenshot.ScreenshotPath,
                    'TimestampSeconds': Screenshot.TimestampSeconds,
                    'Width': Screenshot.Width,
                    'Height': Screenshot.Height,
                    'Format': Screenshot.Format,
                    'Success': Screenshot.Success,
                    'ErrorMessage': Screenshot.ErrorMessage
                })
            
            Result = {
                'Success': BatchResult.Success,
                'ErrorMessage': BatchResult.ErrorMessage,
                'BatchData': {
                    'SourceFilePath': BatchResult.SourceFilePath,
                    'TotalScreenshots': BatchResult.TotalScreenshots,
                    'SuccessfulScreenshots': BatchResult.SuccessfulScreenshots,
                    'FailedScreenshots': BatchResult.FailedScreenshots,
                    'Screenshots': ScreenshotData
                }
            }
            
            if BatchResult.Success:
                LoggingService.LogInfo(f"Successfully generated {BatchResult.SuccessfulScreenshots} screenshots", 'GenerateScreenshotsAtIntervals', 'FFmpegScreenshotViewModel')
            else:
                LoggingService.LogWarning(f"Failed to generate screenshots: {BatchResult.ErrorMessage}", 'GenerateScreenshotsAtIntervals', 'FFmpegScreenshotViewModel')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in batch screenshot view model", e, 'GenerateScreenshotsAtIntervals', 'FFmpegScreenshotViewModel')
            return {
                'Success': False,
                'ErrorMessage': f"Batch screenshot generation error: {str(e)}",
                'BatchData': None
            }
    
    def GenerateScreenshotsAtSpecificTimes(self, SourceFilePath: str, Timestamps: List[float],
                                         OutputDirectory: str = None, Width: int = None, 
                                         Height: int = None, Format: str = "jpg") -> Dict[str, Any]:
        """Generate screenshots at specific timestamps and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("GenerateScreenshotsAtSpecificTimes", 'FFmpegScreenshotViewModel', 
                                          f"Source: {SourceFilePath}, Timestamps: {len(Timestamps)}")
            
            # Generate screenshots
            BatchResult = self.ScreenshotService.GenerateScreenshotsAtSpecificTimes(
                SourceFilePath, Timestamps, OutputDirectory, Width, Height, Format
            )
            
            # Convert to dictionary for JSON response
            ScreenshotData = []
            for Screenshot in BatchResult.Screenshots:
                ScreenshotData.append({
                    'SourceFilePath': Screenshot.SourceFilePath,
                    'ScreenshotPath': Screenshot.ScreenshotPath,
                    'TimestampSeconds': Screenshot.TimestampSeconds,
                    'Width': Screenshot.Width,
                    'Height': Screenshot.Height,
                    'Format': Screenshot.Format,
                    'Success': Screenshot.Success,
                    'ErrorMessage': Screenshot.ErrorMessage
                })
            
            Result = {
                'Success': BatchResult.Success,
                'ErrorMessage': BatchResult.ErrorMessage,
                'BatchData': {
                    'SourceFilePath': BatchResult.SourceFilePath,
                    'TotalScreenshots': BatchResult.TotalScreenshots,
                    'SuccessfulScreenshots': BatchResult.SuccessfulScreenshots,
                    'FailedScreenshots': BatchResult.FailedScreenshots,
                    'Screenshots': ScreenshotData
                }
            }
            
            if BatchResult.Success:
                LoggingService.LogInfo(f"Successfully generated {BatchResult.SuccessfulScreenshots} screenshots", 'GenerateScreenshotsAtSpecificTimes', 'FFmpegScreenshotViewModel')
            else:
                LoggingService.LogWarning(f"Failed to generate screenshots: {BatchResult.ErrorMessage}", 'GenerateScreenshotsAtSpecificTimes', 'FFmpegScreenshotViewModel')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in specific time screenshot view model", e, 'GenerateScreenshotsAtSpecificTimes', 'FFmpegScreenshotViewModel')
            return {
                'Success': False,
                'ErrorMessage': f"Specific time screenshot generation error: {str(e)}",
                'BatchData': None
            }
    
    def IsScreenshotAvailable(self) -> bool:
        """Check if screenshot service is available."""
        return self.ScreenshotService.IsAvailable()
    
    def GetScreenshotCapabilities(self) -> Dict[str, Any]:
        """Get information about screenshot capabilities."""
        return {
            'Available': self.ScreenshotService.IsAvailable(),
            'SupportedFormats': ['jpg', 'png', 'bmp', 'tiff'],
            'Features': [
                'Single screenshot at specific timestamp',
                'Multiple screenshots at regular intervals',
                'Multiple screenshots at specific timestamps',
                'Custom resolution and format support'
            ]
        }
