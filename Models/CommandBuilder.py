import os
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService
import ntpath
from Core.Path.LocalPath import LocalDirname, LocalSamePath
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Features.AudioCompletion.AudioCompletionService import AudioCompletionService


# directive: mv-suffix-greedy-collapse
class CommandBuilder:
    """Pure data transformation model for building FFmpeg transcoding commands."""

    @staticmethod
    # directive: mv-suffix-greedy-collapse
    def _CollapseMvSuffix(BaseName: str) -> str:
        """Strip ALL trailing `-mv` segments greedily so any depth of `<name>-mv...-mv.<ext>` source produces `<name>-mv.<output-ext>`. compliance-gated-rename.feature.md C7."""
        while BaseName and BaseName.lower().endswith('-mv'):
            BaseName = BaseName[:-3]
        return BaseName

    @staticmethod
    # directive: mv-suffix-greedy-collapse
    def _NormalizeFfmpegPath(Path: Optional[str]) -> str:
        r"""Collapse mixed `\` and `/` separators -- some Windows FFmpeg builds reject the mix with AVERROR(EINVAL) = -22; pure transformation, no filesystem touch."""
        if not Path:
            return Path
        return Path.strip().strip('"')

    @classmethod
    # directive: mv-suffix-greedy-collapse
    def BuildFFmpegCommand(cls, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Single public entry point. Cascade: Job.IsSubtitleFix -> subtitle-fix; Job.IsRemux -> remux; else Transcode. See command-builder.feature.md C2. Returns {Command, OutputPath} or None."""
        if not MediaFile or not Job:
            return None
        Builder = cls()
        try:
            if getattr(Job, 'IsSubtitleFix', False):
                return Builder._BuildSubtitleFixShape(MediaFile, Job, Context)
            if getattr(Job, 'IsRemux', False):
                return Builder._BuildRemuxShape(MediaFile, Job, Context)
            return Builder._BuildTranscodeShape(MediaFile, Job, Context)
        except Exception as e:
            LoggingService.LogException(
                f"CommandBuilder.BuildFFmpegCommand failed (JobId={getattr(Job, 'Id', None)})",
                e, "BuildFFmpegCommand", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
    def _RunFFprobeAnalysis(self, InputPath: str, FFprobePath: Optional[str]):
        """Pre-flight FFprobe (header-only) for remux/subtitle-fix stream detection. Returns analysis object or None on failure."""
        try:
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            AnalysisService = FFmpegAnalysisService(FFprobePath=FFprobePath)
            return AnalysisService.AnalyzeMediaFile(InputPath)
        except Exception as e:
            LoggingService.LogException(
                f"CommandBuilder._RunFFprobeAnalysis failed (InputPath={InputPath})",
                e, "_RunFFprobeAnalysis", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
    def _CalculateTargetResolution(self, ProfileSettings: Dict[str, Any], SourceResolution: str) -> str:
        Target = ProfileSettings.get('TargetResolution')
        return Target if Target else SourceResolution

    # directive: mv-suffix-greedy-collapse
    def _CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str, MediaFile, ProfileSettings: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Width-anchored scale: emits scale=w=<TierWidth>:h=-2 (letterbox-safe; codec-legal even height)."""
        try:
            if SourceResolution == TargetResolution:
                return None
            from Services.ResolutionService import ResolutionService
            ResolutionServiceInstance = ResolutionService()
            StandardizedTarget = ResolutionServiceInstance.StandardizeResolution(TargetResolution)
            TargetHeight = self._ExtractHeightFromResolution(StandardizedTarget)
            StandardTargetHeight = ResolutionServiceInstance.GetStandardHeight(TargetHeight)
            TierWidth = {2160: 3840, 1080: 1920, 720: 1280, 480: 854}.get(StandardTargetHeight)
            if TierWidth is None:
                return None
            return f"scale=w={TierWidth}:h=-2"
        except Exception as e:
            LoggingService.LogException(
                "Exception calculating scale filter", e, "_CalculateScaleFilter", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
    def _ExtractHeightFromResolution(self, Resolution: str) -> int:
        try:
            if Resolution.endswith('p'):
                return int(Resolution[:-1])
            if 'x' in Resolution:
                return int(Resolution.split('x')[1])
            return int(Resolution)
        except (ValueError, IndexError):
            return 720

    # directive: mv-suffix-greedy-collapse
    def _GetSourceDimensions(self, MediaFile) -> tuple:
        try:
            if not MediaFile or not getattr(MediaFile, 'Resolution', None):
                return (1920, 1080)
            Resolution = MediaFile.Resolution
            if 'x' in Resolution:
                try:
                    Width, Height = Resolution.split('x')
                    return (int(Width), int(Height))
                except (ValueError, IndexError):
                    pass
            if Resolution in ('2160p', '4K'):
                return (3840, 2160)
            if Resolution == '1080p':
                return (1920, 1080)
            if Resolution == '720p':
                return (1280, 720)
            if Resolution == '480p':
                return (854, 480)
            Height = self._ExtractHeightFromResolution(Resolution)
            return (self._CalculateWidthFromHeight(Height), Height)
        except Exception:
            return (1920, 1080)

    # directive: mv-suffix-greedy-collapse
    def _CalculateWidthFromHeight(self, Height: int, AspectRatio: Optional[float] = None) -> int:
        try:
            if AspectRatio:
                Width = int(Height * AspectRatio)
                return Width - (Width % 2)
            if Height == 2160:
                return 3840
            if Height == 1080:
                return 1920
            if Height == 720:
                return 1280
            if Height == 480:
                return 854
            return int(Height * 16 / 9)
        except Exception:
            return 1280

    # directive: mv-suffix-greedy-collapse
    def _BuildTranscodeShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Transcode shape: video re-encode + audio (branch on AudioComplete) + container. Heaviest path -- subsumes remux + audio as side-effects of one FFmpeg pass."""
        try:
            CommandData = Context  # legacy alias; existing code paths read from it
            ProfileSettings = CommandData.get('ProfileSettings', {})
            CodecFlags = CommandData.get('CodecFlags', {})
            CodecParameters = CommandData.get('CodecParameters', [])
            SourceResolution = CommandData.get('SourceResolution') or getattr(MediaFile, 'Resolution', '') or ''
            TargetResolution = CommandData.get('TargetResolution') or self._CalculateTargetResolution(ProfileSettings, SourceResolution)
            ScaleFilter = CommandData.get('ScaleFilter')
            if ScaleFilter is None and TargetResolution and SourceResolution and TargetResolution != SourceResolution:
                ScaleFilter = self._CalculateScaleFilter(SourceResolution, TargetResolution, MediaFile, ProfileSettings)
            StartTime = CommandData.get('StartTime')
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')

            # Build command components
            InputPath = self._NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            # Resolve preferred audio stream via FFprobe if caller didn't supply one
            if 'AudioStreamIndex' not in CommandData:
                Analysis = self._RunFFprobeAnalysis(InputPath, CommandData.get('FFprobePath'))
                if Analysis and Analysis.AudioStreamIndex is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex

            # Generate output filename with target resolution and container type
            CrfValue = ProfileSettings.get('Quality')
            OutputFileName = self.GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution, ContainerType, CrfValue)

            # In-place output: put encoded file next to the source.
            OutputDirectory = LocalDirname(InputPath)
            OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

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

            MaxCpuThreads = CommandData.get('MaxCpuThreads')
            if MaxCpuThreads:
                CommandParts.extend(['-threads', str(MaxCpuThreads)])

            # Add parameters using CodecParameters database values
            self.AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)
            
            if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                CommandParts.extend(['-c:a', 'copy'])
            else:
                ProfilePinnedCodec = ProfileSettings.get('AudioCodec')
                if ProfilePinnedCodec:
                    CommandParts.extend(['-c:a', str(ProfilePinnedCodec)])
                    PinnedChannels = ProfileSettings.get('AudioChannels')
                    if PinnedChannels is not None:
                        CommandParts.extend(['-ac', str(int(PinnedChannels))])
                    PinnedBitrate = ProfileSettings.get('AudioBitrateKbps')
                    if PinnedBitrate is not None:
                        CommandParts.extend(['-b:a', f'{int(PinnedBitrate)}k'])
                    PinnedAudioFilter = ProfileSettings.get('AudioFilter')
                    if PinnedAudioFilter:
                        CommandParts.extend(['-af', f'"{PinnedAudioFilter}"'])
                else:
                    ProfileAudioBitrate = ProfileSettings.get('AudioBitrateKbps')
                    try:
                        ProfileAudioBitrate = int(ProfileAudioBitrate) if ProfileAudioBitrate not in (None, '', 'None') else 0
                    except (TypeError, ValueError):
                        ProfileAudioBitrate = 0
                    CommandParts.extend(self.BuildAudioCodecArgs(MediaFile, ProfileAudioBitrate))
                    AudioFilter = self.BuildAudioFilters(MediaFile)
                    if AudioFilter:
                        CommandParts.extend(['-af', f'"{AudioFilter}"'])
            
            # Add video filters (deinterlacing only for interlaced sources, plus scaling)
            RawInterlaced = getattr(MediaFile, 'IsInterlaced', None) if MediaFile else None
            IsInterlaced = str(RawInterlaced).strip().lower() in ('1', 'true', 'yes', 't') if RawInterlaced is not None else False
            VideoFilter = self.BuildVideoFilters(ProfileSettings, ScaleFilter, IsInterlaced)
            if VideoFilter:
                CommandParts.extend(['-vf', f'"{VideoFilter}"'])
            
            # Add film grain parameter after video filters
            self.AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add pixel format parameter for 10-bit encoding
            self.AddPixelFormatParameter(CommandParts, CodecParameters, ProfileSettings)
            
            EffectiveContainer = (ProfileSettings.get('Container') if 'ProfileSettings' in dir() and ProfileSettings else None) or ContainerType
            EffectiveContainer = (EffectiveContainer or '').lower()
            if EffectiveContainer:
                CommandParts.extend(['-f', EffectiveContainer])
            ProfileFastStart = ProfileSettings.get('FastStart') if 'ProfileSettings' in dir() and ProfileSettings else None
            if ProfileFastStart is True:
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
            JobId = getattr(Job, 'Id', None)
            FilePath = getattr(Job, 'FilePath', None)
            LoggingService.LogException(
                f"CommandBuilder._BuildTranscodeShape failed (JobId={JobId}, FilePath={FilePath})",
                e, "_BuildTranscodeShape", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """NVENC knobs read from ProfileSettings per directive (no literals)."""
        try:
            ParamLookup = {}
            for param in CodecParameters:
                ParamLookup[param['ParameterName']] = param

            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)

            if UseNvidiaHardware == 1:
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    CommandParts.extend(['-preset', f'p{Preset}'])

                Tune = ProfileSettings.get('Tune')
                if Tune:
                    CommandParts.extend(['-tune', str(Tune)])

                Multipass = ProfileSettings.get('Multipass')
                if Multipass:
                    CommandParts.extend(['-multipass', str(Multipass)])

                CommandParts.extend(['-rc', 'vbr'])

                RateControlMode = (ProfileSettings.get('RateControlMode') or 'cq').lower()
                if RateControlMode == 'vbr':
                    SrcKbps = ProfileSettings.get('SourceVideoBitrateKbps')
                    Pct = ProfileSettings.get('SourceBitratePercent')
                    MinKbps = ProfileSettings.get('MinBitrateKbps')
                    MaxKbps = ProfileSettings.get('MaxBitrateKbps')
                    Multiplier = ProfileSettings.get('MaxBitrateMultiplier')
                    if not SrcKbps or float(SrcKbps) <= 0:
                        raise ValueError(
                            f"VBR profile cannot encode: source VideoBitrateKbps missing or zero (SrcKbps={SrcKbps})."
                        )
                    if not Pct or float(Pct) <= 0:
                        raise ValueError(
                            f"VBR profile missing SourceBitratePercent on ProfileThresholds (got {Pct})."
                        )
                    if not Multiplier or float(Multiplier) <= 0:
                        raise ValueError(
                            f"VBR profile missing MaxBitrateMultiplier on ProfileThresholds (got {Multiplier})."
                        )
                    Calc = int(round(float(SrcKbps) * float(Pct) / 100.0))
                    if MinKbps is not None:
                        Calc = max(Calc, int(MinKbps))
                    if MaxKbps is not None:
                        Calc = min(Calc, int(MaxKbps))
                    MaxRate = int(round(Calc * float(Multiplier)))
                    CommandParts.extend([
                        '-b:v', f'{Calc}k',
                        '-maxrate:v', f'{MaxRate}k',
                        '-bufsize:v', f'{MaxRate}k',
                    ])
                else:
                    CommandParts.extend(['-b:v', '0'])
                    Quality = ProfileSettings.get('Quality')
                    if Quality is not None and Quality != '' and Quality != 'None':
                        CommandParts.extend(['-cq', str(Quality)])

                CommandParts.extend(['-spatial-aq', '1', '-temporal-aq', '1'])
                AqStrength = ProfileSettings.get('AqStrength')
                if AqStrength is not None:
                    CommandParts.extend(['-aq-strength', str(int(AqStrength))])

                RcLookahead = ProfileSettings.get('RcLookahead')
                if RcLookahead is not None:
                    CommandParts.extend(['-rc-lookahead', str(int(RcLookahead))])

                BFrames = ProfileSettings.get('BFrames')
                if BFrames is not None:
                    CommandParts.extend(['-bf', str(int(BFrames))])

                BRefMode = ProfileSettings.get('BRefMode')
                if BRefMode:
                    CommandParts.extend(['-b_ref_mode', str(BRefMode)])

                Gop = ProfileSettings.get('Gop')
                if Gop is not None and Gop != '' and Gop != 'None':
                    CommandParts.extend(['-g', str(int(Gop))])
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
            LoggingService.LogException(
                "Error adding codec parameters -- transcode will run with partial/default settings",
                e, "AddCodecParameters", "CommandBuilder"
            )
    
    # directive: mv-suffix-greedy-collapse
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
    
    # directive: mv-suffix-greedy-collapse
    def AddPixelFormatParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Emit `-pix_fmt <Profiles.PixelFormat>` -- NVENC AV1 wants p010le, SVT-AV1 wants yuv420p10le; mismatch routes through filter-graph autoconvert and can drift color-range handling."""
        try:
            PixFmt = ProfileSettings.get('PixelFormat')
            if PixFmt:
                CommandParts.extend(['-pix_fmt', str(PixFmt)])

        except Exception as e:
            LoggingService.LogException(
                "Error adding pixel format parameter -- transcode will fall back to encoder default",
                e, "AddPixelFormatParameter", "CommandBuilder"
            )

    # directive: mv-suffix-greedy-collapse
    def GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4', CrfValue: int = None) -> str:
        """Generate `<basename>[-resolution]-mv.<ext>.inprogress` -- canonical MediaVortex output marker per worker-lifecycle.feature.md C6. CrfValue kept for back-compat but no longer embedded in name."""
        try:
            import ntpath as _ntpath
            OriginalFileName = _ntpath.basename(_ntpath.basename(OriginalFileName or ''))
            BaseName = os.path.splitext(OriginalFileName)[0]
            BaseName = self._CollapseMvSuffix(BaseName)

            if SourceResolution == TargetResolution:
                return f"{BaseName}-mv.{ContainerType}.inprogress"

            SourceResolutionStr = self.ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
                return f"{BaseName}{TargetResolutionStr}-mv.{ContainerType}.inprogress"

            TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
            NewBaseName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            NewBaseName = os.path.splitext(NewBaseName)[0]
            NewBaseName = self._CollapseMvSuffix(NewBaseName)

            return f"{NewBaseName}-mv.{ContainerType}.inprogress"

        except Exception:
            BaseName = os.path.splitext(OriginalFileName)[0]
            BaseName = self._CollapseMvSuffix(BaseName)
            return f"{BaseName}-mv.{ContainerType}.inprogress"
    
    # directive: mv-suffix-greedy-collapse
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
    
    # directive: mv-suffix-greedy-collapse
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
    
    # directive: mv-suffix-greedy-collapse, legacy-audio-damage-accounting | # see legacy-audio-damage-accounting.C5
    def BuildAudioFilters(self, MediaFile) -> Optional[str]:
        """Build the linear-loudnorm audio filter per linear-loudnorm.feature.md. Returns None when AudioNormalizationEnabled is off; raises RuntimeError when measurements missing or peak is ungainable (defense in depth -- the queue admission gate should have held the file)."""
        from Repositories.DatabaseManager import DatabaseManager
        Db = DatabaseManager()

        AudioNormalizationEnabled = Db.GetSystemSetting('AudioNormalizationEnabled')
        if not (AudioNormalizationEnabled
                and AudioNormalizationEnabled.lower() in ('1', 'true', 'yes')):
            return None  # operator kill switch

        I_Lufs = getattr(MediaFile, 'SourceIntegratedLufs', None)
        L_Lu = getattr(MediaFile, 'SourceLoudnessRangeLU', None)
        P_Dbtp = getattr(MediaFile, 'SourceTruePeakDbtp', None)
        T_Lufs = getattr(MediaFile, 'SourceIntegratedThresholdLufs', None)

        Missing = [
            Name for Name, Val in (
                ('SourceIntegratedLufs', I_Lufs),
                ('SourceLoudnessRangeLU', L_Lu),
                ('SourceTruePeakDbtp', P_Dbtp),
                ('SourceIntegratedThresholdLufs', T_Lufs),
            ) if Val is None
        ]
        if Missing:
            MfId = getattr(MediaFile, 'Id', None)
            raise RuntimeError(
                f"BuildAudioFilters: loudnorm requested for MediaFileId={MfId} "
                f"but measurements missing: {', '.join(Missing)}. The admission "
                f"gate in QueueManagementBusinessService should have deferred "
                f"this file with AdmissionDeferReason="
                f"'awaiting_loudness_measurement' or 'loudness_measurement_failed'."
            )

        TargetI = int(Db.GetSystemSetting('TargetLoudness') or -23)
        TargetTp = int(Db.GetSystemSetting('TruePeak') or -2)
        Floor = int(Db.GetSystemSetting('MinimumLoudnessRangeLU') or 11)
        TargetLra = max(float(L_Lu), float(Floor))

        Gain = float(TargetI) - float(I_Lufs)
        PredictedPeak = float(P_Dbtp) + Gain
        LinearOk = PredictedPeak <= float(TargetTp)

        MeasuredArgs = (
            f"measured_I={float(I_Lufs):.2f}"
            f":measured_LRA={float(L_Lu):.2f}"
            f":measured_TP={float(P_Dbtp):.2f}"
            f":measured_thresh={float(T_Lufs):.2f}"
        )
        Common = (
            f"loudnorm=I={TargetI}:LRA={TargetLra:.2f}:TP={TargetTp}"
            f":{MeasuredArgs}"
        )

        if not LinearOk:
            MfId = getattr(MediaFile, 'Id', None)
            raise RuntimeError(
                f"BuildAudioFilters: ungainable peak for MediaFileId={MfId} "
                f"(SourceIntegratedLufs={float(I_Lufs):.2f}, gain={Gain:+.2f} dB, "
                f"predicted_peak={PredictedPeak:+.2f} dBTP > target_TP={TargetTp} dBTP). "
                f"The admission gate in QueueManagementBusinessService should have deferred "
                f"this file with AdmissionDeferReason='ungainable_peak'. "
                f"linear-loudnorm.feature.md: 'Linear or refused -- never quietly different.'"
            )

        Filter = f"{Common}:linear=true"
        LoggingService.LogInfo(
            f"linear loudnorm: gain={Gain:+.2f} dB, "
            f"target_LRA={TargetLra:.2f} (source {float(L_Lu):.2f}), "
            f"MediaFileId={getattr(MediaFile, 'Id', None)}",
            "CommandBuilder", "BuildAudioFilters",
        )
        return Filter

    # directive: mv-suffix-greedy-collapse
    def BuildVideoFilters(self, ProfileSettings: Dict[str, Any], ScaleFilter: Optional[str], IsInterlaced: bool = False) -> Optional[str]:
        """Build video filter string. Yadif applied only when source is interlaced."""
        Filters = []

        if IsInterlaced:
            Filters.append("yadif=1:1:1")

        # Add scale filter if provided
        if ScaleFilter:
            Filters.append(ScaleFilter)

        # Return combined filters or None if no filters
        return ','.join(Filters) if Filters else None
    
    MP4_COMPATIBLE_AUDIO = ('aac', 'ac3', 'eac3', 'mp3')

    _AUDIO_DEFAULT_BITRATE_BY_CHANNELS = {
        1: 96,   # mono
        2: 128,  # stereo
        6: 256,  # 5.1
        8: 384,  # 7.1
    }

    @classmethod
    # directive: mv-suffix-greedy-collapse
    def _DefaultAudioBitrateForChannels(cls, Channels: Optional[int]) -> int:
        if not Channels or Channels < 1:
            return 128
        # Round up to the nearest known channel count
        for Threshold in sorted(cls._AUDIO_DEFAULT_BITRATE_BY_CHANNELS.keys()):
            if Channels <= Threshold:
                return cls._AUDIO_DEFAULT_BITRATE_BY_CHANNELS[Threshold]
        return 384

    # directive: mv-suffix-greedy-collapse
    def BuildAudioCodecArgs(self, MediaFile, ProfileBitrate: Optional[int]) -> list:
        """Resolve `-c:a / -b:a` args per the audio re-encode policy in command-builder.feature.md (Audio re-encode policy section). MP4-compat source codec -> same codec preserving channels+bitrate; mp3 -> aac; anything else -> eac3."""
        SourceCodec = (getattr(MediaFile, 'AudioCodec', None) or '').lower()
        SourceChannels = getattr(MediaFile, 'AudioChannels', None)
        SourceBitrate = getattr(MediaFile, 'AudioBitrateKbps', None)
        OperatorOverride = bool(ProfileBitrate)  # 0 / None / '' -> use source

        if SourceCodec in ('aac', 'ac3', 'eac3'):
            Bitrate = ProfileBitrate if OperatorOverride else (
                SourceBitrate or self._DefaultAudioBitrateForChannels(SourceChannels)
            )
            return ['-c:a', SourceCodec, '-b:a', f'{Bitrate}k']

        if SourceCodec == 'mp3':
            Bitrate = ProfileBitrate if OperatorOverride else (
                SourceBitrate or self._DefaultAudioBitrateForChannels(SourceChannels)
            )
            return ['-c:a', 'aac', '-b:a', f'{Bitrate}k']

        Bitrate = ProfileBitrate if OperatorOverride else self._DefaultAudioBitrateForChannels(SourceChannels)
        return ['-c:a', 'eac3', '-b:a', f'{Bitrate}k']

    # directive: mv-suffix-greedy-collapse
    def _BuildRemuxShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Remux shape: -c:v copy + audio (branch on AudioComplete) + container. Output ends `.inprogress` per worker-lifecycle.feature.md C6. Refuses if OutputPath would collide with InputPath (collision = -y overwrite risk)."""
        try:
            CommandData = Context
            InputPath = self._NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            # Pre-flight FFprobe to detect audio stream / codec / presence
            if 'AudioStreamIndex' not in CommandData or 'HasAudio' not in CommandData:
                Analysis = self._RunFFprobeAnalysis(InputPath, CommandData.get('FFprobePath'))
                DetectedAudioCodec = Analysis.AudioCodec if Analysis and Analysis.AudioCodec else ''
                if 'AudioStreamIndex' not in CommandData and Analysis and Analysis.AudioStreamIndex is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex
                if 'HasAudio' not in CommandData:
                    CommandData['HasAudio'] = bool(DetectedAudioCodec)
            AudioCodec = CommandData.get('AudioCodec', '')
            BaseName = os.path.splitext(MediaFile.FileName)[0]
            BaseName = self._CollapseMvSuffix(BaseName)

            ExplicitOutputPath = CommandData.get('OutputPath')
            if ExplicitOutputPath:
                OutputPath = self._NormalizeFfmpegPath(ExplicitOutputPath)
            else:
                OutputFileName = BaseName + "-mv.mp4.inprogress"
                OutputDirectory = LocalDirname(InputPath)
                OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            if LocalSamePath(OutputPath, InputPath):
                LoggingService.LogError(
                    f"_BuildRemuxShape: OutputPath equals InputPath ({InputPath}). "
                    f"OutputPath must be a `.inprogress` side-by-side file.",
                    "CommandBuilder", "_BuildRemuxShape"
                )
                return None

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the command builder.")
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # Stream mapping: always map video; only map audio if the source has an audio stream.
            HasAudio = CommandData.get('HasAudio', True)
            CommandParts.extend(['-map', '0:v:0'])
            if HasAudio:
                AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
                CommandParts.extend(['-map', f'0:a:{AudioStreamIndex}'])

            # Video: always copy (no re-encode)
            CommandParts.extend(['-c:v', 'copy'])

            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            if HasAudio:
                if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                    SourceCodec = (getattr(MediaFile, 'AudioCodec', '') or '').lower()
                    if SourceCodec and SourceCodec not in AudioCompletionService.MP4_COMPAT_AUDIO_CODECS:
                        MediaFileId = getattr(MediaFile, 'Id', None)
                        LoggingService.LogError(
                            f"_BuildRemuxShape: AudioComplete=true but AudioCodec={SourceCodec!r} "
                            f"is not MP4-stream-copy-compatible (MediaFileId={MediaFileId}). "
                            f"Flagging AudioCorruptSuspect=true and refusing the command.",
                            "CommandBuilder", "_BuildRemuxShape"
                        )
                        if MediaFileId is not None:
                            AudioCompletionService.MarkAudioCorruptSuspect(
                                MediaFileId,
                                AudioCompletionService.REASON_INCOMPATIBLE_CODEC_UNSUPPORTED,
                            )
                        return None
                    CommandParts.extend(['-c:a', 'copy'])
                else:
                    CommandParts.extend(self.BuildAudioCodecArgs(MediaFile, ProfileBitrate=0))
                    AudioFilter = self.BuildAudioFilters(MediaFile)
                    if AudioFilter:
                        CommandParts.extend(['-af', f'"{AudioFilter}"'])

            ContainerType = ProfileSettings.get('Container') if 'ProfileSettings' in dir() and ProfileSettings else None
            EffectiveContainer = (ContainerType or '').lower()
            if EffectiveContainer:
                CommandParts.extend(['-f', EffectiveContainer])
            ProfileFastStart = ProfileSettings.get('FastStart') if 'ProfileSettings' in dir() and ProfileSettings else None
            if ProfileFastStart is True:
                CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return {
                'Command': ' '.join(CommandParts),
                'OutputPath': OutputPath
            }

        except Exception as e:
            LoggingService.LogException(
                f"CommandBuilder._BuildRemuxShape failed (JobId={getattr(Job, 'Id', None)})",
                e, "_BuildRemuxShape", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
    def _BuildSubtitleFixShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Subtitle-fix shape: -c:v copy + audio (branch on AudioComplete) + ASS/SSA -> mov_text + container. Output ends `<basename>-mv.mp4.inprogress` per worker-lifecycle.feature.md C6."""
        try:
            CommandData = Context
            InputPath = self._NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            # Pre-flight FFprobe to detect audio + subtitle streams
            if 'AudioStreamIndex' not in CommandData or 'SubtitleStreamIndex' not in CommandData:
                Analysis = self._RunFFprobeAnalysis(InputPath, CommandData.get('FFprobePath'))
                if 'AudioStreamIndex' not in CommandData and Analysis and Analysis.AudioStreamIndex is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex
                if 'SubtitleStreamIndex' not in CommandData and Analysis and Analysis.SubtitleStreamIndex is not None:
                    CommandData['SubtitleStreamIndex'] = Analysis.SubtitleStreamIndex
                if Analysis and Analysis.AudioCodec and 'AudioCodec' not in CommandData:
                    CommandData['AudioCodec'] = Analysis.AudioCodec
            AudioCodec = CommandData.get('AudioCodec', '')
            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            SubtitleStreamIndex = CommandData.get('SubtitleStreamIndex', 0)
            BaseName = os.path.splitext(MediaFile.FileName)[0]
            BaseName = self._CollapseMvSuffix(BaseName)

            ExplicitOutputPath = CommandData.get('OutputPath')
            if ExplicitOutputPath:
                OutputPath = self._NormalizeFfmpegPath(ExplicitOutputPath)
            else:
                OutputFileName = BaseName + "-mv.mp4.inprogress"
                OutputDirectory = LocalDirname(InputPath)
                OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            if LocalSamePath(OutputPath, InputPath):
                LoggingService.LogError(
                    f"_BuildSubtitleFixShape: OutputPath equals InputPath ({InputPath}). "
                    f"OutputPath must be a `.inprogress` side-by-side file.",
                    "CommandBuilder", "_BuildSubtitleFixShape"
                )
                return None

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the command builder.")
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # Map video, preferred audio, and preferred subtitle streams
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}', '-map', f'0:s:{SubtitleStreamIndex}'])

            # Video: copy (no re-encode)
            CommandParts.extend(['-c:v', 'copy'])

            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                CommandParts.extend(['-c:a', 'copy'])
            else:
                CommandParts.extend(self.BuildAudioCodecArgs(MediaFile, ProfileBitrate=0))
                AudioFilter = self.BuildAudioFilters({})
                if AudioFilter:
                    CommandParts.extend(['-af', f'"{AudioFilter}"'])

            # Subtitle: convert to mov_text (MP4-native text format)
            CommandParts.extend(['-c:s', 'mov_text'])

            ContainerType = ProfileSettings.get('Container') if 'ProfileSettings' in dir() and ProfileSettings else None
            EffectiveContainer = (ContainerType or '').lower()
            if EffectiveContainer:
                CommandParts.extend(['-f', EffectiveContainer])
            ProfileFastStart = ProfileSettings.get('FastStart') if 'ProfileSettings' in dir() and ProfileSettings else None
            if ProfileFastStart is True:
                CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return {
                'Command': ' '.join(CommandParts),
                'OutputPath': OutputPath
            }

        except Exception as e:
            LoggingService.LogException(
                f"CommandBuilder._BuildSubtitleFixShape failed (JobId={getattr(Job, 'Id', None)})",
                e, "_BuildSubtitleFixShape", "CommandBuilder"
            )
            return None

    # directive: mv-suffix-greedy-collapse
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
