import os
from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname
from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.AudioNormalization.Policies.IAudioCodecPolicy import EAC3OrPassthroughCodecPolicy
from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
class TranscodeShape(EncodeShape):
    """Builds ffmpeg argv for full video re-encode jobs; audio goes through AudioFilterEmitter (no profile-pinned override)."""

    # directive: audio-pipeline-fail-loud | # see audio-normalization.C8 | # see encode-emit.C12
    def __init__(self, ResolutionCalculator, OutputFilenameBuilder, CodecParameterAssembler,
                 VideoFilterBuilder, MediaProbeAdapter,
                 Resolver=None, Emitter=None, StreamProbe=None, CodecPolicy=None):
        self.ResolutionCalculator = ResolutionCalculator
        self.OutputFilenameBuilder = OutputFilenameBuilder
        self.CodecParameterAssembler = CodecParameterAssembler
        self.VideoFilterBuilder = VideoFilterBuilder
        self.MediaProbeAdapter = MediaProbeAdapter
        self.Resolver = Resolver or AudioPolicyResolver()
        # directive: audio-dialog-boost-real | # see audio-normalization.C8 | # see encode-emit.C12
        self.Emitter = Emitter or AudioFilterEmitter()
        self.StreamProbe = StreamProbe or AudioStreamProbe()
        self.CodecPolicy = CodecPolicy or EAC3OrPassthroughCodecPolicy()

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        """Port of CommandBuilder._BuildTranscodeShape; returns CommandSpec or None on failure."""
        try:
            CommandData = Context
            ProfileSettings = CommandData.get('ProfileSettings', {}) or {}
            CodecParameters = CommandData.get('CodecParameters', []) or []
            SourceResolution = CommandData.get('SourceResolution') or getattr(MediaFile, 'Resolution', '') or ''
            TargetResolution = CommandData.get('TargetResolution') or self.ResolutionCalculator.CalculateTargetResolution(ProfileSettings, SourceResolution)
            ScaleFilter = CommandData.get('ScaleFilter')
            if ScaleFilter is None and TargetResolution and SourceResolution and TargetResolution != SourceResolution:
                ScaleFilter = self.ResolutionCalculator.CalculateScaleFilter(SourceResolution, TargetResolution, MediaFile, ProfileSettings)
            StartTime = CommandData.get('StartTime')
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')

            InputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            if 'AudioStreamIndex' not in CommandData:
                Analysis = self.MediaProbeAdapter.RunAnalysis(InputPath)
                if Analysis and getattr(Analysis, 'AudioStreamIndex', None) is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex

            CrfValue = ProfileSettings.get('Quality')
            OutputFileName = self.OutputFilenameBuilder.GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution, ContainerType, CrfValue)
            OutputDirectory = LocalDirname(InputPath)
            OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the shape.")
            CommandParts = [FFmpegPath]

            if StartTime and StartTime.strip():
                CommandParts.extend(['-ss', StartTime.strip()])
            CommandParts.extend(['-i', f'"{InputPath}"'])

            # directive: audio-dialog-boost-real | # see audio-normalization.C8
            Policy = self.Resolver.GetEffectivePolicy(MediaFile)
            if not Policy:
                raise AudioPolicyUnresolvedError(
                    'PolicyMissing',
                    f'MediaFile.Id={getattr(MediaFile, "Id", None)} has no effective AudioPolicy; refusing legacy stream-copy/ceiling fallback (starvation risk).',
                    None,
                )
            SourceStreams = self.StreamProbe.Probe(CommandData.get('InputPath')) or None
            DemucsPremixPath = CommandData.get('DemucsPremixPath')
            VocalsRmsDbfs = CommandData.get('VocalsRmsDbfs')
            PremixMeasuredI = CommandData.get('PremixMeasuredI')
            PremixMeasuredLra = CommandData.get('PremixMeasuredLra')
            PremixMeasuredTp = CommandData.get('PremixMeasuredTp')
            PremixMeasuredThresh = CommandData.get('PremixMeasuredThresh')
            Blocks = self.Emitter.EmitTracks(
                MediaFile, Policy, AudioStreams=SourceStreams,
                DemucsPremixPath=DemucsPremixPath, VocalsRmsDbfs=VocalsRmsDbfs,
                PremixMeasuredI=PremixMeasuredI, PremixMeasuredLra=PremixMeasuredLra,
                PremixMeasuredTp=PremixMeasuredTp, PremixMeasuredThresh=PremixMeasuredThresh,
            )
            for Block in Blocks:
                if Block.InputArgs:
                    Quoted = []
                    for I in range(0, len(Block.InputArgs), 2):
                        Quoted.append(Block.InputArgs[I])
                        Quoted.append(f'"{Block.InputArgs[I+1]}"')
                    CommandParts.extend(Quoted)

            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            CommandParts.extend(['-map', '0:v:0'])

            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
            VideoCodec = 'av1_nvenc' if UseNvidiaHardware == 1 else ProfileSettings.get('Codec', 'libsvtav1')
            CommandParts.extend(['-c:v', VideoCodec])

            MaxCpuThreads = CommandData.get('MaxCpuThreads')
            if MaxCpuThreads:
                CommandParts.extend(['-threads', str(MaxCpuThreads)])

            self.CodecParameterAssembler.AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)
            if not Blocks:
                # directive: audio-dialog-boost-real | # see audio-normalization.C8
                raise AudioPolicyUnresolvedError(
                    'EmitTracksReturnedEmpty',
                    f'MediaFile.Id={getattr(MediaFile, "Id", None)} produced empty audio Blocks; refusing legacy ProfileAudioCeiling reencode fallback (starvation risk).',
                    None,
                )
            for Block in Blocks:
                CommandParts.extend(Block.MapArgs)
                CommandParts.extend(Block.CodecArgs)
                if Block.FilterArgs:
                    CommandParts.extend(Block.FilterArgs[:1])
                    CommandParts.append(f'"{Block.FilterArgs[1]}"')
                CommandParts.extend(Block.MetadataArgs)
                CommandParts.extend(Block.DispositionArgs)

            RawInterlaced = getattr(MediaFile, 'IsInterlaced', None) if MediaFile else None
            IsInterlaced = str(RawInterlaced).strip().lower() in ('1', 'true', 'yes', 't') if RawInterlaced is not None else False
            VideoFilter = self.VideoFilterBuilder.Build(ProfileSettings, ScaleFilter, IsInterlaced)
            if VideoFilter:
                CommandParts.extend(['-vf', f'"{VideoFilter}"'])

            self.CodecParameterAssembler.AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
            self.CodecParameterAssembler.AddPixelFormatParameter(CommandParts, CodecParameters, ProfileSettings)

            EffectiveContainer = (ProfileSettings.get('Container') or ContainerType or '').lower()
            if EffectiveContainer:
                CommandParts.extend(['-f', EffectiveContainer])
            if ProfileSettings.get('FastStart') is True:
                CommandParts.extend(['-movflags', '+faststart'])

            CommandParts.extend(['-metadata', '"comment=Transcoded by MediaVortex"'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return CommandSpec(Command=' '.join(CommandParts), OutputPath=OutputPath)

        except Exception as Ex:
            JobId = getattr(Job, 'Id', None)
            FilePath = getattr(Job, 'FilePath', None)
            LoggingService.LogException(
                f"TranscodeShape.Build failed (JobId={JobId}, FilePath={FilePath})",
                Ex, "TranscodeShape", "Build",
            )
            return None
