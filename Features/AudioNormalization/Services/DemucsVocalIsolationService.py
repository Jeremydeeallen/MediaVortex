# directive: audio-dialog-boost-real | # see audio-normalization.C14
import json
import os
import re
import subprocess
import sys

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin


DEMUCS_MODEL_NAME = "htdemucs"
SILENCE_FLOOR_DBFS = -120.0


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _DetectDemucsDevice(PythonExe):
    Code = (
        "try:\n"
        " import intel_extension_for_pytorch\n"
        "except ImportError:\n"
        " pass\n"
        "import torch\n"
        "if torch.cuda.is_available():\n"
        " print('cuda')\n"
        "elif hasattr(torch, 'xpu') and torch.xpu.is_available():\n"
        " print('xpu')\n"
        "else:\n"
        " print('cpu')\n"
    )
    Probe = subprocess.run(
        [PythonExe, "-c", Code],
        capture_output=True, text=True, timeout=30,
    )
    if Probe.returncode != 0:
        return "cpu"
    return (Probe.stdout or "cpu").strip() or "cpu"


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

    # directive: transcode-flow-canonical -- long-lived daemon amortizes model load + XPU compile
    def __init__(self, FfmpegPath, PythonExe=None, ModelName=DEMUCS_MODEL_NAME, Device=None, Daemon=None):
        self.FfmpegPath = FfmpegPath
        self.PythonExe = PythonExe or sys.executable
        self.ModelName = ModelName
        self.Device = Device or _DetectDemucsDevice(self.PythonExe)
        self._Daemon = Daemon

    def IsolateVocals(self, StereoInputWavPath, OutputDir):
        os.makedirs(OutputDir, exist_ok=True)
        LoggingService.LogInfo(
            f"Demucs isolating {StereoInputWavPath} -> {OutputDir} (device={self.Device})",
            "DemucsVocalIsolationService", "IsolateVocals",
        )
        Daemon = self._GetDaemon()
        Resp = Daemon.IsolateVocals(StereoInputWavPath, OutputDir, ModelName=self.ModelName)
        if not Resp.Success:
            raise RuntimeError(f"demucs daemon isolation failed: {Resp.ErrorMessage}")
        VocalsPath = Resp.VocalsWavPath
        InstrumentalPath = Resp.InstrumentalWavPath
        if not LocalExists(VocalsPath) or not LocalExists(InstrumentalPath):
            raise RuntimeError(
                f"demucs output missing: vocals_exists={LocalExists(VocalsPath)} "
                f"instrumental_exists={LocalExists(InstrumentalPath)}"
            )
        VocalsRms = self._MeasureWavRmsDbfs(VocalsPath)
        return DemucsIsolationResult(
            VocalsWavPath=VocalsPath,
            InstrumentalWavPath=InstrumentalPath,
            VocalsRmsDbfs=VocalsRms,
        )

    def _GetDaemon(self):
        if self._Daemon is None:
            from Features.AudioNormalization.Services.DemucsDaemonClient import GetOrStartDaemon
            self._Daemon = GetOrStartDaemon(PythonExe=self.PythonExe)
        return self._Daemon

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def MixBoostedPremix(self, IsolationResult, OutputWavPath, VocalsBoostDb, InstrumentalAttenDb, CompressorThreshold, CompressorRatio, CompressorMakeupDb, DynaudnormFrameLen, DynaudnormGaussSize):
        Filter = (
            f"[0:a:0]volume={float(VocalsBoostDb):+.1f}dB[v];"
            f"[1:a:0]volume={-abs(float(InstrumentalAttenDb)):+.1f}dB[i];"
            f"[v][i]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
            f"[mix]acompressor=threshold={float(CompressorThreshold):.3f}:ratio={float(CompressorRatio):.1f}:attack=8:release=120:makeup={float(CompressorMakeupDb):.1f}:knee=4,"
            f"dynaudnorm=f={int(DynaudnormFrameLen)}:g={int(DynaudnormGaussSize)}:p=0.7:m=8[out]"
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

    # directive: transcode-flow-canonical
    def MeasureSourceLoudnorm(self, SourcePath, TargetLufs, TargetLra, TargetTruePeakDbtp):
        Filter = f"loudnorm=I={float(TargetLufs):.2f}:LRA={float(TargetLra):.2f}:TP={float(TargetTruePeakDbtp):.2f}:print_format=json"
        Result = subprocess.run(
            [self.FfmpegPath, "-hide_banner", "-nostats", "-i", SourcePath, "-map", "0:a:0", "-af", Filter, "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800,
        )
        Match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", Result.stderr, re.DOTALL)
        if not Match:
            LoggingService.LogWarning(
                f"Source loudnorm measurement returned no JSON block for {SourcePath}. stderr tail={Result.stderr[-400:]}",
                "DemucsVocalIsolationService", "MeasureSourceLoudnorm",
            )
            return None, None, None, None
        try:
            Payload = json.loads(Match.group(0))
            return (
                float(Payload["input_i"]),
                float(Payload["input_lra"]),
                float(Payload["input_tp"]),
                float(Payload["input_thresh"]),
            )
        except (ValueError, KeyError) as Ex:
            LoggingService.LogWarning(
                f"Source loudnorm JSON parse failed for {SourcePath} ({Ex}); block={Match.group(0)[:400]}",
                "DemucsVocalIsolationService", "MeasureSourceLoudnorm",
            )
            return None, None, None, None

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def MeasurePremixLoudnorm(self, WavPath, TargetLufs, TargetLra, TargetTruePeakDbtp):
        """Measure premix loudness with ffmpeg's loudnorm analysis pass; return (I, LRA, TP, thresh) or all-None on parse failure."""
        Filter = f"loudnorm=I={float(TargetLufs):.2f}:LRA={float(TargetLra):.2f}:TP={float(TargetTruePeakDbtp):.2f}:print_format=json"
        Result = subprocess.run(
            [self.FfmpegPath, "-hide_banner", "-nostats", "-i", WavPath, "-af", Filter, "-f", "null", "-"],
            capture_output=True, text=True, timeout=900,
        )
        Match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", Result.stderr, re.DOTALL)
        if not Match:
            LoggingService.LogWarning(
                f"Premix loudnorm measurement returned no JSON block; falling back to dynamic loudnorm. stderr tail={Result.stderr[-400:]}",
                "DemucsVocalIsolationService", "MeasurePremixLoudnorm",
            )
            return None, None, None, None
        try:
            Payload = json.loads(Match.group(0))
            return (
                float(Payload["input_i"]),
                float(Payload["input_lra"]),
                float(Payload["input_tp"]),
                float(Payload["input_thresh"]),
            )
        except (ValueError, KeyError) as Ex:
            LoggingService.LogWarning(
                f"Premix loudnorm JSON parse failed ({Ex}); falling back to dynamic loudnorm. block={Match.group(0)[:400]}",
                "DemucsVocalIsolationService", "MeasurePremixLoudnorm",
            )
            return None, None, None, None

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
