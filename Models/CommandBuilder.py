from typing import Dict, Any, Optional
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel


class CommandBuilder:
    """Pure data transformation model for building FFmpeg transcoding commands."""
    
    def BuildCommand(self, CommandData: Dict[str, Any]) -> Optional[str]:
        """Build complete FFmpeg transcoding command from provided data.
        
        Args:
            CommandData: Dictionary containing all necessary data for command building
            
        Returns:
            Complete FFmpeg command string or None if building fails
        """
        try:
            # Extract data
            Job = CommandData.get('Job')
            MediaFile = CommandData.get('MediaFile')
            ProfileSettings = CommandData.get('ProfileSettings', {})
            CodecFlags = CommandData.get('CodecFlags', {})
            CodecParameters = CommandData.get('CodecParameters', {})
            SourceResolution = CommandData.get('SourceResolution', '')
            TargetResolution = CommandData.get('TargetResolution', '')
            ScaleFilter = CommandData.get('ScaleFilter')
            
            if not Job or not MediaFile:
                return None
            
            # Build command components
            InputPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"
            OutputPath = f"C:\\MediaVortex\\{MediaFile.FileName}"
            
            # Start building command
            CommandParts = ['ffmpeg', '-i', f'"{InputPath}"']
            
            # Add video codec and settings
            VideoCodec = ProfileSettings.get('Codec', 'libsvtav1')
            CommandParts.extend(['-c:v', VideoCodec])
            
            # Add codec-specific parameters
            if CodecParameters:
                for param in CodecParameters:
                    if param.get('IsEnabled', False):
                        CommandParts.extend([param.get('Parameter'), str(param.get('Value', ''))])
            
            # Add preset if specified
            Preset = ProfileSettings.get('Preset')
            if Preset is not None:
                CommandParts.extend(['-preset', str(Preset)])
            
            # Add film grain if specified
            FilmGrain = ProfileSettings.get('FilmGrain')
            if FilmGrain is not None:
                CommandParts.extend(['-film-grain', str(FilmGrain)])
            
            # Add deinterlacing if specified
            YadifMode = ProfileSettings.get('YadifMode')
            YadifParity = ProfileSettings.get('YadifParity')
            YadifDeint = ProfileSettings.get('YadifDeint')
            
            if YadifMode is not None and YadifParity is not None and YadifDeint is not None:
                YadifFilter = f"yadif=mode={YadifMode}:parity={YadifParity}:deint={YadifDeint}"
                
                # Combine with scale filter if needed
                if ScaleFilter:
                    VideoFilter = f"{YadifFilter},{ScaleFilter}"
                else:
                    VideoFilter = YadifFilter
                
                CommandParts.extend(['-vf', VideoFilter])
            elif ScaleFilter:
                # Only scale filter
                CommandParts.extend(['-vf', ScaleFilter])
            
            # Add audio codec (copy to preserve quality)
            CommandParts.extend(['-c:a', 'copy'])
            
            # Add output path
            CommandParts.append(f'"{OutputPath}"')
            
            # Add overwrite flag
            CommandParts.append('-y')
            
            # Join command parts
            CompleteCommand = ' '.join(CommandParts)
            
            return CompleteCommand
            
        except Exception as e:
            # Pure function should not log, just return None on error
            return None
    
    def _ValidateCommandData(self, CommandData: Dict[str, Any]) -> bool:
        """Validate that all required data is present for command building."""
        RequiredKeys = ['Job', 'MediaFile', 'ProfileSettings']
        
        for key in RequiredKeys:
            if key not in CommandData or CommandData[key] is None:
                return False
        
        return True
    
    def _BuildVideoCodecParameters(self, CodecParameters: list) -> list:
        """Build video codec parameter list from codec parameters data."""
        Parameters = []
        
        for param in CodecParameters:
            if param.get('IsEnabled', False):
                ParameterName = param.get('Parameter', '')
                ParameterValue = param.get('Value', '')
                
                if ParameterName and ParameterValue is not None:
                    Parameters.extend([ParameterName, str(ParameterValue)])
        
        return Parameters
    
    def _BuildVideoFilters(self, ProfileSettings: Dict[str, Any], ScaleFilter: Optional[str]) -> Optional[str]:
        """Build video filter string from profile settings and scale filter."""
        Filters = []
        
        # Add deinterlacing filter
        YadifMode = ProfileSettings.get('YadifMode')
        YadifParity = ProfileSettings.get('YadifParity')
        YadifDeint = ProfileSettings.get('YadifDeint')
        
        if YadifMode is not None and YadifParity is not None and YadifDeint is not None:
            YadifFilter = f"yadif=mode={YadifMode}:parity={YadifParity}:deint={YadifDeint}"
            Filters.append(YadifFilter)
        
        # Add scale filter if provided
        if ScaleFilter:
            Filters.append(ScaleFilter)
        
        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None
