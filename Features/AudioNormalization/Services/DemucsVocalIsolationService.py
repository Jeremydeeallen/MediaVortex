# directive: audio-dialog-boost-real | # see audio-normalization.C14
import json
import os
import re
import subprocess
import sys

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists, LocalJoin
from Core.SubprocessUtil import NoWindowFlags


DEMUCS_MODEL_NAME = "htdemucs"
SILENCE_FLOOR_DBFS = -120.0

# directive: audio-preencode-progress -- shared streaming ffmpeg runner: spawns Popen, parses "Duration: HH:MM:SS.xx" and "time=HH:MM:SS.xx" from stderr, invokes ProgressCallback(percent) per tick. Returns full stderr on completion for downstream JSON extraction. Kept next to the loudnorm callers because those are its only consumers.
_FF_DUR_RE = re.compile(r"Duration:\s+(\d+):(\d+):(\d+)\.(\d+)")
_FF_TIME_RE = re.compile(r"\btime=(\d+):(\d+):(\d+)\.(\d+)")


def _ParseHms(H, M, S, Cs):
    return int(H) * 3600 + int(M) * 60 + int(S) + int(Cs) / 100.0


def _RunFfmpegStreaming(Cmd, ProgressCallback):
    Proc = subprocess.Popen(Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1, creationflags=NoWindowFlags())
    StderrChunks = []
    TotalSec = None
    LastPct = -1
    for Line in iter(Proc.stderr.readline, ''):
        StderrChunks.append(Line)
        if TotalSec is None:
            DurMatch = _FF_DUR_RE.search(Line)
            if DurMatch:
                TotalSec = _ParseHms(*DurMatch.groups())
        TimeMatch = _FF_TIME_RE.search(Line)
        if TimeMatch and TotalSec and TotalSec > 0 and ProgressCallback is not None:
            DoneSec = _ParseHms(*TimeMatch.groups())
            Pct = min(99, int(100.0 * DoneSec / TotalSec))
            if Pct != LastPct:
                LastPct = Pct
                try:
                    ProgressCallback(Pct)
                # fail-loud-ok: progress callback errors must not abort the ffmpeg subprocess; measurement still completes and returns stderr
                except Exception:
                    pass
    RC = Proc.wait(timeout=1800)
    Stderr = ''.join(StderrChunks)
    if RC != 0:
        raise RuntimeError(f"ffmpeg measurement exit {RC}: {Stderr[-500:]}")
    return Stderr


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class DemucsIsolationResult:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, VocalsWavPath, InstrumentalWavPath, VocalsRmsDbfs, PremixWavPath=None):
        self.VocalsWavPath = VocalsWavPath
        self.InstrumentalWavPath = InstrumentalWavPath
        self.VocalsRmsDbfs = VocalsRmsDbfs
        self.PremixWavPath = PremixWavPath


# directive: demucs-liveness | # see demucs-daemon.C5 -- hardware flags decide the device; cpu only when the worker has neither GPU flag
def DeviceForCapabilities(NvencCapable, QsvCapable):
    if NvencCapable:
        return 'cuda'
    if QsvCapable:
        return 'xpu'
    return 'cpu'


# directive: demucs-liveness | # see demucs-daemon.C5 -- reads this worker's Workers row fresh; a missing row raises
def RequiredDemucsDevice():
    from Core.Database.DatabaseService import DatabaseService
    from Core.WorkerContext import WorkerContext
    WorkerName = WorkerContext.Current().WorkerName
    Rows = DatabaseService().ExecuteQuery(
        "SELECT NvencCapable, QsvCapable FROM Workers WHERE WorkerName = %s", (WorkerName,))
    if not Rows:
        raise RuntimeError(f"RequiredDemucsDevice: no Workers row for '{WorkerName}'")
    return DeviceForCapabilities(bool(Rows[0]['NvencCapable']), bool(Rows[0]['QsvCapable']))


# directive: demucs-liveness | # see demucs-daemon.C13 -- pulls the loudnorm JSON block out of ffmpeg stderr; no block or a missing field raises
def ParseLoudnormMeasurement(StderrText, What):
    Match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", StderrText, re.DOTALL)
    if not Match:
        raise RuntimeError(f"{What}: ffmpeg loudnorm printed no measurement block. stderr tail={StderrText[-400:]}")
    try:
        Payload = json.loads(Match.group(0))
        return (
            float(Payload["input_i"]),
            float(Payload["input_lra"]),
            float(Payload["input_tp"]),
            float(Payload["input_thresh"]),
        )
    except (ValueError, KeyError) as Ex:
        raise RuntimeError(f"{What}: ffmpeg loudnorm block unreadable ({Ex}). block={Match.group(0)[:400]}") from Ex


