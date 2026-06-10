import os
from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname
from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
class TranscodeShape(EncodeShape):
    """Builds ffmpeg argv for full video re-encode jobs; composes resolution + filename + codec + filter + audio collaborators."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C12
    def __init__(self, ResolutionCalculator, OutputFilenameBuilder, CodecParameterAssembler,
                 AudioCodecArgsBuilder, AudioFilterBuilder, VideoFilterBuilder, MediaProbeAdapter):
        """Inject domain primitive collaborators via constructor (DIP)."""
        self.ResolutionCalculator = ResolutionCalculator
        self.OutputFilenameBuilder = OutputFilenameBuilder
        self.CodecParameterAssembler = CodecParameterAssembler
        self.AudioCodecArgsBuilder = AudioCodecArgsBuilder
        self.AudioFilterBuilder = AudioFilterBuilder
        self.VideoFilterBuilder = VideoFilterBuilder
        self.MediaProbeAdapter = MediaProbeAdapter

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

            AudioStreamIndex = CommandData.get('AudioStreamIndex', 0)
            CommandParts.extend(['-map', '0:v:0', '-map', f'0:a:{AudioStreamIndex}'])

            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
            VideoCodec = 'av1_nvenc' if UseNvidiaHardware == 1 else ProfileSettings.get('Codec', 'libsvtav1')
            CommandParts.extend(['-c:v', VideoCodec])

            MaxCpuThreads = CommandData.get('MaxCpuThreads')
            if MaxCpuThreads:
                CommandParts.extend(['-threads', str(MaxCpuThreads)])

            self.CodecParameterAssembler.AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)

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
                    CommandParts.extend(self.AudioCodecArgsBuilder.BuildAudioCodecArgs(MediaFile, ProfileAudioBitrate))
                    AudioFilter = self.AudioFilterBuilder.Build(MediaFile)
                    if AudioFilter:
                        CommandParts.extend(['-af', f'"{AudioFilter}"'])

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
