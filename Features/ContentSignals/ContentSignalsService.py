import os
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists
from Features.ContentSignals.Models.ContentSignalsModel import ContentSignalsModel


_FFMPEG_TIMEOUT_SEC = 600
_SIGNALSTATS_FRAME_INTERVAL = 24
_MOTION_THRESHOLD_YDIF = 8.0


# directive: path-schema-migration | # see path.S9
def _GetFfmpegPath() -> Optional[str]:
    try:
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        FfmpegCandidate = Ctx.FFmpegPath if Ctx else None
        if LocalExists(FfmpegCandidate):
            return FfmpegCandidate
    except Exception:
        pass
    Base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    for Candidate in (
        os.path.join(Base, "FFmpegMaster", "bin", "ffmpeg.exe"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ):
        if LocalExists(Candidate):
            return Candidate
    return None


# directive: path-schema-migration | # see path.S5
def _RunSignalstats(FfmpegBinary: str, LocalFile: str) -> Optional[dict]:
    """Returns dict with MotionFraction + LumaVariance or None on failure."""
    Cmd = [
        FfmpegBinary,
        "-hide_banner", "-loglevel", "info",
        "-i", LocalFile,
        "-vf", f"select='not(mod(n\\,{_SIGNALSTATS_FRAME_INTERVAL}))',signalstats,metadata=mode=print",
        "-an", "-sn",
        "-f", "null", "-",
    ]
    try:
        R = subprocess.run(Cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        LoggingService.LogWarning(
            f"signalstats timeout after {_FFMPEG_TIMEOUT_SEC}s on {LocalFile}",
            "ContentSignalsService", "_RunSignalstats",
        )
        return None
    except Exception as Ex:
        LoggingService.LogException(
            f"signalstats failed on {LocalFile}", Ex,
            "ContentSignalsService", "_RunSignalstats",
        )
        return None

    if R.returncode != 0:
        return None

    YdifValues = []
    YlowValues = []
    YhighValues = []
    YdifRe = re.compile(r"lavfi\.signalstats\.YDIF=([\d.]+)")
    YlowRe = re.compile(r"lavfi\.signalstats\.YLOW=([\d.]+)")
    YhighRe = re.compile(r"lavfi\.signalstats\.YHIGH=([\d.]+)")
    for Line in (R.stderr or "").splitlines():
        Ym = YdifRe.search(Line)
        if Ym:
            try:
                YdifValues.append(float(Ym.group(1)))
            except ValueError:
                pass
        Lm = YlowRe.search(Line)
        if Lm:
            try:
                YlowValues.append(float(Lm.group(1)))
            except ValueError:
                pass
        Hm = YhighRe.search(Line)
        if Hm:
            try:
                YhighValues.append(float(Hm.group(1)))
            except ValueError:
                pass

    if not YdifValues:
        return None

    MotionFrames = sum(1 for V in YdifValues if V >= _MOTION_THRESHOLD_YDIF)
    MotionFraction = MotionFrames / len(YdifValues)

    LumaVariance = None
    if YlowValues and YhighValues and len(YlowValues) == len(YhighValues):
        Spreads = [(YhighValues[I] - YlowValues[I]) for I in range(len(YlowValues))]
        Mean = sum(Spreads) / len(Spreads)
        LumaVariance = sum((S - Mean) ** 2 for S in Spreads) / len(Spreads)

    return {
        "MotionFraction": MotionFraction,
        "LumaVariance": LumaVariance,
        "FramesSampled": len(YdifValues),
    }


# directive: path-schema-migration | # see path.S5
def _RunScenedetect(LocalFile: str) -> Optional[float]:
    """Returns SceneChangeRatePerMin or None on failure."""
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        LoggingService.LogWarning(
            "PySceneDetect not installed; SceneChangeRatePerMin will be NULL. Add 'scenedetect>=0.6.0' to the worker venv.",
            "ContentSignalsService", "_RunScenedetect",
        )
        return None

    try:
        Video = open_video(LocalFile)
        Manager = SceneManager()
        Manager.add_detector(ContentDetector())
        Manager.detect_scenes(video=Video, show_progress=False)
        Scenes = Manager.get_scene_list()
        DurationSec = float(Video.duration.get_seconds()) if hasattr(Video, "duration") else 0.0
        if DurationSec <= 0:
            return None
        return (len(Scenes) / DurationSec) * 60.0
    except Exception as Ex:
        LoggingService.LogException(
            f"scenedetect failed on {LocalFile}", Ex,
            "ContentSignalsService", "_RunScenedetect",
        )
        return None


# directive: path-schema-migration | # see path.S5
class ContentSignalsService:
    @staticmethod
    # directive: path-schema-migration | # see path.S5
    def ComputeSignals(LocalFilePath: str) -> Optional[ContentSignalsModel]:
        LocalFile = LocalFilePath
        if not LocalExists(LocalFile):
            LoggingService.LogWarning(
                f"ComputeSignals: file not found at {LocalFile}",
                "ContentSignalsService", "ComputeSignals",
            )
            return None

        FfmpegBinary = _GetFfmpegPath()
        if not FfmpegBinary:
            LoggingService.LogWarning(
                "ComputeSignals: ffmpeg not resolvable from WorkerContext",
                "ContentSignalsService", "ComputeSignals",
            )
            return None

        T0 = time.time()
        Stats = _RunSignalstats(FfmpegBinary, LocalFile)
        SceneRate = _RunScenedetect(LocalFile)
        Dt = time.time() - T0

        if Stats is None and SceneRate is None:
            LoggingService.LogWarning(
                f"ComputeSignals: both signalstats and scenedetect returned no data for {LocalFile}",
                "ContentSignalsService", "ComputeSignals",
            )
            return None

        Model = ContentSignalsModel(
            MotionFraction=Stats.get("MotionFraction") if Stats else None,
            SceneChangeRatePerMin=SceneRate,
            LumaVariance=Stats.get("LumaVariance") if Stats else None,
            ComputedAt=datetime.now(timezone.utc),
        )

        LoggingService.LogInfo(
            f"ContentSignals computed in {Dt:.1f}s: motion={Model.MotionFraction} scene_rate={Model.SceneChangeRatePerMin} luma_var={Model.LumaVariance} ({LocalFile})",
            "ContentSignalsService", "ComputeSignals",
        )
        return Model