# directive: demucs-liveness | # see demucs-daemon.C13 -- last "RMS level dB" in astats output; "-inf" is true silence and maps to the floor; no line or an unreadable value raises
def ParseAstatsRmsDbfs(StderrText, What):
    Values = []
    for Line in StderrText.splitlines():
        if "RMS level dB:" in Line:
            Token = Line.split("RMS level dB:")[1].strip()
            Values.append(SILENCE_FLOOR_DBFS if Token == "-inf" else float(Token))
    if not Values:
        raise RuntimeError(f"{What}: ffmpeg astats printed no RMS level. stderr tail={StderrText[-400:]}")
    return Values[-1]


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class DemucsVocalIsolationService:

    # directive: transcode-flow-canonical -- long-lived daemon amortizes model load + XPU compile; device detection lives inside DemucsDaemonEntry
    def __init__(self, FfmpegPath, PythonExe=None, ModelName=DEMUCS_MODEL_NAME, Daemon=None):
        self.FfmpegPath = FfmpegPath
        self.PythonExe = PythonExe or sys.executable
        self.ModelName = ModelName
        self._Daemon = Daemon

    # directive: audio-preencode-progress -- ProgressCallback forwarded to daemon: fires (percent, done_sec, total_sec) per tqdm tick from Demucs subprocess stderr
    def IsolateVocals(self, StereoInputWavPath, OutputDir, ProgressCallback=None):
        os.makedirs(OutputDir, exist_ok=True)
        LoggingService.LogInfo(
            f"Demucs isolating {StereoInputWavPath} -> {OutputDir} (via daemon)",
            "DemucsVocalIsolationService", "IsolateVocals",
        )
        Daemon = self._GetDaemon()
        Resp = Daemon.IsolateVocals(StereoInputWavPath, OutputDir, ModelName=self.ModelName, ProgressCallback=ProgressCallback)
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

    # directive: demucs-liveness | # see demucs-daemon.C5
    def _GetDaemon(self):
        if self._Daemon is None:
            from Features.AudioNormalization.Services.DemucsDaemonClient import GetOrStartDaemon
            self._Daemon = GetOrStartDaemon(RequiredDemucsDevice(), PythonExe=self.PythonExe)
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
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=1800, creationflags=NoWindowFlags())
        if Result.returncode != 0:
            raise RuntimeError(
                f"premix ffmpeg failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        IsolationResult.PremixWavPath = OutputWavPath
        return IsolationResult

    # directive: audio-preencode-progress -- ffmpeg's single-pass loudnorm measurement can take 30-90s on a 24-min file; stream stderr, parse Duration + time= ticks, invoke ProgressCallback so /Activity shows live percent instead of 60s of frozen 0%. Drops `-nostats` so ffmpeg emits progress.
    def MeasureSourceLoudnorm(self, SourcePath, TargetLufs, TargetLra, TargetTruePeakDbtp, ProgressCallback=None):
        Filter = f"loudnorm=I={float(TargetLufs):.2f}:LRA={float(TargetLra):.2f}:TP={float(TargetTruePeakDbtp):.2f}:print_format=json"
        StderrText = _RunFfmpegStreaming(
            [self.FfmpegPath, "-hide_banner", "-i", SourcePath, "-map", "0:a:0", "-af", Filter, "-f", "null", "-"],
            ProgressCallback,
        )
        return ParseLoudnormMeasurement(StderrText, f"Source loudness of {SourcePath}")

    # directive: audio-preencode-progress -- premix loudnorm measurement streams ffmpeg time= per second; drop -nostats. Same shape as MeasureSourceLoudnorm.
    def MeasurePremixLoudnorm(self, WavPath, TargetLufs, TargetLra, TargetTruePeakDbtp, ProgressCallback=None):
        Filter = f"loudnorm=I={float(TargetLufs):.2f}:LRA={float(TargetLra):.2f}:TP={float(TargetTruePeakDbtp):.2f}:print_format=json"
        StderrText = _RunFfmpegStreaming(
            [self.FfmpegPath, "-hide_banner", "-i", WavPath, "-af", Filter, "-f", "null", "-"],
            ProgressCallback,
        )
        return ParseLoudnormMeasurement(StderrText, f"Premix loudness of {WavPath}")

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _MeasureWavRmsDbfs(self, WavPath):
        Result = subprocess.run(
            [self.FfmpegPath, "-i", WavPath, "-map", "0:a:0", "-af", "astats", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120, creationflags=NoWindowFlags()
        )
        return ParseAstatsRmsDbfs(Result.stderr, f"Vocals level of {WavPath}")
