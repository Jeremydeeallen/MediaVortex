import os
from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Features.AudioCompletion.AudioCompletionService import AudioCompletionService


class CommandBuilder:
    """Pure data transformation model for building FFmpeg transcoding commands."""

    @staticmethod
    def _CollapseMvSuffix(BaseName: str) -> str:
        """Strip a trailing `-mv` from `BaseName` so re-transcoding a
        `<name>-mv.<ext>` source produces `<name>-mv.<output-ext>` instead
        of `<name>-mv-mv.<output-ext>`. Owned by `compliance-gated-rename.feature.md`
        criterion 7 (BUG-0020 Slice 1). The same-path collision created by
        this stripping is handled in
        `FileReplacementBusinessService._ProcessCompleteFileReplacement`'s
        same-slot-replacement branch.
        """
        if BaseName and BaseName.lower().endswith('-mv'):
            return BaseName[:-3]
        return BaseName

    @staticmethod
    def _NormalizeFfmpegPath(Path: Optional[str]) -> str:
        """Collapse mixed separators to the platform-native form.

        Required because PathStorage.Resolve composes a backslash drive prefix
        with a forward-slash relative portion (cross-platform-safe internal
        representation), and downstream os.path.join then adds another OS-native
        separator before the basename. On Windows FFmpeg some builds reject the
        resulting `T:\\Show/Season\\file.mkv` shape with AVERROR(EINVAL) = -22.

        os.path.normpath also strips trailing slashes and surrounding whitespace
        once we strip the optional quotes the caller may have wrapped earlier.
        Pure transformation -- no filesystem touch.
        """
        if not Path:
            return Path
        return os.path.normpath(Path.strip().strip('"'))

    @classmethod
    def BuildFFmpegCommand(cls, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Single public entry point. Decides command shape from Job state.

        Cascade (Features/CommandBuilder/command-builder.feature.md criterion 2):
          Job.IsSubtitleFix  -> subtitle-fix shape (subtitle convert + remux + audio)
          Job.IsRemux        -> remux shape (-c:v copy + remux + audio)
          else (Transcode)   -> transcode shape (video re-encode + remux + audio)

        Args:
            MediaFile: source state (AudioComplete, AudioCodec, Resolution, etc.)
            Job: queue row whose ProcessingMode selects dispatch
            Context: operational data the model doesn't know about. Required keys:
                FFmpegPath. Optional: FFprobePath, InputPath, OutputPath,
                OutputDirectory, MaxCpuThreads, AudioStreamIndex,
                ProfileSettings, CodecFlags, CodecParameters, SourceResolution,
                StartTime. The shape methods pull what they need.

        Returns {Command, OutputPath} dict or None on failure.
        """
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

    def _RunFFprobeAnalysis(self, InputPath: str, FFprobePath: Optional[str]):
        """Pre-flight FFprobe for stream selection. Returns analysis object or None.

        Used by remux/subtitle-fix shapes to detect AudioStreamIndex, AudioCodec,
        SubtitleStreamIndex without re-probing logic in callers. Cheap because
        FFprobe only reads headers.
        """
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

    def _CalculateTargetResolution(self, ProfileSettings: Dict[str, Any], SourceResolution: str) -> str:
        Target = ProfileSettings.get('TargetResolution')
        return Target if Target else SourceResolution

    def _CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str, MediaFile) -> Optional[str]:
        """Compute -vf scale filter when down-scaling; None when no scaling needed."""
        try:
            if SourceResolution == TargetResolution:
                return None
            from Services.ResolutionService import ResolutionService
            ResolutionServiceInstance = ResolutionService()
            StandardizedTarget = ResolutionServiceInstance.StandardizeResolution(TargetResolution)
            TargetHeight = self._ExtractHeightFromResolution(StandardizedTarget)
            StandardTargetHeight = ResolutionServiceInstance.GetStandardHeight(TargetHeight)
            SourceWidth, SourceHeight = self._GetSourceDimensions(MediaFile)
            if SourceHeight <= 0:
                return None
            SourceAspectRatio = SourceWidth / SourceHeight
            TargetWidth = self._CalculateWidthFromHeight(StandardTargetHeight, SourceAspectRatio)
            return f"scale={TargetWidth}:{StandardTargetHeight}"
        except Exception as e:
            LoggingService.LogException(
                "Exception calculating scale filter", e, "_CalculateScaleFilter", "CommandBuilder"
            )
            return None

    def _ExtractHeightFromResolution(self, Resolution: str) -> int:
        try:
            if Resolution.endswith('p'):
                return int(Resolution[:-1])
            if 'x' in Resolution:
                return int(Resolution.split('x')[1])
            return int(Resolution)
        except (ValueError, IndexError):
            return 720

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

    def _BuildTranscodeShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Transcode shape: video re-encode + audio (branch on AudioComplete) + container.

        Heaviest path. Subsumes remux + audio fix as side-effects of the
        single FFmpeg pass.
        """
        try:
            CommandData = Context  # legacy alias; existing code paths read from it
            ProfileSettings = CommandData.get('ProfileSettings', {})
            CodecFlags = CommandData.get('CodecFlags', {})
            CodecParameters = CommandData.get('CodecParameters', [])
            SourceResolution = CommandData.get('SourceResolution') or getattr(MediaFile, 'Resolution', '') or ''
            TargetResolution = CommandData.get('TargetResolution') or self._CalculateTargetResolution(ProfileSettings, SourceResolution)
            ScaleFilter = CommandData.get('ScaleFilter')
            if ScaleFilter is None and TargetResolution and SourceResolution and TargetResolution != SourceResolution:
                ScaleFilter = self._CalculateScaleFilter(SourceResolution, TargetResolution, MediaFile)
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
            OutputDirectory = os.path.dirname(InputPath)
            OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

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
            
            # Audio: branch on AudioComplete. If the file's audio has already
            # been through the one-shot normalize pass (or is suspect), copy
            # bytes through unchanged. Otherwise apply source-preserving
            # re-encode + loudnorm/acompressor -- the first and last time we
            # touch this file's audio.
            if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                CommandParts.extend(['-c:a', 'copy'])
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
            IsInterlaced = str(RawInterlaced) == '1' if RawInterlaced is not None else False
            VideoFilter = self.BuildVideoFilters(ProfileSettings, ScaleFilter, IsInterlaced)
            if VideoFilter:
                CommandParts.extend(['-vf', f'"{VideoFilter}"'])
            
            # Add film grain parameter after video filters
            self.AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add pixel format parameter for 10-bit encoding
            self.AddPixelFormatParameter(CommandParts, CodecParameters, ProfileSettings)
            
            # Add container-specific flags. -f mp4 is REQUIRED because the
            # output filename ends `.mp4.inprogress` (worker-lifecycle C6) --
            # FFmpeg's extension-based muxer detection fails on `.inprogress`
            # and exits with AVERROR(EINVAL). See BUG-0005.
            if ContainerType.lower() == 'mp4':
                CommandParts.extend(['-f', 'mp4', '-movflags', '+faststart'])
            
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
                # NVENC quality knob set from the 2026-05-28 shootout
                # (Scripts/Smoke/EncoderShootout.feature.md, nv_cq32_sink: -14% size
                # vs SVT P6 CRF26 reference at -0.47 VMAF, ~1.6x faster). Profile
                # contributes Preset + Quality; the rest are fixed to the winning
                # config until a future test motivates per-profile variation.
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    CommandParts.extend(['-preset', f'p{Preset}'])
                CommandParts.extend([
                    '-tune', 'uhq',
                    '-multipass', 'fullres',
                    '-rc', 'vbr',
                    '-b:v', '0',
                ])
                Quality = ProfileSettings.get('Quality')
                if Quality is not None and Quality != '' and Quality != 'None':
                    CommandParts.extend(['-cq', str(Quality)])
                CommandParts.extend([
                    '-spatial-aq', '1',
                    '-temporal-aq', '1',
                    '-aq-strength', '15',
                    '-rc-lookahead', '32',
                    '-bf', '7',
                    '-b_ref_mode', 'middle',
                ])
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
        """Add pixel format parameter for 10-bit encoding.

        NVENC AV1 takes p010le (semi-planar 10-bit); SVT-AV1 takes yuv420p10le
        (planar 10-bit). Mixing them works via filter-graph autoconvert but
        wastes a copy and can subtly alter color-range handling -- match the
        encoder's native format.
        """
        try:
            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
            PixFmt = 'p010le' if UseNvidiaHardware == 1 else 'yuv420p10le'
            CommandParts.extend(['-pix_fmt', PixFmt])

        except Exception as e:
            LoggingService.LogException(
                "Error adding pixel format parameter -- transcode will fall back to encoder default",
                e, "AddPixelFormatParameter", "CommandBuilder"
            )

    def GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4', CrfValue: int = None) -> str:
        """Generate the staged output filename: <basename>[-resolution]-mv.<ext>.inprogress.

        The `-mv` suffix is the canonical "MediaVortex transcoded this" marker.
        The `.inprogress` suffix marks a work-in-progress encode; FileReplacement
        renames to drop the suffix once the file is verified. See
        worker-lifecycle.feature.md criterion 6.

        CrfValue parameter is accepted for backwards compatibility but no longer
        embedded in filenames -- CRF is tracked in the TranscodeAttempts table.
        """
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
    
    def BuildAudioFilters(self, MediaFile) -> Optional[str]:
        """Build the linear-loudnorm audio filter for the encode pass.

        Implements the contract defined in
        `Features/LoudnessAnalysis/linear-loudnorm.feature.md` -- one
        filter, linear-mode when fixed gain fits under the TP ceiling,
        dynamic-mode when it does not. No fallback, no `acompressor`,
        no silent degradation.

        Returns:
          - The loudnorm filter string when audio normalization is enabled
            and all four measurements are present.
          - None when `AudioNormalizationEnabled` is off (operator kill
            switch) -- the audio re-encodes via `BuildAudioCodecArgs` with
            no filter.

        Raises:
          - RuntimeError when the file is missing any of the four ebur128
            measurements. This is defense-in-depth -- the queue admission
            gate in `QueueManagementBusinessService._EvaluateCompliance`
            (linear-loudnorm.feature.md C9) should have held the file
            out. Raising here makes the bug loud instead of silently
            degrading to a guessed command.
        """
        from Repositories.DatabaseManager import DatabaseManager
        Db = DatabaseManager()

        AudioNormalizationEnabled = Db.GetSystemSetting('AudioNormalizationEnabled')
        if not (AudioNormalizationEnabled
                and AudioNormalizationEnabled.lower() in ('1', 'true', 'yes')):
            return None  # operator kill switch

        # Measurements -- all four required for linear or dynamic mode.
        # Defense-in-depth: admission gate should have prevented this.
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

        # Predicted peak after fixed gain. If it exceeds the TP ceiling,
        # linear mode is impossible -- switch to dynamic mode (loudnorm
        # compresses the range to honor the peak target).
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

        if LinearOk:
            Filter = f"{Common}:linear=true"
            LoggingService.LogInfo(
                f"linear loudnorm: gain={Gain:+.2f} dB, "
                f"target_LRA={TargetLra:.2f} (source {float(L_Lu):.2f}), "
                f"MediaFileId={getattr(MediaFile, 'Id', None)}",
                "CommandBuilder", "BuildAudioFilters",
            )
        else:
            # BUG-0014: loudnorm's dynamic-mode internal limiter does not
            # reliably enforce TP -- observed overshoot of +1 to +3 dBTP on
            # quiet-but-peaky sources. Chain a sample-peak alimiter after
            # loudnorm with 2 dB headroom under TargetTruePeak and a 1ms
            # attack so transient peaks get clamped before they ride
            # through. First-iteration value of -1 dB / 5ms attack landed
            # Doctor Who S06E04 output at -1.6 dBTP (criterion 26 needs
            # <= -2 dBTP) -- the 5ms default attack let individual sample
            # transients leak above the threshold. level=0 disables
            # alimiter's autoleveling so loudnorm's integrated target is
            # preserved; alimiter only acts when peaks would otherwise
            # exceed the ceiling.
            SafetyDb = float(TargetTp) - 2.0
            SafetyLinear = 10.0 ** (SafetyDb / 20.0)
            Filter = f"{Common},alimiter=limit={SafetyLinear:.4f}:attack=1:level=0"
            LoggingService.LogInfo(
                f"dynamic loudnorm: ungainable peak (would clip at "
                f"{PredictedPeak:+.2f} dBTP), target_LRA={TargetLra:.2f} "
                f"(source {float(L_Lu):.2f}), TP-safety alimiter at "
                f"{SafetyDb:+.1f} dBFS with 1ms attack, "
                f"MediaFileId={getattr(MediaFile, 'Id', None)}",
                "CommandBuilder", "BuildAudioFilters",
            )

        return Filter

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
    
    # MP4-compatible audio codecs (we re-encode to the same codec to keep
    # source format/channels through the loudnorm decode-filter-encode pass).
    MP4_COMPATIBLE_AUDIO = ('aac', 'ac3', 'eac3', 'mp3')

    # Channel-aware default bitrates when source bitrate is missing or the
    # source codec is being replaced (DTS/FLAC/TrueHD/PCM -> EAC3).
    _AUDIO_DEFAULT_BITRATE_BY_CHANNELS = {
        1: 96,   # mono
        2: 128,  # stereo
        6: 256,  # 5.1
        8: 384,  # 7.1
    }

    @classmethod
    def _DefaultAudioBitrateForChannels(cls, Channels: Optional[int]) -> int:
        if not Channels or Channels < 1:
            return 128
        # Round up to the nearest known channel count
        for Threshold in sorted(cls._AUDIO_DEFAULT_BITRATE_BY_CHANNELS.keys()):
            if Channels <= Threshold:
                return cls._AUDIO_DEFAULT_BITRATE_BY_CHANNELS[Threshold]
        return 384

    def BuildAudioCodecArgs(self, MediaFile, ProfileBitrate: Optional[int]) -> list:
        """Resolve `-c:a / -b:a` args for the loudnorm-aware re-encode pass.

        Policy (chosen 2026-05-10, replaces forced AAC stereo):
        - Operator override: if ProfileBitrate is non-zero, treat the profile
          as authoritative for bitrate. Codec/channels still match source per
          MP4-compatibility rules below.
        - MP4-compatible source codec (aac/ac3/eac3/mp3): re-encode to same
          codec, preserve channel count (no `-ac` flag), match source bitrate
          when known. Channel-aware default fallback when source bitrate is
          NULL.
        - mp3 source: convert to aac (more universal in MP4) preserving
          channels and bitrate.
        - Anything else (dts/flac/truehd/pcm/unknown): re-encode to eac3 with
          channel-aware default bitrate. EAC3 fits MP4 and supports up to 7.1.

        Note: no `-ac` flag is emitted -- FFmpeg defaults to source channel
        count, which is what we want. The previous forced `-ac 2` downmix
        was removed deliberately.
        """
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

        # Lossless / unknown -> EAC3 preserving channels, channel-aware default
        # (source bitrate is meaningless for lossless inputs).
        Bitrate = ProfileBitrate if OperatorOverride else self._DefaultAudioBitrateForChannels(SourceChannels)
        return ['-c:a', 'eac3', '-b:a', f'{Bitrate}k']

    def _BuildRemuxShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Remux shape: -c:v copy + audio (branch on AudioComplete) + container.

        Quick path. Handles container fix and/or audio normalize in one pass.
        OutputPath, when supplied by the caller, must end in `.inprogress`.
        The original source is never renamed during processing -- see
        worker-lifecycle.feature.md criterion 6.

        Defense in depth: if OutputPath would equal InputPath (collision),
        refuse to build the command rather than risk a -y overwrite.
        """
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
                OutputDirectory = os.path.dirname(InputPath)
                OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            if os.path.normcase(OutputPath) == os.path.normcase(InputPath):
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

            # Tag HEVC as hvc1 for broad device compatibility (Android TV,
            # Apple, etc.). Only valid for HEVC sources -- applying hvc1 to
            # an h264/avc1 stream causes FFmpeg to refuse the muxing
            # ("Tag hvc1 incompatible with output codec id '27' (avc1)").
            # Pre-2026-05-09 this was unconditional and silently fine because
            # nothing routed h264 sources through remux; the routing cascade
            # changes that.
            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            # Audio: branch on AudioComplete.
            #   AudioComplete=true (or Suspect=true) -> -c:a copy (byte-identical)
            #   AudioComplete=false                  -> one-shot codec convert
            #                                           + loudnorm/acompressor
            #   AudioComplete=true with non-MP4-compat codec is a logic error:
            #   the row claims stream-copy-eligible but the codec cannot be
            #   stream-copied into MP4. Flag suspect and refuse the command.
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

            # MP4 container flags. -f mp4 is REQUIRED because the output
            # filename ends `.mp4.inprogress` -- FFmpeg's auto-detection reads
            # only the last extension, can't find a muxer for `.inprogress`,
            # and exits with AVERROR(EINVAL) = -22 (BUG-0005, 2026-05-18).
            CommandParts.extend(['-f', 'mp4', '-movflags', '+faststart'])
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

    def _BuildSubtitleFixShape(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Subtitle-fix shape: -c:v copy + audio (branch on AudioComplete) + subtitle
        convert (ASS/SSA -> mov_text) + container.

        Specialized variant of the remux shape. OutputPath ends in
        `<basename>-mv.mp4.inprogress` (worker-lifecycle.feature.md criterion 6).
        """
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
                OutputDirectory = os.path.dirname(InputPath)
                OutputPath = self._NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            if os.path.normcase(OutputPath) == os.path.normcase(InputPath):
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

            # Tag HEVC as hvc1 only for actual HEVC sources -- see same
            # comment in BuildRemuxCommand. Applying hvc1 to h264/av1 fails.
            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            # Audio: branch on AudioComplete (same policy as BuildRemuxCommand).
            # See Features/AudioCompletion/audio-completion.flow.md.
            if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                CommandParts.extend(['-c:a', 'copy'])
            else:
                CommandParts.extend(self.BuildAudioCodecArgs(MediaFile, ProfileBitrate=0))
                AudioFilter = self.BuildAudioFilters({})
                if AudioFilter:
                    CommandParts.extend(['-af', f'"{AudioFilter}"'])

            # Subtitle: convert to mov_text (MP4-native text format)
            CommandParts.extend(['-c:s', 'mov_text'])

            # MP4 container flags. -f mp4 is REQUIRED because the output
            # filename ends `.mp4.inprogress` -- FFmpeg's auto-detection reads
            # only the last extension, can't find a muxer for `.inprogress`,
            # and exits with AVERROR(EINVAL) = -22 (BUG-0005, 2026-05-18).
            CommandParts.extend(['-f', 'mp4', '-movflags', '+faststart'])
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
