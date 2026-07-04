import os
from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname, LocalSamePath
from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape
from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
class SubtitleFixShape(EncodeShape):
    """Builds ffmpeg argv for subtitle-fix jobs (ASS/SSA -> mov_text); audio goes through AudioFilterEmitter."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
    def __init__(self, OutputFilenameBuilder, AudioCodecArgsBuilder, MediaProbeAdapter,
                 Resolver=None, Emitter=None, StreamProbe=None):
        """Inject collaborators; audio path goes through Resolver + Emitter; StreamProbe enumerates per-language audio streams."""
        self.OutputFilenameBuilder = OutputFilenameBuilder
        self.AudioCodecArgsBuilder = AudioCodecArgsBuilder
        self.MediaProbeAdapter = MediaProbeAdapter
        self.Resolver = Resolver or AudioPolicyResolver()
        self.Emitter = Emitter or AudioFilterEmitter()
        self.StreamProbe = StreamProbe or AudioStreamProbe()

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        """Port of CommandBuilder._BuildSubtitleFixShape with unconditional -f mp4 + faststart."""
        try:
            CommandData = Context
            InputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            if 'AudioStreamIndex' not in CommandData or 'SubtitleStreamIndex' not in CommandData:
                Analysis = self.MediaProbeAdapter.RunAnalysis(InputPath)
                if 'AudioStreamIndex' not in CommandData and Analysis and getattr(Analysis, 'AudioStreamIndex', None) is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex
                if 'SubtitleStreamIndex' not in CommandData and Analysis and getattr(Analysis, 'SubtitleStreamIndex', None) is not None:
                    CommandData['SubtitleStreamIndex'] = Analysis.SubtitleStreamIndex
                if Analysis and getattr(Analysis, 'AudioCodec', None) and 'AudioCodec' not in CommandData:
                    CommandData['AudioCodec'] = Analysis.AudioCodec

            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            SubtitleStreamIndex = CommandData.get('SubtitleStreamIndex', 0)

            BaseName = os.path.splitext(MediaFile.FileName)[0]
            BaseName = self.OutputFilenameBuilder.CollapseMvSuffix(BaseName)

            ExplicitOutputPath = CommandData.get('OutputPath')
            if ExplicitOutputPath:
                OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(ExplicitOutputPath)
            else:
                OutputFileName = BaseName + "-mv.mp4.inprogress"
                OutputDirectory = LocalDirname(InputPath)
                OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))

            if LocalSamePath(OutputPath, InputPath):
                LoggingService.LogError(
                    f"SubtitleFixShape.Build: OutputPath equals InputPath ({InputPath}). OutputPath must be a `.inprogress` side-by-side file.",
                    "SubtitleFixShape", "Build",
                )
                return None

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the shape.")

            Policy = self.Resolver.GetEffectivePolicy(MediaFile)
            if not Policy:
                # directive: audio-dialog-boost-real | # see audio-normalization.C8
                from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
                raise AudioPolicyUnresolvedError(
                    'PolicyMissing',
                    f'MediaFile.Id={getattr(MediaFile, "Id", None)} has no effective AudioPolicy; refusing stream-copy fallback that would ship source-bitrate audio (starvation risk).',
                    None,
                )
            SourceStreams = self.StreamProbe.Probe(CommandData.get('InputPath')) or None
            Blocks = self.Emitter.EmitTracks(
                MediaFile, Policy, AudioStreams=SourceStreams,
                DemucsPremixPath=CommandData.get('DemucsPremixPath'),
                VocalsRmsDbfs=CommandData.get('VocalsRmsDbfs'),
                PremixMeasuredI=CommandData.get('PremixMeasuredI'),
                PremixMeasuredLra=CommandData.get('PremixMeasuredLra'),
                PremixMeasuredTp=CommandData.get('PremixMeasuredTp'),
                PremixMeasuredThresh=CommandData.get('PremixMeasuredThresh'),
            )
            if not Blocks:
                from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
                raise AudioPolicyUnresolvedError(
                    'EmitTracksReturnedEmpty',
                    f'MediaFile.Id={getattr(MediaFile, "Id", None)} produced empty audio Blocks; refusing stream-copy fallback (starvation risk).',
                    None,
                )

            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])
            for Block in Blocks:
                if Block.InputArgs:
                    for I in range(0, len(Block.InputArgs), 2):
                        CommandParts.append(Block.InputArgs[I])
                        CommandParts.append(f'"{Block.InputArgs[I+1]}"')

            CommandParts.extend(['-map', '0:v:0'])
            CommandParts.extend(['-c:v', 'copy'])

            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            for Block in Blocks:
                CommandParts.extend(Block.MapArgs)
                CommandParts.extend(Block.CodecArgs)
                if Block.FilterArgs:
                    CommandParts.extend(Block.FilterArgs[:1])
                    CommandParts.append(f'"{Block.FilterArgs[1]}"')
                CommandParts.extend(Block.MetadataArgs)
                CommandParts.extend(Block.DispositionArgs)

            # directive: transcode-flow-canonical | # see transcode.ST5 -- BUG-0083 subtitle preservation
            SubtitleFormats = getattr(MediaFile, 'SubtitleFormats', None)
            CommandParts.extend(SubtitleSlot().Emit('mp4', SubtitleFormats))

            CommandParts.extend(['-f', 'mp4'])
            CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return CommandSpec(Command=' '.join(CommandParts), OutputPath=OutputPath)

        except Exception as Ex:
            LoggingService.LogException(
                f"SubtitleFixShape.Build failed (JobId={getattr(Job, 'Id', None)})",
                Ex, "SubtitleFixShape", "Build",
            )
            return None
