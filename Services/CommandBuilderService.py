from typing import Dict, Any, Optional
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Models.CommandBuilder import CommandBuilder
from Services.ResolutionService import ResolutionService
from Services.LoggingService import LoggingService


class CommandBuilderService:
    """Orchestrates command building by coordinating data retrieval and command construction."""
    
    def __init__(self, CommandBuilderInstance: CommandBuilder = None,
                 ResolutionServiceInstance: ResolutionService = None):
        self.CommandBuilder = CommandBuilderInstance or CommandBuilder()
        self.ResolutionService = ResolutionServiceInstance or ResolutionService()
    
    def BuildCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, 
                    TranscodingSettings: Dict[str, Any]) -> Optional[str]:
        """Build complete transcoding command by orchestrating data preparation and command construction."""
        try:
            LoggingService.LogFunctionEntry("BuildCommand", "CommandBuilderService", Job.Id)
            
            # Extract settings from the provided data
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            CodecFlags = TranscodingSettings.get('CodecFlags', {})
            CodecParameters = TranscodingSettings.get('CodecParameters', {})
            SourceResolution = TranscodingSettings.get('SourceResolution', '')
            
            # Calculate target resolution and scaling
            TargetResolution = self.CalculateTargetResolution(ProfileSettings, SourceResolution)
            ScaleFilter = self.CalculateScaleFilter(SourceResolution, TargetResolution)
            
            # Prepare command data
            CommandData = {
                'Job': Job,
                'MediaFile': MediaFile,
                'ProfileSettings': ProfileSettings,
                'CodecFlags': CodecFlags,
                'CodecParameters': CodecParameters,
                'SourceResolution': SourceResolution,
                'TargetResolution': TargetResolution,
                'ScaleFilter': ScaleFilter
            }
            
            # Build the command using the pure model
            TranscodeCommand = self.CommandBuilder.BuildCommand(CommandData)
            
            if TranscodeCommand:
                LoggingService.LogInfo(f"Successfully built command for job {Job.Id}", "CommandBuilderService", "BuildCommand")
                return TranscodeCommand
            else:
                LoggingService.LogError(f"Failed to build command for job {Job.Id}", "CommandBuilderService", "BuildCommand")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception building command", e, "CommandBuilderService", "BuildCommand")
            return None
    
    def CalculateTargetResolution(self, ProfileSettings: Dict[str, Any], SourceResolution: str) -> str:
        """Calculate target resolution based on profile settings and TranscodeDownTo logic."""
        try:
            # The GetProfileSettingsForTargetResolution method already calculates the target resolution
            # based on TranscodeDownTo logic, so we just use that
            TargetResolution = ProfileSettings.get('TargetResolution')
            if TargetResolution:
                LoggingService.LogInfo(f"Using target resolution from profile settings: {TargetResolution}", 
                                     "CommandBuilderService", "CalculateTargetResolution")
                return TargetResolution
            
            # Fallback to source resolution if no target resolution found
            LoggingService.LogWarning(f"No target resolution found in profile settings, using source: {SourceResolution}", 
                                    "CommandBuilderService", "CalculateTargetResolution")
            return SourceResolution
            
        except Exception as e:
            LoggingService.LogException("Exception calculating target resolution", e, "CommandBuilderService", "CalculateTargetResolution")
            return SourceResolution
    
    def CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str) -> Optional[str]:
        """Calculate FFmpeg scale filter if resolution scaling is needed."""
        try:
            # If resolutions are the same, no scaling needed
            if SourceResolution == TargetResolution:
                return None
            
            # Standardize both resolutions
            StandardizedSource = self.ResolutionService.StandardizeResolution(SourceResolution)
            StandardizedTarget = self.ResolutionService.StandardizeResolution(TargetResolution)
            
            # Extract height from standardized resolutions
            SourceHeight = self._ExtractHeightFromResolution(StandardizedSource)
            TargetHeight = self._ExtractHeightFromResolution(StandardizedTarget)
            
            # Get standard dimensions
            StandardSourceHeight = self.ResolutionService.GetStandardHeight(SourceHeight)
            StandardTargetHeight = self.ResolutionService.GetStandardHeight(TargetHeight)
            
            # Calculate target width maintaining 16:9 aspect ratio
            TargetWidth = self._CalculateWidthFromHeight(StandardTargetHeight)
            
            # Build scale filter with target dimensions
            ScaleFilter = f"scale={TargetWidth}:{StandardTargetHeight}"
            
            LoggingService.LogInfo(f"Calculated scale filter: {ScaleFilter} (from {StandardizedSource} to {StandardizedTarget})", 
                                 "CommandBuilderService", "CalculateScaleFilter")
            
            return ScaleFilter
            
        except Exception as e:
            LoggingService.LogException("Exception calculating scale filter", e, "CommandBuilderService", "CalculateScaleFilter")
            return None
    
    def _ExtractHeightFromResolution(self, Resolution: str) -> int:
        """Extract height integer from resolution string (e.g., '1080p' -> 1080)."""
        try:
            if Resolution.endswith('p'):
                return int(Resolution[:-1])
            elif 'x' in Resolution:
                return int(Resolution.split('x')[1])
            else:
                return int(Resolution)
        except (ValueError, IndexError):
            LoggingService.LogWarning(f"Could not extract height from resolution: {Resolution}", "CommandBuilderService", "_ExtractHeightFromResolution")
            return 720  # Default fallback
    
    def _CalculateWidthFromHeight(self, Height: int) -> int:
        """Calculate width maintaining 16:9 aspect ratio from height."""
        try:
            # Standard 16:9 aspect ratio widths for common resolutions
            if Height == 2160:  # 4K
                return 3840
            elif Height == 1080:  # Full HD
                return 1920
            elif Height == 720:  # HD
                return 1280
            elif Height == 480:  # SD
                return 854
            else:
                # Calculate using 16:9 ratio for any other height
                return int(Height * 16 / 9)
        except Exception as e:
            LoggingService.LogException("Exception calculating width from height", e, "CommandBuilderService", "_CalculateWidthFromHeight")
            return 1280  # Default fallback to 720p width
