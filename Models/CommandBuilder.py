import os
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService
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
            InputPath = CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")

            # Generate output filename with target resolution and container type
            CrfValue = ProfileSettings.get('Quality')
            OutputFileName = self.GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution, ContainerType, CrfValue)

            # Output location: use source file's directory (true in-place) unless Staging mode
            OutputMode = CommandData.get('TranscodeOutputMode', 'InPlace')
            if OutputMode == 'Staging':
                OutputDirectory = CommandData.get('OutputDirectory') or 'c:\\MediaVortex'
            else:
                # InPlace: put output next to the source file
                OutputDirectory = os.path.dirname(InputPath.strip('"'))
            OutputPath = os.path.join(OutputDirectory, OutputFileName)

            # Start building command - FFmpeg command structure: ffmpeg -i input [options] output -y
            # Use full path to FFmpeg executable (configurable per worker for distributed transcoding)
            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the command builder.")
            CommandParts = [FFmpegPath]
            
            # Add start time parameter if specified (must come before -i input)
            if StartTime and StartTime.strip():
                CommandParts.extend(['-ss', StartTime.strip()])
            
            # Add input file
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # Explicit stream mapping: select preferred audio stream (English when available)
            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}'])

            # Simple decision: NVIDIA or Software
            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
            
            if UseNvidiaHardware == 1:
                # NVIDIA hardware encoding
                VideoCodec = 'av1_nvenc'
            else:
                # Software encoding
                VideoCodec = ProfileSettings.get('Codec', 'libsvtav1')
            
            CommandParts.extend(['-c:v', VideoCodec])

            # Per-worker thread limit -- tells FFmpeg/SVT-AV1 how many threads to use.
            # Critical for LXC containers where /proc/cpuinfo shows all host CPUs
            # but cgroup limits actual available cores.
            MaxCpuThreads = CommandData.get('MaxCpuThreads')
            if MaxCpuThreads:
                CommandParts.extend(['-threads', str(MaxCpuThreads)])

            # Add parameters using CodecParameters database values
            self.AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)
            
            # Add audio codec and bitrate - always use AAC for normalization compatibility
            # Downmix to stereo to avoid unsupported channel layouts (e.g. 5.1 surround)
            AudioBitrate = ProfileSettings.get('AudioBitrateKbps')
            if AudioBitrate and AudioBitrate != '' and AudioBitrate != 'None':
                CommandParts.extend(['-c:a', 'aac', '-ac', '2', '-b:a', f'{AudioBitrate}k'])
            else:
                # Use default AAC bitrate when none specified (never use copy for audio normalization)
                CommandParts.extend(['-c:a', 'aac', '-ac', '2', '-b:a', '128k'])
            
            # Add audio filters (normalization)
            AudioFilter = self.BuildAudioFilters(ProfileSettings)
            if AudioFilter:
                CommandParts.extend(['-af', f'"{AudioFilter}"'])
            
            # Add video filters (deinterlacing only for interlaced sources, plus scaling)
            RawInterlaced = getattr(MediaFile, 'IsInterlaced', None) if MediaFile else None
            IsInterlaced = str(RawInterlaced) == '1' if RawInterlaced is not None else False
            VideoFilter = self.BuildVideoFilters(ProfileSettings, ScaleFilter, IsInterlaced)
            if VideoFilter:
                CommandParts.extend(['-vf', f'"{VideoFilter}"'])
            
            # Add film grain parameter after video filters
            self.AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add pixel format parameter for 10-bit encoding
            self.AddPixelFormatParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add container-specific flags
            if ContainerType.lower() == 'mp4':
                CommandParts.extend(['-movflags', '+faststart'])
            
            # Tag file so we can verify it was transcoded by MediaVortex
            CommandParts.extend(['-metadata', '"comment=Transcoded by MediaVortex"'])
            
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
            # Log loudly so the failure surfaces in the database with full traceback.
            # The previous silent return-None hid today's FFmpegPath=None ValueError
            # behind a generic "Failed to build command" message with no context.
            JobId = None
            FilePath = None
            try:
                JobObj = CommandData.get('Job') if isinstance(CommandData, dict) else None
                if JobObj is not None:
                    JobId = getattr(JobObj, 'Id', None)
                    FilePath = getattr(JobObj, 'FilePath', None)
            except Exception:
                pass
            LoggingService.LogException(
                f"CommandBuilder.BuildCommand failed (JobId={JobId}, FilePath={FilePath})",
                e, "BuildCommand", "CommandBuilder"
            )
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
            
            # Simple decision: NVIDIA or Software
            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
            
            if UseNvidiaHardware == 1:
                # NVIDIA hardware encoding parameters
                Quality = ProfileSettings.get('Quality')
                if Quality is not None and Quality != '' and Quality != 'None':
                    CommandParts.extend(['-qp', str(Quality)])
                
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    CommandParts.extend(['-preset', f'p{Preset}'])
            else:
                # Software encoding parameters
                Quality = ProfileSettings.get('Quality')
                if Quality is not None and Quality != '' and Quality != 'None':
                    if 'crf' in ParamLookup:
                        CommandParts.extend(['-crf', str(Quality)])
                
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    if 'preset' in ParamLookup:
                        CommandParts.extend(['-preset', str(Preset)])
            
            # Video bitrate (maxrate) - only if not null/blank
            VideoBitrate = ProfileSettings.get('VideoBitrateKbps')
            if VideoBitrate and VideoBitrate != '' and VideoBitrate != 'None':
                CommandParts.extend(['-maxrate', f'{VideoBitrate}k'])

        except Exception as e:
            # Codec parameter failures silently produce wrong-quality output.
            # Log loudly so the DB Logs table captures the cause; partial command
            # is still returned so the transcode runs with whatever did get added.
            LoggingService.LogException(
                "Error adding codec parameters -- transcode will run with partial/default settings",
                e, "AddCodecParameters", "CommandBuilder"
            )
    
    def AddFilmGrainParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Add film grain parameter for SVT-AV1 (skip for NVIDIA hardware acceleration)."""
        try:
            # Simple decision: Skip for NVIDIA, add for software
            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)

            if UseNvidiaHardware == 1:
                # NVIDIA doesn't support film grain - skip
                return

            # Create a lookup dictionary for codec parameters
            ParamLookup = {}
            for param in CodecParameters:
                ParamLookup[param['ParameterName']] = param

            # Add film grain (for software encoding only)
            if 'film-grain' in ParamLookup:
                FilmGrain = ProfileSettings.get('FilmGrain')
                if FilmGrain is not None and FilmGrain != '' and FilmGrain != 'None' and FilmGrain > 0:
                    CommandParts.extend(['-svtav1-params', f'film-grain={FilmGrain}'])

        except Exception as e:
            LoggingService.LogException(
                "Error adding film-grain parameter -- transcode will run without grain synthesis",
                e, "AddFilmGrainParameter", "CommandBuilder"
            )
    
    def AddPixelFormatParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Add pixel format parameter for 10-bit encoding."""
        try:
            # Always add 10-bit encoding for SVT-AV1 to improve quality and VMAF scores
            # Use yuv420p10le for 10-bit color depth to reduce banding and improve compression efficiency
            CommandParts.extend(['-pix_fmt', 'yuv420p10le'])

        except Exception as e:
            LoggingService.LogException(
                "Error adding pixel format parameter -- transcode will fall back to encoder default",
                e, "AddPixelFormatParameter", "CommandBuilder"
            )

    def GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4', CrfValue: int = None) -> str:
        """Generate output filename with target resolution and container type.
        CrfValue parameter is accepted for backwards compatibility but no longer embedded in filenames.
        CRF is tracked in the TranscodeAttempts table."""
        try:
            # Get the base filename without extension
            BaseName = os.path.splitext(OriginalFileName)[0]

            # If resolutions are the same, just change extension
            if SourceResolution == TargetResolution:
                return f"{BaseName}.{ContainerType}"

            # Extract resolution from filename (e.g., "1080p", "720p")
            SourceResolutionStr = self.ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                # If no resolution found in filename, add target resolution
                TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
                return f"{BaseName}{TargetResolutionStr}.{ContainerType}"

            # Replace source resolution with target resolution
            TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
            NewBaseName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            NewBaseName = os.path.splitext(NewBaseName)[0]  # Remove old extension

            # Add container type extension
            return f"{NewBaseName}.{ContainerType}"

        except Exception:
            # If anything goes wrong, return original filename with container extension
            BaseName = os.path.splitext(OriginalFileName)[0]
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

        except Exception as e:
            LoggingService.LogException(
                "Error reading audio filter settings from DB -- transcode will run without acompressor/loudnorm",
                e, "BuildAudioFilters", "CommandBuilder"
            )
        
        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None

    def BuildVideoFilters(self, ProfileSettings: Dict[str, Any], ScaleFilter: Optional[str], IsInterlaced: bool = False) -> Optional[str]:
        """Build video filter string. Yadif applied only when source is interlaced."""
        Filters = []

        # Apply yadif ONLY for interlaced sources (not based on profile settings).
        # Uses yadif=1:1:1 (send frame per field, auto parity, deinterlace all frames).
        if IsInterlaced:
            Filters.append("yadif=1:1:1")

        # Add scale filter if provided
        if ScaleFilter:
            Filters.append(ScaleFilter)

        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None
    
    # MP4-compatible audio codecs that can be copied without re-encoding
    MP4_COMPATIBLE_AUDIO = ['aac', 'ac3', 'eac3', 'mp3']

    def BuildRemuxCommand(self, CommandData: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Build FFmpeg remux command: copy video, handle audio conditionally, output MP4."""
        try:
            Job = CommandData.get('Job')
            MediaFile = CommandData.get('MediaFile')
            AudioCodec = CommandData.get('AudioCodec', '')

            if not Job or not MediaFile:
                return None

            InputPath = CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            OutputFileName = os.path.splitext(MediaFile.FileName)[0] + ".mp4"

            OutputMode = CommandData.get('TranscodeOutputMode', 'InPlace')
            if OutputMode == 'Staging':
                OutputDirectory = CommandData.get('OutputDirectory') or 'c:\\MediaVortex'
            else:
                OutputDirectory = os.path.dirname(InputPath.strip('"'))
            OutputPath = os.path.join(OutputDirectory, OutputFileName)

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the command builder.")
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # Explicit stream mapping: select preferred audio stream (English when available)
            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}'])

            # Video: always copy (no re-encode)
            CommandParts.extend(['-c:v', 'copy'])

            # Tag HEVC as hvc1 for broad device compatibility (Android TV, Apple, etc.)
            CommandParts.extend(['-tag:v', 'hvc1'])

            # Audio: copy if MP4-compatible, otherwise re-encode to AAC
            if AudioCodec.lower() in self.MP4_COMPATIBLE_AUDIO:
                CommandParts.extend(['-c:a', 'copy'])
            else:
                CommandParts.extend(['-c:a', 'aac', '-b:a', '128k'])

            # MP4 container flags
            CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return {
                'Command': ' '.join(CommandParts),
                'OutputPath': OutputPath
            }

        except Exception as e:
            JobId = getattr(CommandData.get('Job'), 'Id', None) if isinstance(CommandData, dict) else None
            LoggingService.LogException(
                f"CommandBuilder.BuildRemuxCommand failed (JobId={JobId})",
                e, "BuildRemuxCommand", "CommandBuilder"
            )
            return None

    def BuildSubtitleFixCommand(self, CommandData: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Build FFmpeg subtitle fix command: copy video+audio, convert ASS/SSA subtitle to mov_text, output MP4."""
        try:
            Job = CommandData.get('Job')
            MediaFile = CommandData.get('MediaFile')
            AudioCodec = CommandData.get('AudioCodec', '')
            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            SubtitleStreamIndex = CommandData.get('SubtitleStreamIndex', 0)

            if not Job or not MediaFile:
                return None

            InputPath = CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            OutputFileName = os.path.splitext(MediaFile.FileName)[0] + ".mp4"

            OutputMode = CommandData.get('TranscodeOutputMode', 'InPlace')
            if OutputMode == 'Staging':
                OutputDirectory = CommandData.get('OutputDirectory') or 'c:\\MediaVortex'
            else:
                OutputDirectory = os.path.dirname(InputPath.strip('"'))
            OutputPath = os.path.join(OutputDirectory, OutputFileName)

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the command builder.")
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # Map video, preferred audio, and preferred subtitle streams
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}', '-map', f'0:s:{SubtitleStreamIndex}'])

            # Video: copy (no re-encode)
            CommandParts.extend(['-c:v', 'copy'])

            # Tag HEVC as hvc1 for broad device compatibility
            CommandParts.extend(['-tag:v', 'hvc1'])

            # Audio: copy if MP4-compatible, otherwise re-encode to AAC
            if AudioCodec.lower() in self.MP4_COMPATIBLE_AUDIO:
                CommandParts.extend(['-c:a', 'copy'])
            else:
                CommandParts.extend(['-c:a', 'aac', '-b:a', '128k'])

            # Subtitle: convert to mov_text (MP4-native text format)
            CommandParts.extend(['-c:s', 'mov_text'])

            # MP4 container flags
            CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return {
                'Command': ' '.join(CommandParts),
                'OutputPath': OutputPath
            }

        except Exception as e:
            JobId = getattr(CommandData.get('Job'), 'Id', None) if isinstance(CommandData, dict) else None
            LoggingService.LogException(
                f"CommandBuilder.BuildSubtitleFixCommand failed (JobId={JobId})",
                e, "BuildSubtitleFixCommand", "CommandBuilder"
            )
            return None

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
