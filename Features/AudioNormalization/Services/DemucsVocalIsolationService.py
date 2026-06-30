# directive: audio-dialog-boost-real | # see audio-normalization.C14
import os
import subprocess
import sys

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin


DEMUCS_MODEL_NAME = "htdemucs"
SILENCE_FLOOR_DBFS = -120.0


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class DemucsIsolationResult:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, VocalsWavPath, InstrumentalWavPath, VocalsRmsDbfs, PremixWavPath=None):
        self.VocalsWavPath = VocalsWavPath
        self.InstrumentalWavPath = InstrumentalWavPath
        self.VocalsRmsDbfs = VocalsRmsDbfs
        self.PremixWavPath = PremixWavPath


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class DemucsVocalIsolationService:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, FfmpegPath, PythonExe=None, ModelName=DEMUCS_MODEL_NAME):
        self.FfmpegPath = FfmpegPath
        self.PythonExe = PythonExe or sys.executable
        self.ModelName = ModelName

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def IsolateVocals(self, StereoInputWavPath, OutputDir):
        os.makedirs(OutputDir, exist_ok=True)
        LoggingService.LogInfo(
            f"Demucs separating {StereoInputWavPath} -> {OutputDir}",
            "DemucsVocalIsolationService", "IsolateVocals"
        )
        Cmd = [
            self.PythonExe, "-m", "demucs.separate",
            "-n", self.ModelName,
            "--two-stems", "vocals",
            "-o", OutputDir,
            "--filename", "{stem}.{ext}",
            StereoInputWavPath,
        ]
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=3600)
        if Result.returncode != 0:
            raise RuntimeError(
                f"demucs failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        Sub = LocalJoin(OutputDir, self.ModelName)
        VocalsPath = LocalJoin(Sub, "vocals.wav")
        InstrumentalPath = LocalJoin(Sub, "no_vocals.wav")
        if not LocalExists(VocalsPath) or not LocalExists(InstrumentalPath):
            raise RuntimeError(
                f"demucs output missing: vocals={LocalExists(VocalsPath)} "
                f"instrumental={LocalExists(InstrumentalPath)} dir={Sub}"
            )
        VocalsRms = self._MeasureWavRmsDbfs(VocalsPath)
        return DemucsIsolationResult(
            VocalsWavPath=VocalsPath,
            InstrumentalWavPath=InstrumentalPath,
            VocalsRmsDbfs=VocalsRms,
        )

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def MixBoostedPremix(self, IsolationResult, OutputWavPath, VocalsBoostDb=5.0, InstrumentalAttenDb=3.0):
        Filter = (
            f"[0:a:0]volume={VocalsBoostDb:+.1f}dB[v];"
            f"[1:a:0]volume={-abs(InstrumentalAttenDb):+.1f}dB[i];"
            f"[v][i]amix=inputs=2:duration=longest:dropout_transition=0[out]"
        )
        Cmd = [
            self.FfmpegPath, "-y",
            "-i", IsolationResult.VocalsWavPath,
            "-i", IsolationResult.InstrumentalWavPath,
            "-filter_complex", Filter,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            "-ar", "48000",
            OutputWavPath,
        ]
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=1800)
        if Result.returncode != 0:
            raise RuntimeError(
                f"premix ffmpeg failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        IsolationResult.PremixWavPath = OutputWavPath
        return IsolationResult

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _MeasureWavRmsDbfs(self, WavPath):
        Result = subprocess.run(
            [self.FfmpegPath, "-i", WavPath, "-map", "0:a:0", "-af", "astats", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120
        )
        Values = []
        for Line in Result.stderr.splitlines():
            if "RMS level dB:" in Line:
                Token = Line.split("RMS level dB:")[1].strip()
                if Token == "-inf":
                    Values.append(SILENCE_FLOOR_DBFS)
                else:
                    try:
                        Values.append(float(Token))
                    except ValueError:
                        pass
        if not Values:
            return SILENCE_FLOOR_DBFS
        return Values[-1]
