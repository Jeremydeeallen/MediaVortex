# directive: audio-dialog-boost-real | # see audio-normalization.C14
import shutil
import subprocess
import tempfile

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin
from Core.SubprocessUtil import NoWindowFlags
from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository
from Features.AudioNormalization.Services.DemucsVocalIsolationService import DemucsVocalIsolationService


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

    # directive: audio-preencode-progress -- every substep emits start (0%) + end (100%) rows via ProgressReporter -> TranscodeProgress. Demucs additionally receives per-tqdm-tick callback from the daemon so its progress is visible in real time (>= 1 Hz on real workloads).
    def Run(self, SourceFilePath, JobId):
        ScratchDir = LocalJoin(self.ScratchRoot, f"mv_audio_{JobId}")
        try:
            R = self._RulesRepo.GetRules()
            self._Report('SourceMeasure', 0.0, 'Measuring source loudness for Track 0 linear loudnorm')
            SrcTargetTp = float(R['TargetTruePeakDbtp']) - float(R['SampleLimitHeadroomDb'])
            SourceMeasureCallback = lambda Pct: self._Report('SourceMeasure', float(Pct), 'ffmpeg scanning source')
            SourceI, SourceLra, SourceTp, SourceThresh = self.DemucsService.MeasureSourceLoudnorm(
                SourceFilePath,
                TargetLufs=R['TargetIntegratedLufs'],
                TargetLra=R.get('SourceMeasureTargetLra', 7.0),
                TargetTruePeakDbtp=SrcTargetTp,
                ProgressCallback=SourceMeasureCallback,
            )
            self._Report('SourceMeasure', 100.0, 'Source loudness measured')
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
                'DemucsPremixPath': PremixWavPath,
                'VocalsRmsDbfs': Isolation.VocalsRmsDbfs,
                'PremixMeasuredI': PremixI,
                'PremixMeasuredLra': PremixLra,
                'PremixMeasuredTp': PremixTp,
                'PremixMeasuredThresh': PremixThresh,
                'SourceMeasuredI': SourceI,
                'SourceMeasuredLra': SourceLra,
                'SourceMeasuredTp': SourceTp,
                'SourceMeasuredThresh': SourceThresh,
                'ScratchDir': ScratchDir,
            }
        except Exception as Ex:
            LoggingService.LogException(
                f"PreEncodeAudioPipeline failed for {SourceFilePath} (job {JobId}); Dialog Boost track will be skipped",
                Ex, "PreEncodeAudioPipeline", "Run",
            )
            self.Cleanup(ScratchDir)
            # see audio-normalization.C39
            return {'DemucsPremixPath': None, 'VocalsRmsDbfs': None, 'ScratchDir': None, 'DemucsFailed': True, 'DemucsFailureReason': f"{type(Ex).__name__}: {str(Ex)[:200]}"}

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

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _SelectPreferredAudioIndex(self, SourceFilePath):
        # Pick English track if present; fall back to first audio. Multi-language sources (Bluray with fre+eng) used to blindly grab a:0 -- Dialog Boost then contained boosted French mislabeled 'Dialog Boost (eng)'.
        try:
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            Analysis = FFmpegAnalysisService(FFprobePath=self.FFprobePath).AnalyzeMediaFile(SourceFilePath)
            if Analysis is not None and getattr(Analysis, 'AudioStreamIndex', None) is not None:
                return int(Analysis.AudioStreamIndex)
        except Exception as Ex:
            LoggingService.LogWarning(
                f"PreEncodeAudioPipeline: preferred-audio probe failed for {SourceFilePath}: {Ex}; falling back to a:0",
                "PreEncodeAudioPipeline", "_SelectPreferredAudioIndex",
            )
        return 0

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
