import os
from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname, LocalSamePath
from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
class SubtitleFixShape(EncodeShape):
    """Builds ffmpeg argv for subtitle-fix jobs (ASS/SSA -> mov_text); always emits -f mp4 + -movflags +faststart."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C14
    def __init__(self, OutputFilenameBuilder, AudioCodecArgsBuilder, AudioFilterBuilder, MediaProbeAdapter):
        """Inject minimal collaborators needed for subtitle-fix (no video filter or codec assembler)."""
        self.OutputFilenameBuilder = OutputFilenameBuilder
        self.AudioCodecArgsBuilder = AudioCodecArgsBuilder
        self.AudioFilterBuilder = AudioFilterBuilder
        self.MediaProbeAdapter = MediaProbeAdapter

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
            CommandParts = [FFmpegPath]
            CommandParts.extend(['-i', f'"{InputPath}"'])
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}', '-map', f'0:s:{SubtitleStreamIndex}'])
            CommandParts.extend(['-c:v', 'copy'])

            VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
            if VideoCodec in ('hevc', 'h265', 'x265'):
                CommandParts.extend(['-tag:v', 'hvc1'])

            if AudioCompletionService.ShouldStreamCopyAudio(MediaFile):
                CommandParts.extend(['-c:a', 'copy'])
            else:
                CommandParts.extend(self.AudioCodecArgsBuilder.BuildAudioCodecArgs(MediaFile, ProfileBitrate=0))
                AudioFilter = self.AudioFilterBuilder.Build(MediaFile)
                if AudioFilter:
                    CommandParts.extend(['-af', f'"{AudioFilter}"'])

            CommandParts.extend(['-c:s', 'mov_text'])
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
