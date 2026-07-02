# directive: audio-dialog-boost-real | # see audio-normalization.C14
import shutil
import subprocess
import tempfile

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin
from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository
from Features.AudioNormalization.Services.DemucsVocalIsolationService import DemucsVocalIsolationService


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class PreEncodeAudioPipeline:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, FfmpegPath, PythonExe, DemucsService=None, ScratchRoot=None, RulesRepo=None, ProgressReporter=None):
        self.FfmpegPath = FfmpegPath
        self.PythonExe = PythonExe
        self.DemucsService = DemucsService or DemucsVocalIsolationService(FfmpegPath=FfmpegPath, PythonExe=PythonExe)
        self.ScratchRoot = ScratchRoot or tempfile.gettempdir()
        self._RulesRepo = RulesRepo or AudioComplianceRulesRepository()
        self._Report = ProgressReporter or (lambda Phase, Percent, Info: None)

    # directive: audio-dialog-boost-real | # see audio-normalization.C34
    def Run(self, SourceFilePath, JobId):
        ScratchDir = LocalJoin(self.ScratchRoot, f"mv_audio_{JobId}")
        try:
            R = self._RulesRepo.GetRules()
            self._Report('demucs.downmix', 0.0, 'Extracting stereo downmix for Demucs')
            DownmixWavPath = self._ExtractStereoDownmix(SourceFilePath, ScratchDir)
            self._Report('demucs.isolate', 0.0, f'Isolating vocals ({self.DemucsService.ModelName} on {self.DemucsService.Device})')
            Isolation = self.DemucsService.IsolateVocals(DownmixWavPath, ScratchDir)
            self._Report('demucs.premix', 0.0, 'Mixing boosted vocals + attenuated instrumental')
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
            return {
                'DemucsPremixPath': PremixWavPath,
                'VocalsRmsDbfs': Isolation.VocalsRmsDbfs,
                'ScratchDir': ScratchDir,
            }
        except Exception as Ex:
            LoggingService.LogException(
                f"PreEncodeAudioPipeline failed for {SourceFilePath} (job {JobId}); Dialog Boost track will be skipped",
                Ex, "PreEncodeAudioPipeline", "Run",
            )
            self.Cleanup(ScratchDir)
            return {'DemucsPremixPath': None, 'VocalsRmsDbfs': None, 'ScratchDir': None}

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
    def _ExtractStereoDownmix(self, SourceFilePath, ScratchDir):
        import os
        os.makedirs(ScratchDir, exist_ok=True)
        OutputPath = LocalJoin(ScratchDir, "source_downmix.wav")
        Cmd = [
            self.FfmpegPath, "-y",
            "-i", SourceFilePath,
            "-map", "0:a:0",
            "-ac", "2",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            OutputPath,
        ]
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=1800)
        if Result.returncode != 0:
            raise RuntimeError(
                f"stereo downmix failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        if not LocalExists(OutputPath):
            raise RuntimeError(f"stereo downmix output missing: {OutputPath}")
        return OutputPath
