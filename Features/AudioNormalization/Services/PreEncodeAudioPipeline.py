# directive: pre-encode-pipeline-parallel | # see audio-normalization.C14
import shutil
import subprocess
import tempfile
import threading

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin
from Core.SubprocessUtil import NoWindowFlags
from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository
from Features.AudioNormalization.Services.DemucsVocalIsolationService import DemucsVocalIsolationService


# directive: pre-encode-pipeline-parallel
class _ThreadResult:
    def __init__(self):
        self.value = None
        self.exception = None


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class PreEncodeAudioPipeline:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, FfmpegPath, PythonExe, DemucsService=None, ScratchRoot=None, RulesRepo=None, ProgressReporter=None, FFprobePath=None):
        self.FfmpegPath = FfmpegPath
        # FFprobePath optional; falls back to sibling-of-ffmpeg convention when caller does not supply it. Used to pick preferred (English) audio stream for the Dialog Boost downmix.
        self.FFprobePath = FFprobePath or FfmpegPath.replace('ffmpeg.exe', 'ffprobe.exe').replace('/ffmpeg', '/ffprobe')
        self.PythonExe = PythonExe
        self.DemucsService = DemucsService or DemucsVocalIsolationService(FfmpegPath=FfmpegPath, PythonExe=PythonExe)
        self.ScratchRoot = ScratchRoot or tempfile.gettempdir()
        self._RulesRepo = RulesRepo or AudioComplianceRulesRepository()
        self._Report = ProgressReporter or (lambda Phase, Percent, Info: None)

    # directive: bug-0093-preencode-fail-loud-via-d13 -- pre-encode failure raises; caller (JobProcessor) routes via transcode.D13 partial-completion (AudioSlot=Copy fallback + AudioFix follow-up). Silent-fallback sentinel removed.
    def Run(self, SourceFilePath, JobId, MediaFileId=None):
        ScratchDir = LocalJoin(self.ScratchRoot, f"mv_audio_{JobId}")
        R = self._RulesRepo.GetRules()
        SourceBox = _ThreadResult()
        SourceThread = threading.Thread(
            target=self._RunSourceMeasureTask,
            args=(SourceFilePath, R, SourceBox, MediaFileId),
            name=f"PreEncodeSourceMeasure-{JobId}",
            daemon=True,
        )
        SourceThread.start()
        try:
            ChainResult = self._RunDemucsChain(SourceFilePath, ScratchDir, R)
        except Exception:
            SourceThread.join()
            self.Cleanup(ScratchDir)
            raise
        SourceThread.join()
        if SourceBox.exception is not None:
            self.Cleanup(ScratchDir)
            raise SourceBox.exception
        SourceI, SourceLra, SourceTp, SourceThresh = SourceBox.value
        return {
            'DemucsPremixPath': ChainResult['PremixWavPath'],
            'VocalsRmsDbfs': ChainResult['VocalsRmsDbfs'],
            'PremixMeasuredI': ChainResult['PremixI'],
            'PremixMeasuredLra': ChainResult['PremixLra'],
            'PremixMeasuredTp': ChainResult['PremixTp'],
            'PremixMeasuredThresh': ChainResult['PremixThresh'],
            'SourceMeasuredI': SourceI,
            'SourceMeasuredLra': SourceLra,
            'SourceMeasuredTp': SourceTp,
            'SourceMeasuredThresh': SourceThresh,
            'ScratchDir': ScratchDir,
        }

    # directive: preencode-loudness-cache-hit -- cache-hit skips ffmpeg pass; cache-miss falls through to MeasureSourceLoudnorm (persistence handled by AudioPreEncodeFacade.PersistSourceLoudness in caller)
    def _RunSourceMeasureTask(self, SourceFilePath, R, ResultBox, MediaFileId=None):
        try:
            if MediaFileId is not None:
                from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
                Cached = MediaFilesRepository().GetSourceLoudness(int(MediaFileId))
                if Cached is not None:
                    self._Report('SourceMeasure', 100.0, f'cache-hit MediaFileId={MediaFileId}')
                    LoggingService.LogDebug(
                        f"SourceMeasure cache-hit MediaFileId={MediaFileId}",
                        "PreEncodeAudioPipeline", "_RunSourceMeasureTask",
                    )
                    ResultBox.value = Cached
                    return
            self._Report('SourceMeasure', 0.0, 'Measuring source loudness for Track 0 linear loudnorm')
            SrcTargetTp = float(R['TargetTruePeakDbtp']) - float(R['SampleLimitHeadroomDb'])
            SourceMeasureCallback = lambda Pct: self._Report('SourceMeasure', float(Pct), 'ffmpeg scanning source')
            import time as _TimeMod
            _MissStart = _TimeMod.perf_counter()
            ResultBox.value = self.DemucsService.MeasureSourceLoudnorm(
                SourceFilePath,
                TargetLufs=R['TargetIntegratedLufs'],
                TargetLra=R.get('SourceMeasureTargetLra', 7.0),
                TargetTruePeakDbtp=SrcTargetTp,
                ProgressCallback=SourceMeasureCallback,
            )
            _MissElapsed = _TimeMod.perf_counter() - _MissStart
            self._Report('SourceMeasure', 100.0, 'Source loudness measured')
            LoggingService.LogInfo(
                f"SourceMeasure cache-miss MediaFileId={MediaFileId}; ran ffmpeg loudnorm scan ({_MissElapsed:.1f}s)",
                "PreEncodeAudioPipeline", "_RunSourceMeasureTask",
            )
        except Exception as Ex:
            ResultBox.exception = Ex

    # directive: pre-encode-pipeline-parallel -- Downmix -> Demucs -> Premix -> LoudnormMeasure runs on the caller thread; internal ordering unchanged from sequential predecessor
    def _RunDemucsChain(self, SourceFilePath, ScratchDir, R):
        self._Report('Downmix', 0.0, 'Extracting stereo downmix for Demucs')
        DownmixWavPath = self._ExtractStereoDownmix(SourceFilePath, ScratchDir)
        self._Report('Downmix', 100.0, 'Stereo downmix ready')
        self._Report('Demucs', 0.0, f'Isolating vocals ({self.DemucsService.ModelName} via daemon)')
        DemucsCallback = lambda Pct, DoneSec, TotalSec: self._Report('Demucs', float(Pct), f'{DoneSec:.1f}s / {TotalSec:.1f}s')
        Isolation = self.DemucsService.IsolateVocals(DownmixWavPath, ScratchDir, ProgressCallback=DemucsCallback)
        self._Report('Demucs', 100.0, 'Vocals isolated')
        self._Report('Premix', 0.0, 'Mixing boosted vocals + attenuated instrumental')
        PremixWavPath = LocalJoin(ScratchDir, "dialog_boost_premix.wav")
        self.DemucsService.MixBoostedPremix(
            Isolation, PremixWavPath,
            VocalsBoostDb=R['VocalsBoostDb'],
            InstrumentalAttenDb=R['InstrumentalAttenDb'],
            CompressorThreshold=R['PremixCompressorThreshold'],
            CompressorRatio=R['PremixCompressorRatio'],
            CompressorMakeupDb=R['PremixCompressorMakeupDb'],
            DynaudnormFrameLen=R['PremixDynaudnormFrameLen'],
            DynaudnormGaussSize=R['PremixDynaudnormGaussSize'],
        )
        self._Report('Premix', 100.0, 'Premix WAV ready')
        self._Report('LoudnormMeasure', 0.0, 'Measuring premix loudness for two-pass linear loudnorm')
        EffectiveTp = float(R['TargetTruePeakDbtp']) - float(R['SampleLimitHeadroomDb'])
        LoudnormCallback = lambda Pct: self._Report('LoudnormMeasure', float(Pct), 'ffmpeg scanning premix')
        PremixI, PremixLra, PremixTp, PremixThresh = self.DemucsService.MeasurePremixLoudnorm(
            PremixWavPath,
            TargetLufs=R['DialogBoostTargetLufs'],
            TargetLra=R['DialogBoostTargetLra'],
            TargetTruePeakDbtp=EffectiveTp,
            ProgressCallback=LoudnormCallback,
        )
        self._Report('LoudnormMeasure', 100.0, 'Premix loudness measured')
        return {
            'PremixWavPath': PremixWavPath,
            'VocalsRmsDbfs': Isolation.VocalsRmsDbfs,
            'PremixI': PremixI,
            'PremixLra': PremixLra,
            'PremixTp': PremixTp,
            'PremixThresh': PremixThresh,
        }

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def Cleanup(self, ScratchDir):
        if not ScratchDir:
            return
        if LocalExists(ScratchDir):
            try:
                shutil.rmtree(ScratchDir, ignore_errors=True)
            except Exception as Ex:
                LoggingService.LogException(
                    f"PreEncodeAudioPipeline cleanup failed for {ScratchDir}",
                    Ex, "PreEncodeAudioPipeline", "Cleanup",
                )

    # directive: dialog-boost-emission-integrity | # see .claude/directive.md C2 -- raises PriorBoostSourceError when source is prior-boost-only.
    def _SelectPreferredAudioIndex(self, SourceFilePath):
        from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe
        from Features.AudioNormalization.SourceAudioTrackSelector import SelectTrueSourceStreams
        Streams = AudioStreamProbe(FFprobePath=self.FFprobePath).Probe(SourceFilePath)
        TrueStreams = SelectTrueSourceStreams(Streams)
        if not TrueStreams:
            return 0
        AllowedIndices = {int(S.get('index')) for S in TrueStreams if S.get('index') is not None}
        try:
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            Analysis = FFmpegAnalysisService(FFprobePath=self.FFprobePath).AnalyzeMediaFile(SourceFilePath)
            Preferred = getattr(Analysis, 'AudioStreamIndex', None) if Analysis is not None else None
            if Preferred is not None and int(Preferred) in AllowedIndices:
                return int(Preferred)
        except Exception as Ex:
            LoggingService.LogWarning(
                f"PreEncodeAudioPipeline: FFmpegAnalysisService preference lookup failed for {SourceFilePath}: {Ex}; picking first true-source stream",
                "PreEncodeAudioPipeline", "_SelectPreferredAudioIndex",
            )
        for S in TrueStreams:
            Tags = S.get('tags') or {}
            if str(Tags.get('language') or '').lower() in ('eng', 'en'):
                return int(S.get('index'))
        return int(TrueStreams[0].get('index'))

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _ExtractStereoDownmix(self, SourceFilePath, ScratchDir):
        import os
        os.makedirs(ScratchDir, exist_ok=True)
        OutputPath = LocalJoin(ScratchDir, "source_downmix.wav")
        PreferredIdx = self._SelectPreferredAudioIndex(SourceFilePath)
        Cmd = [
            self.FfmpegPath, "-y",
            "-i", SourceFilePath,
            "-map", f"0:a:{PreferredIdx}",
            "-ac", "2",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            OutputPath,
        ]
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=1800, creationflags=NoWindowFlags())
        if Result.returncode != 0:
            raise RuntimeError(
                f"stereo downmix failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        if not LocalExists(OutputPath):
            raise RuntimeError(f"stereo downmix output missing: {OutputPath}")
        return OutputPath
