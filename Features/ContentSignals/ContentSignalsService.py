"""Content signal extraction.

Runs ffmpeg signalstats + PySceneDetect on a source file; returns aggregated
MotionFraction / SceneChangeRatePerMin / LumaVariance. Never raises -- failure
returns None and is logged.

See Features/ContentSignals/content-signals.feature.md.
"""

import os
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from Core.Logging.LoggingService import LoggingService
from Core.PathStorage import Join, LocalExists, ParentDir
from Features.ContentSignals.Models.ContentSignalsModel import ContentSignalsModel


_FFMPEG_TIMEOUT_SEC = 600
_SIGNALSTATS_FRAME_INTERVAL = 24
_MOTION_THRESHOLD_YDIF = 8.0


def _GetFfmpegPath() -> Optional[str]:
    try:
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        if Ctx and Ctx.FFmpegPath and LocalExists(Ctx.FFmpegPath):
            return Ctx.FFmpegPath
    except Exception:
        pass
    for Candidate in (
        Join(Join(ParentDir(ParentDir(ParentDir(__file__))), "FFmpegMaster"), Join("bin", "ffmpeg.exe")),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ):
        if Candidate and LocalExists(Candidate):
            return Candidate
    return None


def _RunSignalstats(FfmpegPath: str, LocalFilePath: str) -> Optional[dict]:
    """Returns dict with MotionFraction + LumaVariance or None on failure."""
    Cmd = [
        FfmpegPath,
        "-hide_banner", "-loglevel", "info",
        "-i", LocalFilePath,
        "-vf", f"select='not(mod(n\\,{_SIGNALSTATS_FRAME_INTERVAL}))',signalstats,metadata=mode=print",
        "-an", "-sn",
        "-f", "null", "-",
    ]
    try:
        R = subprocess.run(Cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        LoggingService.LogWarning(
            f"signalstats timeout after {_FFMPEG_TIMEOUT_SEC}s on {LocalFilePath}",
            "ContentSignalsService", "_RunSignalstats",
        )
        return None
    except Exception as Ex:
        LoggingService.LogException(
            f"signalstats failed on {LocalFilePath}", Ex,
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


def _RunScenedetect(LocalFilePath: str) -> Optional[float]:
    """Returns SceneChangeRatePerMin or None on failure."""
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        LoggingService.LogWarning(
            "PySceneDetect not installed; SceneChangeRatePerMin will be NULL. "
            "Add 'scenedetect>=0.6.0' to the worker venv.",
            "ContentSignalsService", "_RunScenedetect",
        )
        return None

    try:
        Video = open_video(LocalFilePath)
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
            f"scenedetect failed on {LocalFilePath}", Ex,
            "ContentSignalsService", "_RunScenedetect",
        )
        return None


class ContentSignalsService:
    @staticmethod
    def ComputeSignals(LocalFilePath: str) -> Optional[ContentSignalsModel]:
        if not LocalFilePath or not LocalExists(LocalFilePath):
            LoggingService.LogWarning(
                f"ComputeSignals: file not found at {LocalFilePath}",
                "ContentSignalsService", "ComputeSignals",
            )
            return None

        FfmpegPath = _GetFfmpegPath()
        if not FfmpegPath:
            LoggingService.LogWarning(
                "ComputeSignals: ffmpeg not resolvable from WorkerContext",
                "ContentSignalsService", "ComputeSignals",
            )
            return None

        T0 = time.time()
        Stats = _RunSignalstats(FfmpegPath, LocalFilePath)
        SceneRate = _RunScenedetect(LocalFilePath)
        Dt = time.time() - T0

        if Stats is None and SceneRate is None:
            LoggingService.LogWarning(
                f"ComputeSignals: both signalstats and scenedetect returned no data for {LocalFilePath}",
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
            f"ContentSignals computed in {Dt:.1f}s: motion={Model.MotionFraction} "
            f"scene_rate={Model.SceneChangeRatePerMin} luma_var={Model.LumaVariance} ({LocalFilePath})",
            "ContentSignalsService", "ComputeSignals",
        )
        return Model
