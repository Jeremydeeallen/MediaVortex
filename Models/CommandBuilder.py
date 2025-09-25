import os
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
            InputPath = f"C:/MediaVortex/Source/{MediaFile.FileName}"
            
            # Generate output filename with target resolution
            OutputFileName = self._GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution)
            OutputPath = f"C:/MediaVortex/{OutputFileName}"
            
            # Start building command - FFmpeg command structure: ffmpeg -i input [options] output -y
            # Use relative path to FFmpeg executable from project root
            # Use Windows backslashes for the executable path
            CommandParts = ['FFmpegMaster\\bin\\ffmpeg.exe', '-i', f'"{InputPath}"']
            
            # Add video codec
            VideoCodec = ProfileSettings.get('Codec', 'libsvtav1')
            CommandParts.extend(['-c:v', VideoCodec])
            
            # Add video bitrate control (maxrate) - only if not null/blank
            VideoBitrate = ProfileSettings.get('VideoBitrateKbps')
            if VideoBitrate and VideoBitrate != '' and VideoBitrate != 'None':
                CommandParts.extend(['-maxrate', f'{VideoBitrate}k'])
            
            # Add preset if specified - only if not null/blank
            Preset = ProfileSettings.get('Preset')
            if Preset is not None and Preset != '' and Preset != 'None':
                CommandParts.extend(['-preset', str(Preset)])
            
            # Add CRF/Quality if specified - only if not null/blank
            Quality = ProfileSettings.get('Quality')
            if Quality is not None and Quality != '' and Quality != 'None':
                CommandParts.extend(['-crf', str(Quality)])
            
            # Add film grain if specified (for libsvtav1) - only if not null/blank and > 0
            FilmGrain = ProfileSettings.get('Grain')
            if FilmGrain is not None and FilmGrain != '' and FilmGrain != 'None' and FilmGrain > 0:
                CommandParts.extend(['-svtav1-params', f'film-grain={FilmGrain}'])
            
            # Add video filters (deinterlacing and scaling)
            VideoFilter = self._BuildVideoFilters(ProfileSettings, ScaleFilter)
            if VideoFilter:
                CommandParts.extend(['-vf', VideoFilter])
            
            # Add audio codec and bitrate - only if not null/blank
            AudioBitrate = ProfileSettings.get('AudioBitrateKbps')
            if AudioBitrate and AudioBitrate != '' and AudioBitrate != 'None':
                CommandParts.extend(['-c:a', 'aac', '-b:a', f'{AudioBitrate}k'])
            else:
                CommandParts.extend(['-c:a', 'copy'])
            
            # Add overwrite flag (before output path)
            CommandParts.append('-y')
            
            # Add output path (must be last)
            CommandParts.append(f'"{OutputPath}"')
            
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
    
    def _GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str) -> str:
        """Generate output filename with target resolution if different from source."""
        try:
            # If resolutions are the same, use original filename
            if SourceResolution == TargetResolution:
                return OriginalFileName
            
            # Extract resolution from filename (e.g., "1080p", "720p")
            SourceResolutionStr = self._ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                # If no resolution found in filename, just return original
                return OriginalFileName
            
            # Replace source resolution with target resolution
            TargetResolutionStr = self._FormatResolutionForFilename(TargetResolution)
            NewFileName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            
            return NewFileName
            
        except Exception:
            # If anything goes wrong, return original filename
            return OriginalFileName
    
    def _ExtractResolutionFromFilename(self, Filename: str) -> Optional[str]:
        """Extract resolution string from filename (e.g., '1080p', '720p')."""
        try:
            import re
            # Look for resolution patterns like 1080p, 720p, 480p, 4K, etc.
            ResolutionPatterns = [
                r'\b2160p\b',  # 4K
                r'\b1080p\b',  # Full HD
                r'\b720p\b',   # HD
                r'\b480p\b',   # SD
                r'\b4K\b',     # 4K alternative
                r'\bHD\b',     # HD alternative
                r'\bSD\b'      # SD alternative
            ]
            
            for pattern in ResolutionPatterns:
                match = re.search(pattern, Filename, re.IGNORECASE)
                if match:
                    return match.group(0)
            
            return None
            
        except Exception:
            return None
    
    def _FormatResolutionForFilename(self, Resolution: str) -> str:
        """Format resolution for use in filename."""
        try:
            # Convert resolution categories to standard format
            if Resolution == '2160p' or Resolution == '4K':
                return '2160p'
            elif Resolution == '1080p':
                return '1080p'
            elif Resolution == '720p':
                return '720p'
            elif Resolution == '480p':
                return '480p'
            else:
                # For any other resolution, try to extract height and add 'p'
                if 'x' in Resolution:
                    height = Resolution.split('x')[1]
                    return f"{height}p"
                else:
                    return Resolution
                    
        except Exception:
            return Resolution
    
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
        
        # Add deinterlacing filter if specified - only if not null/blank
        YadifMode = ProfileSettings.get('YadifMode')
        YadifParity = ProfileSettings.get('YadifParity')
        YadifDeint = ProfileSettings.get('YadifDeint')
        
        if (YadifMode is not None and YadifMode != '' and YadifMode != 'None' and
            YadifParity is not None and YadifParity != '' and YadifParity != 'None' and
            YadifDeint is not None and YadifDeint != '' and YadifDeint != 'None'):
            YadifFilter = f"yadif=mode={YadifMode}:parity={YadifParity}:deint={YadifDeint}"
            Filters.append(YadifFilter)
        
        # Add scale filter if provided
        if ScaleFilter:
            Filters.append(ScaleFilter)
        
        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None
