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
            # Check if TranscodeDownTo is set
            TranscodeDownTo = ProfileSettings.get('TranscodeDownTo')
            if TranscodeDownTo and TranscodeDownTo != 'None':
                # Use the specified target resolution
                return TranscodeDownTo
            
            # If no TranscodeDownTo, use source resolution
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
            
            # Get standard dimensions
            SourceHeight = self.ResolutionService.GetStandardHeight(StandardizedSource)
            SourceWidth = self.ResolutionService.CalculateStandardWidth(StandardizedSource)
            TargetHeight = self.ResolutionService.GetStandardHeight(StandardizedTarget)
            TargetWidth = self.ResolutionService.CalculateStandardWidth(StandardizedTarget)
            
            # Build scale filter
            ScaleFilter = f"scale={TargetWidth}:{TargetHeight}"
            
            LoggingService.LogInfo(f"Calculated scale filter: {ScaleFilter} (from {SourceWidth}x{SourceHeight} to {TargetWidth}x{TargetHeight})", 
                                 "CommandBuilderService", "CalculateScaleFilter")
            
            return ScaleFilter
            
        except Exception as e:
            LoggingService.LogException("Exception calculating scale filter", e, "CommandBuilderService", "CalculateScaleFilter")
            return None
