import os
from datetime import datetime, timezone
from pathlib import Path as _PyPath
from typing import Any, Dict, Optional

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname, LocalSamePath
from Features.MediaFile.Domain.MediaFileScope import IsAudioOnlyContainer
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.HwAccelResolver import HwAccelResolver
from Features.TranscodeJob.Emit.MediaProbeAdapter import MediaProbeAdapter
from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder
from Features.TranscodeJob.Emit.Plan import Plan, PlanFactory
from Features.TranscodeJob.Emit.ResolutionCalculator import ResolutionCalculator
from Features.TranscodeJob.Emit.Slots.AudioSlot import AudioSlot
from Features.TranscodeJob.Emit.Slots.ContainerSlot import ContainerSlot
from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot
from Features.TranscodeJob.Emit.Slots.VideoSlot import VideoSlot
from Features.TranscodeJob.Emit.VideoFilterBuilder import VideoFilterBuilder


# directive: transcode-flow-canonical -- C34
class NonVideoSourceError(ValueError):
    pass


# directive: transcode-flow-canonical | # see transcode.ST5
class CommandComposer:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def __init__(self, VideoSlotInstance=None, AudioSlotInstance=None, SubtitleSlotInstance=None,
                 ContainerSlotInstance=None, ResolutionCalculatorInstance=None,
                 OutputFilenameBuilderInstance=None, MediaProbeAdapterInstance=None,
                 PlanFactoryInstance=None, HwAccelResolverInstance=None):
        self.VideoSlot = VideoSlotInstance or VideoSlot(VideoFilterBuilder=VideoFilterBuilder())
        self.AudioSlot = AudioSlotInstance or AudioSlot()
        self.SubtitleSlot = SubtitleSlotInstance or SubtitleSlot()
        self.ContainerSlot = ContainerSlotInstance or ContainerSlot()
        self.ResolutionCalculator = ResolutionCalculatorInstance or ResolutionCalculator()
        self.OutputFilenameBuilder = OutputFilenameBuilderInstance or OutputFilenameBuilder()
        self.MediaProbeAdapter = MediaProbeAdapterInstance
        self.PlanFactory = PlanFactoryInstance or PlanFactory()
        self.HwAccelResolver = HwAccelResolverInstance or HwAccelResolver()
        self._CommitSha = self._ReadCommitShaOnce()

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C25 -- worker + profile + encoder + commit + ts baked into moov/udta at build time (Attempt.Id not yet known).
    def _BuildProvenanceMetadata(self, MediaFile, Plan_, ProfileSettings: Dict[str, Any]) -> list:
        try:
            from Core.WorkerContext import WorkerContext
            WorkerName = WorkerContext.TryCurrent()
            WorkerName = WorkerName.WorkerName if WorkerName else 'unknown'
        except Exception:
            WorkerName = 'unknown'
        Profile = getattr(MediaFile, 'AssignedProfile', None) or 'unknown'
        if Plan_.VideoOp == 'Copy':
            Encoder = 'copy'
        else:
            UseNv = ProfileSettings.get('UseNvidiaHardware', 0)
            UseQsv = ProfileSettings.get('UseIntelHardware', 0)
            Codec = ProfileSettings.get('Codec') or 'libsvtav1'
            if UseNv == 1:
                Encoder = 'av1_nvenc' if Codec == 'av1' else Codec
            elif UseQsv == 1:
                Encoder = 'av1_qsv' if Codec == 'av1' else Codec
            else:
                Encoder = Codec
        Ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return [
            '-metadata', '"comment=Transcoded by MediaVortex"',
            '-metadata', f'"mediavortex_worker={WorkerName}"',
            '-metadata', f'"mediavortex_profile={Profile}"',
            '-metadata', f'"mediavortex_encoder={Encoder}"',
            '-metadata', f'"mediavortex_commit={self._CommitSha}"',
            '-metadata', f'"mediavortex_ts={Ts}"',
        ]

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C25 -- baremetal ships to /opt/mediavortex/src, Docker/Windows use different roots; check all known locations.
    def _ReadCommitShaOnce(self) -> str:
        try:
            Candidates = [
                _PyPath('/opt/mediavortex/src/VERSION'),
                _PyPath('/opt/mediavortex/VERSION'),
                _PyPath(__file__).resolve().parents[4] / 'VERSION',
            ]
            for Candidate in Candidates:
                if Candidate.exists():
                    Val = Candidate.read_text(encoding='utf-8').strip()
                    return Val[:8] if Val else 'unknown'
        except Exception:
            pass
        return 'unknown'

    # directive: transcode-flow-canonical | # see transcode.ST5
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        if IsAudioOnlyContainer(MediaFile):
            raise NonVideoSourceError(
                f"CommandComposer.Build refuses audio-only container "
                f"(MediaFileId={getattr(MediaFile, 'Id', None)}, "
                f"ContainerFormat={getattr(MediaFile, 'ContainerFormat', None)!r}, "
                f"JobId={getattr(Job, 'Id', None)}). "
                f"WorkBucket classifier should route audio-only files to 'Unclassified' -- "
                f"reaching CommandComposer means the classifier gate was bypassed."
            )
        try:
            Plan_ = self.PlanFactory.FromProcessingMode(getattr(Job, 'ProcessingMode', None))
            ProfileSettings = Context.get('ProfileSettings', {}) or {}
            CodecParameters = Context.get('CodecParameters', []) or []
            FFmpegPath = Context.get('FFmpegPath')
            if not FFmpegPath:
                raise ValueError("FFmpegPath missing from Context. Caller must resolve from Workers.FFmpegPath via WorkerContext before invoking CommandComposer.")
            InputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(
                Context.get('InputPath', f"c:\\MediaVortex\\Source\\{MediaFile.FileName}")
            )
            OutputPath = self._ResolveOutputPath(MediaFile, Plan_, ProfileSettings, Context, InputPath)
            if OutputPath is None:
                return None
            self._EnrichAudioStreamIndex(Context, InputPath)
            ScaleFilter = self._ResolveScaleFilter(Plan_, ProfileSettings, Context, MediaFile)
            # directive: e2e-bug-fixes | # see e2e-bug-fixes.C27 -- per-worker hwaccel decode; swaps scale filter to backend-native variant.
            HwAccel = None
            if Plan_.VideoOp == 'Reencode':
                from Core.WorkerContext import WorkerContext
                try:
                    Wc = WorkerContext.TryCurrent()
                    WorkerName = Wc.WorkerName if Wc else None
                except Exception:
                    WorkerName = None
                HwAccel = self.HwAccelResolver.Resolve(WorkerName, ProfileSettings, MediaFile, bool(ScaleFilter))
                ScaleFilter = self.HwAccelResolver.AdaptScaleFilter(ScaleFilter, HwAccel)
            AudioEmission_ = self.AudioSlot.Emit(Plan_.AudioOp, MediaFile, Context)
            Parts = [FFmpegPath]
            StartTime = Context.get('StartTime')
            if StartTime and StartTime.strip():
                Parts.extend(['-ss', StartTime.strip()])
            if HwAccel:
                Parts.extend(HwAccel.InputArgs)
            Parts.extend(['-i', f'"{InputPath}"'])
            Parts.extend(AudioEmission_.InputArgs)
            MaxCpuThreads = Context.get('MaxCpuThreads')
            Parts.extend(self.VideoSlot.Emit(Plan_.VideoOp, MediaFile, ProfileSettings, CodecParameters, ScaleFilter, MaxCpuThreads, HwAccelActive=bool(HwAccel)))
            Parts.extend(AudioEmission_.StreamArgs)
            SubtitleFormats = getattr(MediaFile, 'SubtitleFormats', None)
            SubtitleStreams = self._ProbeSubtitleStreams(Context, InputPath)
            Parts.extend(self.SubtitleSlot.Emit('mp4' if Plan_.ContainerOp == 'Mp4' else Plan_.ContainerOp.lower(), SubtitleFormats, SubtitleStreams))
            Parts.extend(self.ContainerSlot.Emit(Plan_.ContainerOp))
            Parts.extend(self._BuildProvenanceMetadata(MediaFile, Plan_, ProfileSettings))
            Parts.append('-y')
            Parts.append(f'"{OutputPath}"')
            return CommandSpec(Command=' '.join(Parts), OutputPath=OutputPath)
        except Exception as Ex:
            JobId = getattr(Job, 'Id', None)
            FilePath = getattr(Job, 'FilePath', None)
            LoggingService.LogException(
                f"CommandComposer.Build failed (JobId={JobId}, FilePath={FilePath})",
                Ex, "CommandComposer", "Build",
            )
            return None

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _ResolveOutputPath(self, MediaFile, Plan_: Plan, ProfileSettings: Dict[str, Any],
                           Context: Dict[str, Any], InputPath: str) -> Optional[str]:
        ExplicitOutputPath = Context.get('OutputPath')
        if ExplicitOutputPath:
            OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(ExplicitOutputPath)
        elif Plan_.VideoOp == 'Reencode':
            SourceResolution = Context.get('SourceResolution') or getattr(MediaFile, 'Resolution', '') or ''
            TargetResolution = Context.get('TargetResolution') or self.ResolutionCalculator.CalculateTargetResolution(ProfileSettings, SourceResolution)
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')
            CrfValue = ProfileSettings.get('Quality')
            OutputFileName = self.OutputFilenameBuilder.GenerateOutputFileName(MediaFile.FileName, SourceResolution, TargetResolution, ContainerType, CrfValue)
            OutputDirectory = LocalDirname(InputPath)
            OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))
        else:
            BaseName = os.path.splitext(MediaFile.FileName)[0]
            BaseName = self.OutputFilenameBuilder.CollapseMvSuffix(BaseName)
            OutputFileName = BaseName + "-mv.mp4.inprogress"
            OutputDirectory = LocalDirname(InputPath)
            OutputPath = self.OutputFilenameBuilder.NormalizeFfmpegPath(os.path.join(OutputDirectory, OutputFileName))
        if LocalSamePath(OutputPath, InputPath):
            LoggingService.LogError(
                f"CommandComposer.Build: OutputPath equals InputPath ({InputPath}). OutputPath must be a `.inprogress` side-by-side file.",
                "CommandComposer", "_ResolveOutputPath",
            )
            return None
        return OutputPath

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EnrichAudioStreamIndex(self, Context: Dict[str, Any], InputPath: str) -> None:
        if 'AudioStreamIndex' in Context or self.MediaProbeAdapter is None:
            return
        Analysis = self.MediaProbeAdapter.RunAnalysis(InputPath)
        if Analysis and getattr(Analysis, 'AudioStreamIndex', None) is not None:
            Context['AudioStreamIndex'] = Analysis.AudioStreamIndex

    # BUG-0083 slot: per-index text-only sub mapping needs (index, codec) list from ffprobe; ffmpeg map syntax has no codec_name selector.
    def _ProbeSubtitleStreams(self, Context: Dict[str, Any], InputPath: str) -> Optional[list]:
        if 'SubtitleStreams' in Context:
            return Context['SubtitleStreams']
        if self.MediaProbeAdapter is None:
            return None
        try:
            Probe = self.MediaProbeAdapter.ProbeStreams(InputPath)
            Streams = [
                (int(S.get('index')), (S.get('codec_name') or '').lower())
                for S in Probe.get('streams', [])
                if S.get('codec_type') == 'subtitle' and S.get('index') is not None
            ]
            Context['SubtitleStreams'] = Streams
            return Streams
        except Exception as Ex:
            LoggingService.LogWarning(
                f"CommandComposer._ProbeSubtitleStreams failed for {InputPath}: {Ex}",
                "CommandComposer", "_ProbeSubtitleStreams",
            )
            return None

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _ResolveScaleFilter(self, Plan_: Plan, ProfileSettings: Dict[str, Any],
                            Context: Dict[str, Any], MediaFile) -> Optional[str]:
        if Plan_.VideoOp != 'Reencode':
            return None
        ScaleFilter = Context.get('ScaleFilter')
        if ScaleFilter is not None:
            return ScaleFilter
        SourceResolution = Context.get('SourceResolution') or getattr(MediaFile, 'Resolution', '') or ''
        TargetResolution = Context.get('TargetResolution') or self.ResolutionCalculator.CalculateTargetResolution(ProfileSettings, SourceResolution)
        if TargetResolution and SourceResolution and TargetResolution != SourceResolution:
            return self.ResolutionCalculator.CalculateScaleFilter(SourceResolution, TargetResolution, MediaFile, ProfileSettings)
        return None
