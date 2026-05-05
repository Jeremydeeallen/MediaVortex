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
                    TranscodingSettings: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Build complete transcoding command by orchestrating data preparation and command construction."""
        try:
            LoggingService.LogFunctionEntry("BuildCommand", "CommandBuilderService", Job.Id)

            # Extract settings from the provided data
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            CodecFlags = TranscodingSettings.get('CodecFlags', {})
            CodecParameters = TranscodingSettings.get('CodecParameters', {})
            SourceResolution = TranscodingSettings.get('SourceResolution', '')
            InputPath = TranscodingSettings.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")

            # Calculate target resolution and scaling
            TargetResolution = self.CalculateTargetResolution(ProfileSettings, SourceResolution)
            ScaleFilter = self.CalculateScaleFilter(SourceResolution, TargetResolution, MediaFile)

            # Determine preferred audio stream via FFprobe analysis
            AudioStreamIndex = 0
            try:
                from Services.FFmpegAnalysisService import FFmpegAnalysisService
                FFprobePath = TranscodingSettings.get('FFprobePath')
                AnalysisService = FFmpegAnalysisService(FFprobePath=FFprobePath)
                Analysis = AnalysisService.AnalyzeMediaFile(InputPath)
                if Analysis and Analysis.AudioStreamIndex is not None:
                    AudioStreamIndex = Analysis.AudioStreamIndex
                    LoggingService.LogInfo(f"Selected audio stream index {AudioStreamIndex} for transcode", "CommandBuilderService", "BuildCommand")
            except Exception as e:
                LoggingService.LogException("Error determining audio stream index, defaulting to 0", e, "CommandBuilderService", "BuildCommand")

            # Prepare command data
            CommandData = {
                'Job': Job,
                'MediaFile': MediaFile,
                'ProfileSettings': ProfileSettings,
                'CodecFlags': CodecFlags,
                'CodecParameters': CodecParameters,
                'SourceResolution': SourceResolution,
                'TargetResolution': TargetResolution,
                'ScaleFilter': ScaleFilter,
                'StartTime': TranscodingSettings.get('StartTime'),
                'AudioStreamIndex': AudioStreamIndex,
                'InputPath': InputPath,
                'FFmpegPath': TranscodingSettings.get('FFmpegPath'),
                'OutputDirectory': TranscodingSettings.get('OutputDirectory'),
                'TranscodeOutputMode': TranscodingSettings.get('TranscodeOutputMode', 'InPlace'),
                'MaxCpuThreads': TranscodingSettings.get('MaxCpuThreads')
            }

            # Build the command using the pure model
            CommandResult = self.CommandBuilder.BuildCommand(CommandData)

            if CommandResult:
                LoggingService.LogInfo(f"Successfully built command for job {Job.Id}", "CommandBuilderService", "BuildCommand")
                return CommandResult
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

    def CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str, MediaFile) -> Optional[str]:
        """Calculate FFmpeg scale filter if resolution scaling is needed, maintaining source aspect ratio."""
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

            # Get source dimensions to calculate aspect ratio
            SourceWidth, SourceHeight = self._GetSourceDimensions(MediaFile)
            SourceAspectRatio = SourceWidth / SourceHeight

            # Calculate target width maintaining source aspect ratio
            TargetWidth = self._CalculateWidthFromHeight(StandardTargetHeight, SourceAspectRatio)

            # Build scale filter with target dimensions
            ScaleFilter = f"scale={TargetWidth}:{StandardTargetHeight}"

            LoggingService.LogInfo(f"Calculated scale filter: {ScaleFilter} (from {StandardizedSource} to {StandardizedTarget}, maintaining {SourceWidth}x{SourceHeight} aspect ratio)",
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

    def _GetSourceDimensions(self, MediaFile) -> tuple:
        """Get source video width and height from MediaFile.Resolution."""
        try:
            if not MediaFile or not MediaFile.Resolution:
                return (1920, 1080)  # Default fallback

            Resolution = MediaFile.Resolution

            # Check if it's already in pixel format (e.g., "1920x1080")
            if 'x' in Resolution:
                try:
                    Width, Height = Resolution.split('x')
                    return (int(Width), int(Height))
                except (ValueError, IndexError):
                    pass

            # If it's in standard format (e.g., "1080p"), use standard dimensions
            if Resolution == '2160p' or Resolution == '4K':
                return (3840, 2160)
            elif Resolution == '1080p':
                return (1920, 1080)
            elif Resolution == '720p':
                return (1280, 720)
            elif Resolution == '480p':
                return (854, 480)
            else:
                # Try to extract height and assume 16:9
                Height = self._ExtractHeightFromResolution(Resolution)
                Width = self._CalculateWidthFromHeight(Height)
                return (Width, Height)

        except Exception as e:
            LoggingService.LogException("Exception getting source dimensions", e, "CommandBuilderService", "_GetSourceDimensions")
            return (1920, 1080)  # Default fallback

    def _CalculateWidthFromHeight(self, Height: int, AspectRatio: float = None) -> int:
        """Calculate width from height, optionally using custom aspect ratio."""
        try:
            if AspectRatio:
                # Use custom aspect ratio
                Width = int(Height * AspectRatio)
                # Ensure even number (required by codecs)
                return Width - (Width % 2)

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

    def BuildSubtitleFixCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, InputPath: str = None, TranscodingSettings: Dict[str, Any] = None) -> Optional[Dict[str, str]]:
        """Build subtitle fix command: copy video+audio, convert ASS/SSA subtitle to mov_text, output MP4."""
        try:
            LoggingService.LogFunctionEntry("BuildSubtitleFixCommand", "CommandBuilderService", Job.Id)

            SourcePath = InputPath or f"c:\\MediaVortex\\Source\\{MediaFile.FileName}"

            # Detect source codecs and preferred streams via FFprobe
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            AnalysisService = FFmpegAnalysisService()
            Analysis = AnalysisService.AnalyzeMediaFile(SourcePath)

            AudioCodec = Analysis.AudioCodec if Analysis and Analysis.AudioCodec else ''
            AudioStreamIndex = Analysis.AudioStreamIndex if Analysis and Analysis.AudioStreamIndex is not None else 0
            SubtitleStreamIndex = Analysis.SubtitleStreamIndex if Analysis and Analysis.SubtitleStreamIndex is not None else 0

            LoggingService.LogInfo(
                f"Subtitle fix: audio={AudioCodec} (stream {AudioStreamIndex}), subtitle stream {SubtitleStreamIndex} ({Analysis.SubtitleCodec if Analysis else '?'})",
                "CommandBuilderService", "BuildSubtitleFixCommand"
            )

            CommandData = {
                'Job': Job,
                'MediaFile': MediaFile,
                'AudioCodec': AudioCodec,
                'AudioStreamIndex': AudioStreamIndex,
                'SubtitleStreamIndex': SubtitleStreamIndex,
                'InputPath': SourcePath,
                'FFmpegPath': TranscodingSettings.get('FFmpegPath') if TranscodingSettings else None,
                'OutputDirectory': TranscodingSettings.get('OutputDirectory') if TranscodingSettings else None,
                'TranscodeOutputMode': TranscodingSettings.get('TranscodeOutputMode', 'InPlace') if TranscodingSettings else 'InPlace'
            }

            CommandResult = self.CommandBuilder.BuildSubtitleFixCommand(CommandData)
            if CommandResult:
                LoggingService.LogInfo(f"Built subtitle fix command for job {Job.Id}", "CommandBuilderService", "BuildSubtitleFixCommand")
            return CommandResult

        except Exception as e:
            LoggingService.LogException("Exception building subtitle fix command", e, "CommandBuilderService", "BuildSubtitleFixCommand")
            return None

    def BuildRemuxCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, InputPath: str = None, TranscodingSettings: Dict[str, Any] = None) -> Optional[Dict[str, str]]:
        """Build remux command: copy video, conditionally copy/re-encode audio, output MP4."""
        try:
            LoggingService.LogFunctionEntry("BuildRemuxCommand", "CommandBuilderService", Job.Id)

            SourcePath = InputPath or f"c:\\MediaVortex\\Source\\{MediaFile.FileName}"

            # Detect source audio codec via FFprobe
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            AnalysisService = FFmpegAnalysisService()
            Analysis = AnalysisService.AnalyzeMediaFile(SourcePath)
            AudioCodec = Analysis.AudioCodec if Analysis and Analysis.AudioCodec else ''
            AudioStreamIndex = Analysis.AudioStreamIndex if Analysis and Analysis.AudioStreamIndex is not None else 0

            LoggingService.LogInfo(f"Source audio codec for remux: {AudioCodec}, selected audio stream index: {AudioStreamIndex}", "CommandBuilderService", "BuildRemuxCommand")

            CommandData = {
                'Job': Job,
                'MediaFile': MediaFile,
                'AudioCodec': AudioCodec,
                'AudioStreamIndex': AudioStreamIndex,
                'InputPath': SourcePath,
                'FFmpegPath': TranscodingSettings.get('FFmpegPath') if TranscodingSettings else None,
                'OutputDirectory': TranscodingSettings.get('OutputDirectory') if TranscodingSettings else None,
                'TranscodeOutputMode': TranscodingSettings.get('TranscodeOutputMode', 'InPlace') if TranscodingSettings else 'InPlace'
            }

            CommandResult = self.CommandBuilder.BuildRemuxCommand(CommandData)
            if CommandResult:
                LoggingService.LogInfo(f"Built remux command for job {Job.Id}", "CommandBuilderService", "BuildRemuxCommand")
            return CommandResult

        except Exception as e:
            LoggingService.LogException("Exception building remux command", e, "CommandBuilderService", "BuildRemuxCommand")
            return None
