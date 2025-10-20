import os
from typing import Dict, Any, Optional
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel


class CommandBuilder:
    """Pure data transformation model for building FFmpeg transcoding commands."""
    
    def BuildCommand(self, CommandData: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Build complete FFmpeg transcoding command from provided data.
        
        Args:
            CommandData: Dictionary containing all necessary data for command building
            
        Returns:
            Dictionary with 'Command' and 'OutputPath' keys, or None if building fails
        """
        try:
            # Extract data
            Job = CommandData.get('Job')
            MediaFile = CommandData.get('MediaFile')
            ProfileSettings = CommandData.get('ProfileSettings', {})
            CodecFlags = CommandData.get('CodecFlags', {})
            CodecParameters = CommandData.get('CodecParameters', [])
            SourceResolution = CommandData.get('SourceResolution', '')
            TargetResolution = CommandData.get('TargetResolution', '')
            ScaleFilter = CommandData.get('ScaleFilter')
            StartTime = CommandData.get('StartTime')
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')  # Default to MP4
            
            if not Job or not MediaFile:
                return None
            
            # Build command components
            InputPath = f"c:\\MediaVortex\\Source\\{MediaFile.FileName}"
            
            # Generate output filename with target resolution and container type
            CrfValue = ProfileSettings.get('Quality')
            OutputFileName = self.GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution, ContainerType, CrfValue)
            OutputPath = f"c:\\MediaVortex\\{OutputFileName}"
            
            # Start building command - FFmpeg command structure: ffmpeg -i input [options] output -y
            # Use full path to FFmpeg executable
            CommandParts = ['C:\\Code\\Automation\\MediaVortex\\FFmpegMaster\\bin\\ffmpeg.exe']
            
            # Add start time parameter if specified (must come before -i input)
            if StartTime and StartTime.strip():
                CommandParts.extend(['-ss', StartTime.strip()])
            
            # Add input file
            CommandParts.extend(['-i', f'"{InputPath}"'])
            
            # Add video codec
            VideoCodec = ProfileSettings.get('Codec', 'libsvtav1')
            CommandParts.extend(['-c:v', VideoCodec])
            
            # Add parameters using CodecParameters database values
            self.AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)
            
            # Add audio codec and bitrate - always use AAC for normalization compatibility
            AudioBitrate = ProfileSettings.get('AudioBitrateKbps')
            if AudioBitrate and AudioBitrate != '' and AudioBitrate != 'None':
                CommandParts.extend(['-c:a', 'aac', '-b:a', f'{AudioBitrate}k'])
            else:
                # Use default AAC bitrate when none specified (never use copy for audio normalization)
                CommandParts.extend(['-c:a', 'aac', '-b:a', '128k'])
            
            # Add audio filters (normalization)
            AudioFilter = self.BuildAudioFilters(ProfileSettings)
            if AudioFilter:
                CommandParts.extend(['-af', f'"{AudioFilter}"'])
            
            # Add video filters (deinterlacing and scaling)
            VideoFilter = self.BuildVideoFilters(ProfileSettings, ScaleFilter)
            if VideoFilter:
                CommandParts.extend(['-vf', f'"{VideoFilter}"'])
            
            # Add film grain parameter after video filters
            self.AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add pixel format parameter for 10-bit encoding
            self.AddPixelFormatParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add container-specific flags
            if ContainerType.lower() == 'mp4':
                CommandParts.extend(['-movflags', '+faststart'])
            
            # Add overwrite flag (before output path)
            CommandParts.append('-y')
            
            # Add output path (must be last)
            CommandParts.append(f'"{OutputPath}"')
            
            # Join command parts
            CompleteCommand = ' '.join(CommandParts)
            
            return {
                'Command': CompleteCommand,
                'OutputPath': OutputPath
            }
            
        except Exception as e:
            # Pure function should not log, just return None on error
            return None
    
    def ValidateCommandData(self, CommandData: Dict[str, Any]) -> bool:
        """Validate that all required data is present for command building."""
        RequiredKeys = ['Job', 'MediaFile', 'ProfileSettings']
        
        for key in RequiredKeys:
            if key not in CommandData or CommandData[key] is None:
                return False
        
        return True
    
    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Add codec parameters from database to command parts."""
        try:
            # Create a lookup dictionary for codec parameters
            ParamLookup = {}
            for param in CodecParameters:
                ParamLookup[param['ParameterName']] = param
            
            # Add parameters in the correct order to match expected command
            # 1. CRF (Quality) - should come before preset
            if 'crf' in ParamLookup:
                Quality = ProfileSettings.get('Quality')
                if Quality is not None and Quality != '' and Quality != 'None':
                    CommandParts.extend(['-crf', str(Quality)])
            
            # 2. Preset
            if 'preset' in ParamLookup:
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    CommandParts.extend(['-preset', str(Preset)])
            
            # 3. Video bitrate (maxrate) - only if not null/blank
            VideoBitrate = ProfileSettings.get('VideoBitrateKbps')
            if VideoBitrate and VideoBitrate != '' and VideoBitrate != 'None':
                CommandParts.extend(['-maxrate', f'{VideoBitrate}k'])
                
        except Exception:
            # If anything goes wrong, continue without adding parameters
            pass
    
    def AddFilmGrainParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Add film grain parameter for SVT-AV1."""
        try:
            # Create a lookup dictionary for codec parameters
            ParamLookup = {}
            for param in CodecParameters:
                ParamLookup[param['ParameterName']] = param
            
            # Add film grain (for libsvtav1)
            if 'film-grain' in ParamLookup:
                FilmGrain = ProfileSettings.get('FilmGrain')
                if FilmGrain is not None and FilmGrain != '' and FilmGrain != 'None' and FilmGrain > 0:
                    SvtAv1Params = [f'film-grain={FilmGrain}']
                    CommandParts.extend(['-svtav1-params', ':'.join(SvtAv1Params)])
                
        except Exception:
            # If anything goes wrong, continue without adding parameters
            pass
    
    def AddPixelFormatParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Add pixel format parameter for 10-bit encoding."""
        try:
            # Always add 10-bit encoding for SVT-AV1 to improve quality and VMAF scores
            # Use yuv420p10le for 10-bit color depth to reduce banding and improve compression efficiency
            CommandParts.extend(['-pix_fmt', 'yuv420p10le'])
                
        except Exception:
            # If anything goes wrong, continue without adding parameters
            pass

    def GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4', CrfValue: int = None) -> str:
        """Generate output filename with target resolution and container type."""
        try:
            # Get the base filename without extension
            BaseName = os.path.splitext(OriginalFileName)[0]
            
            # If resolutions are the same, just change extension
            if SourceResolution == TargetResolution:
                if CrfValue:
                    return f"{BaseName}.{CrfValue}.{ContainerType}"
                return f"{BaseName}.{ContainerType}"
            
            # Extract resolution from filename (e.g., "1080p", "720p")
            SourceResolutionStr = self.ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                # If no resolution found in filename, add target resolution
                TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
                if CrfValue:
                    return f"{BaseName}{TargetResolutionStr}.{CrfValue}.{ContainerType}"
                return f"{BaseName}{TargetResolutionStr}.{ContainerType}"
            
            # Replace source resolution with target resolution
            TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
            NewBaseName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            NewBaseName = os.path.splitext(NewBaseName)[0]  # Remove old extension
            
            # Add container type extension
            if CrfValue:
                return f"{NewBaseName}.{CrfValue}.{ContainerType}"
            return f"{NewBaseName}.{ContainerType}"
            
        except Exception:
            # If anything goes wrong, return original filename with container extension
            BaseName = os.path.splitext(OriginalFileName)[0]
            if CrfValue:
                return f"{BaseName}.{CrfValue}.{ContainerType}"
            return f"{BaseName}.{ContainerType}"
    
    def ExtractResolutionFromFilename(self, Filename: str) -> Optional[str]:
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
    
    def FormatResolutionForFilename(self, Resolution: str) -> str:
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
    
    def BuildVideoCodecParameters(self, CodecParameters: list) -> list:
        """Build video codec parameter list from codec parameters data."""
        Parameters = []
        
        for param in CodecParameters:
            if param.get('IsEnabled', False):
                ParameterName = param.get('Parameter', '')
                ParameterValue = param.get('Value', '')
                
                if ParameterName and ParameterValue is not None:
                    Parameters.extend([ParameterName, str(ParameterValue)])
        
        return Parameters
    
    def BuildAudioFilters(self, ProfileSettings: Dict[str, Any]) -> Optional[str]:
        """Build audio filter string from system settings."""
        Filters = []
        
        # Get system settings for audio compression
        try:
            from Repositories.DatabaseManager import DatabaseManager
            DatabaseManagerInstance = DatabaseManager()
            
            # Check if audio compression is enabled system-wide
            AudioCompressionEnabled = DatabaseManagerInstance.GetSystemSetting('AudioCompressionEnabled')
            if AudioCompressionEnabled and AudioCompressionEnabled.lower() in ['1', 'true', 'yes']:
                # Get compression parameters from system settings with defaults
                Threshold = int(DatabaseManagerInstance.GetSystemSetting('CompressionThreshold') or -15)
                Ratio = int(DatabaseManagerInstance.GetSystemSetting('CompressionRatio') or 3)
                Attack = int(DatabaseManagerInstance.GetSystemSetting('CompressionAttack') or 10)
                Release = int(DatabaseManagerInstance.GetSystemSetting('CompressionRelease') or 100)
                Makeup = int(DatabaseManagerInstance.GetSystemSetting('CompressionMakeup') or 3)
                
                # Build acompressor filter for dynamic range reduction
                CompressorFilter = f"acompressor=threshold={Threshold}dB:ratio={Ratio}:attack={Attack}:release={Release}:makeup={Makeup}dB"
                Filters.append(CompressorFilter)
            
            # Check if audio normalization is enabled system-wide
            AudioNormalizationEnabled = DatabaseManagerInstance.GetSystemSetting('AudioNormalizationEnabled')
            if AudioNormalizationEnabled and AudioNormalizationEnabled.lower() in ['1', 'true', 'yes']:
                # Get normalization parameters from system settings with defaults
                TargetLoudness = int(DatabaseManagerInstance.GetSystemSetting('TargetLoudness') or -23)
                LoudnessRange = int(DatabaseManagerInstance.GetSystemSetting('LoudnessRange') or 7)
                TruePeak = int(DatabaseManagerInstance.GetSystemSetting('TruePeak') or -2)
                
                # Build loudnorm filter
                LoudnormFilter = f"loudnorm=I={TargetLoudness}:LRA={LoudnessRange}:TP={TruePeak}"
                Filters.append(LoudnormFilter)
                
        except Exception:
            # If system settings fail, continue without audio filters
            pass
        
        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None

    def BuildVideoFilters(self, ProfileSettings: Dict[str, Any], ScaleFilter: Optional[str]) -> Optional[str]:
        """Build video filter string from profile settings and scale filter."""
        Filters = []
        
        # Add deinterlacing filter if specified - only if not null/blank
        YadifMode = ProfileSettings.get('YadifMode')
        YadifParity = ProfileSettings.get('YadifParity')
        YadifDeint = ProfileSettings.get('YadifDeint')
        
        if (YadifMode is not None and YadifMode != '' and YadifMode != 'None' and
            YadifParity is not None and YadifParity != '' and YadifParity != 'None' and
            YadifDeint is not None and YadifDeint != '' and YadifDeint != 'None'):
            YadifFilter = f"yadif={YadifMode}:{YadifParity}:{YadifDeint}"
            Filters.append(YadifFilter)
        
        # Add scale filter if provided
        if ScaleFilter:
            Filters.append(ScaleFilter)
        
        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None
    
    def GetMaxCpuThreads(self) -> int:
        """Get maximum CPU threads from system settings or use default."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            DatabaseManagerInstance = DatabaseManager()
            
            # Get CPU thread limit from system settings
            MaxCpuThreads = DatabaseManagerInstance.GetSystemSetting('MaxCpuThreads')
            if MaxCpuThreads and MaxCpuThreads.isdigit():
                ThreadCount = int(MaxCpuThreads)
                # Validate thread count (1-32 for safety)
                if 1 <= ThreadCount <= 32:
                    return ThreadCount
            
            # Default to 16 threads for i9-14900KF (half of 32 cores to prevent overload)
            return 16
            
        except Exception:
            # If system settings fail, use safe default
            return 16
