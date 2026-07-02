import os
from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname, LocalSamePath
from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
class RemuxShape(EncodeShape):
    """Builds ffmpeg argv for container-swap jobs; always emits -f mp4 + -movflags +faststart; audio goes through AudioFilterEmitter."""

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

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C13
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        """Port of CommandBuilder._BuildRemuxShape with unconditional -f mp4 + faststart invariants."""
        try:
            CommandData = Context
            InputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(
                CommandData.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )

            if 'AudioStreamIndex' not in CommandData or 'HasAudio' not in CommandData:
                Analysis = self.MediaProbeAdapter.RunAnalysis(InputPath)
                DetectedAudioCodec = getattr(Analysis, 'AudioCodec', '') if Analysis else ''
                if 'AudioStreamIndex' not in CommandData and Analysis and getattr(Analysis, 'AudioStreamIndex', None) is not None:
                    CommandData['AudioStreamIndex'] = Analysis.AudioStreamIndex
                if 'HasAudio' not in CommandData:
                    CommandData['HasAudio'] = bool(DetectedAudioCodec)

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
                    f"RemuxShape.Build: OutputPath equals InputPath ({InputPath}). OutputPath must be a `.inprogress` side-by-side file.",
                    "RemuxShape", "Build",
                )
                return None

            FFmpegPath = CommandData.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from CommandData. The caller (worker) must resolve this from Workers.FFmpegPath via WorkerContext before invoking the shape.")
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])

            HasAudio = CommandData.get('HasAudio', True)
            CommandParts.extend(['-map', '0:v:0'])

            CommandParts.extend(['-c:v', 'copy'])

            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            if HasAudio:
                AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
                Policy = self.Resolver.GetEffectivePolicy(MediaFile)
                SourceStreams = self.StreamProbe.Probe(CommandData.get('InputPath')) or None
                Blocks = self.Emitter.EmitTracks(MediaFile, Policy, AudioStreams=SourceStreams) if Policy else []
                if not Blocks:
                    CommandParts.extend(['-map', f'0:a:{AudioStreamIndex}', '-c:a', 'copy'])
                else:
                    for Block in Blocks:
                        CommandParts.extend(Block.MapArgs)
                        CommandParts.extend(Block.CodecArgs)
                        if Block.FilterArgs:
                            CommandParts.extend(Block.FilterArgs[:1])
                            CommandParts.append(f'"{Block.FilterArgs[1]}"')
                        CommandParts.extend(Block.MetadataArgs)
                        CommandParts.extend(Block.DispositionArgs)

            CommandParts.extend(['-f', 'mp4'])
            CommandParts.extend(['-movflags', '+faststart'])
            CommandParts.append('-y')
            CommandParts.append(f'"{OutputPath}"')

            return CommandSpec(Command=' '.join(CommandParts), OutputPath=OutputPath)

        except Exception as Ex:
            LoggingService.LogException(
                f"RemuxShape.Build failed (JobId={getattr(Job, 'Id', None)})",
                Ex, "RemuxShape", "Build",
            )
            return None
