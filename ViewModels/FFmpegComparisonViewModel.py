from typing import Dict, Any
from Models.FFmpegComparisonModel import FFmpegComparisonModel
from Models.FFmpegVMAFComparisonModel import FFmpegVMAFComparisonModel
from Services.FFmpegComparisonService import FFmpegComparisonService
from Services.LoggingService import LoggingService


class FFmpegComparisonViewModel:
    """ViewModel for FFmpeg comparison operations."""
    
    def __init__(self, ComparisonService: FFmpegComparisonService = None):
        self.ComparisonService = ComparisonService or FFmpegComparisonService()
    
    def CreateSideBySideComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                                 OutputPath: str = None, Width: int = None, Height: int = None) -> Dict[str, Any]:
        """Create a side-by-side comparison and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("CreateSideBySideComparison", 'FFmpegComparisonViewModel', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison
            ComparisonResult = self.ComparisonService.CreateSideBySideComparison(
                OriginalFilePath, TranscodedFilePath, OutputPath, Width, Height
            )
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': ComparisonResult.Success,
                'ErrorMessage': ComparisonResult.ErrorMessage,
                'ComparisonData': {
                    'OriginalFilePath': ComparisonResult.OriginalFilePath,
                    'TranscodedFilePath': ComparisonResult.TranscodedFilePath,
                    'ComparisonVideoPath': ComparisonResult.ComparisonVideoPath,
                    'ComparisonType': ComparisonResult.ComparisonType,
                    'Width': ComparisonResult.Width,
                    'Height': ComparisonResult.Height,
                    'DurationSeconds': ComparisonResult.DurationSeconds
                }
            }
            
            if ComparisonResult.Success:
                LoggingService.LogInfo(f"Successfully created side-by-side comparison: {ComparisonResult.ComparisonVideoPath}", 'FFmpegComparisonViewModel', 'CreateSideBySideComparison')
            else:
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonResult.ErrorMessage}", 'FFmpegComparisonViewModel', 'CreateSideBySideComparison')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in side-by-side comparison view model", e, 'FFmpegComparisonViewModel', 'CreateSideBySideComparison')
            return {
                'Success': False,
                'ErrorMessage': f"Side-by-side comparison error: {str(e)}",
                'ComparisonData': None
            }
    
    def CreatePictureInPictureComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                                       OutputPath: str = None, PiPWidth: int = 320, PiPHeight: int = 180) -> Dict[str, Any]:
        """Create a picture-in-picture comparison and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("CreatePictureInPictureComparison", 'FFmpegComparisonViewModel', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison
            ComparisonResult = self.ComparisonService.CreatePictureInPictureComparison(
                OriginalFilePath, TranscodedFilePath, OutputPath, PiPWidth, PiPHeight
            )
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': ComparisonResult.Success,
                'ErrorMessage': ComparisonResult.ErrorMessage,
                'ComparisonData': {
                    'OriginalFilePath': ComparisonResult.OriginalFilePath,
                    'TranscodedFilePath': ComparisonResult.TranscodedFilePath,
                    'ComparisonVideoPath': ComparisonResult.ComparisonVideoPath,
                    'ComparisonType': ComparisonResult.ComparisonType,
                    'Width': ComparisonResult.Width,
                    'Height': ComparisonResult.Height,
                    'DurationSeconds': ComparisonResult.DurationSeconds
                }
            }
            
            if ComparisonResult.Success:
                LoggingService.LogInfo(f"Successfully created picture-in-picture comparison: {ComparisonResult.ComparisonVideoPath}", 'FFmpegComparisonViewModel', 'CreatePictureInPictureComparison')
            else:
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonResult.ErrorMessage}", 'FFmpegComparisonViewModel', 'CreatePictureInPictureComparison')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in picture-in-picture comparison view model", e, 'FFmpegComparisonViewModel', 'CreatePictureInPictureComparison')
            return {
                'Success': False,
                'ErrorMessage': f"Picture-in-picture comparison error: {str(e)}",
                'ComparisonData': None
            }
    
    def CreateOverlayComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                              OutputPath: str = None, OverlayOpacity: float = 0.5) -> Dict[str, Any]:
        """Create an overlay comparison and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("CreateOverlayComparison", 'FFmpegComparisonViewModel', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison
            ComparisonResult = self.ComparisonService.CreateOverlayComparison(
                OriginalFilePath, TranscodedFilePath, OutputPath, OverlayOpacity
            )
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': ComparisonResult.Success,
                'ErrorMessage': ComparisonResult.ErrorMessage,
                'ComparisonData': {
                    'OriginalFilePath': ComparisonResult.OriginalFilePath,
                    'TranscodedFilePath': ComparisonResult.TranscodedFilePath,
                    'ComparisonVideoPath': ComparisonResult.ComparisonVideoPath,
                    'ComparisonType': ComparisonResult.ComparisonType,
                    'Width': ComparisonResult.Width,
                    'Height': ComparisonResult.Height,
                    'DurationSeconds': ComparisonResult.DurationSeconds
                }
            }
            
            if ComparisonResult.Success:
                LoggingService.LogInfo(f"Successfully created overlay comparison: {ComparisonResult.ComparisonVideoPath}", 'FFmpegComparisonViewModel', 'CreateOverlayComparison')
            else:
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonResult.ErrorMessage}", 'FFmpegComparisonViewModel', 'CreateOverlayComparison')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in overlay comparison view model", e, 'FFmpegComparisonViewModel', 'CreateOverlayComparison')
            return {
                'Success': False,
                'ErrorMessage': f"Overlay comparison error: {str(e)}",
                'ComparisonData': None
            }
    
    def IsComparisonAvailable(self) -> bool:
        """Check if comparison service is available."""
        return self.ComparisonService.IsAvailable()
    
    def CreateVMAFComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                            OutputPath: str = None, QualityWidth: int = 1280, 
                            QualityHeight: int = 720, VMAFModelPath: str = None) -> Dict[str, Any]:
        """Create a VMAF quality comparison and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("CreateVMAFComparison", 'FFmpegComparisonViewModel', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create VMAF comparison
            VMAFResult = self.ComparisonService.CreateVMAFComparison(
                OriginalFilePath, TranscodedFilePath, OutputPath, QualityWidth, QualityHeight, VMAFModelPath
            )
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': VMAFResult.Success,
                'ErrorMessage': VMAFResult.ErrorMessage,
                'VMAFData': VMAFResult.ToDict()
            }
            
            if VMAFResult.Success:
                LoggingService.LogInfo(f"Successfully created VMAF comparison: {VMAFResult.VMAFResultsPath}", 'FFmpegComparisonViewModel', 'CreateVMAFComparison')
            else:
                LoggingService.LogWarning(f"Failed to create VMAF comparison: {VMAFResult.ErrorMessage}", 'FFmpegComparisonViewModel', 'CreateVMAFComparison')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in VMAF comparison view model", e, 'FFmpegComparisonViewModel', 'CreateVMAFComparison')
            return {
                'Success': False,
                'ErrorMessage': f"VMAF comparison error: {str(e)}",
                'VMAFData': None
            }
    
    def GetComparisonCapabilities(self) -> Dict[str, Any]:
        """Get information about comparison capabilities."""
        return {
            'Available': self.ComparisonService.IsAvailable(),
            'ComparisonTypes': [
                {
                    'Type': 'side_by_side',
                    'Description': 'Original and transcoded videos displayed side by side',
                    'Features': ['Custom resolution support', 'Automatic scaling']
                },
                {
                    'Type': 'picture_in_picture',
                    'Description': 'Transcoded video as picture-in-picture overlay on original',
                    'Features': ['Customizable PiP size', 'Positioned in bottom-right corner']
                },
                {
                    'Type': 'overlay',
                    'Description': 'Transcoded video overlaid on original with transparency',
                    'Features': ['Adjustable opacity', 'Blend mode comparison']
                },
                {
                    'Type': 'vmaf',
                    'Description': 'VMAF quality comparison between original and transcoded videos',
                    'Features': ['Objective quality metrics', 'Frame-by-frame analysis', 'Pooled statistics', 'XML results output']
                }
            ],
            'SupportedFormats': ['mp4', 'mkv', 'avi', 'mov', 'wmv'],
            'OutputFormat': 'mp4 (H.264) for visual comparisons, XML for VMAF',
            'VMAFModels': ['vmaf-8bit.json', 'vmaf-10bit.json', 'vmaf-q25bit.json']
        }
