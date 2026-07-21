from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


_RE_INTEGRATED = re.compile(r'I:\s+(-?\d+(?:\.\d+)?)\s+LUFS')
_RE_LRA = re.compile(r'LRA:\s+(-?\d+(?:\.\d+)?)\s+LU')
_RE_PEAK = re.compile(r'Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS')
_RE_INTEGRATED_THRESHOLD = re.compile(
    r'Integrated loudness:[\s\S]*?Threshold:\s+(-?\d+(?:\.\d+)?)\s+LUFS'
)


PERSIST_WITH_FINGERPRINT_SQL = (
    "UPDATE MediaFiles "
    "SET SourceIntegratedLufs = %s, "
    "SourceLoudnessRangeLU = %s, "
    "SourceTruePeakDbtp = %s, "
    "SourceIntegratedThresholdLufs = %s, "
    "LoudnessMeasuredAt = NOW(), "
    "LastProbedFileSize = %s, "
    "LastProbedFileMtime = %s "
    "WHERE Id = %s"
)


PERSIST_MEASUREMENT_ONLY_SQL = (
    "UPDATE MediaFiles "
    "SET SourceIntegratedLufs = %s, "
    "SourceLoudnessRangeLU = %s, "
    "SourceTruePeakDbtp = %s, "
    "SourceIntegratedThresholdLufs = %s, "
    "LoudnessMeasuredAt = NOW() "
    "WHERE Id = %s"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
@dataclass
class LoudnessResult:
    """Four EBU R128 measurements anchored to a single audio stream."""
    IntegratedLufs: float
    LoudnessRangeLU: float
    TruePeakDbtp: float
    IntegratedThresholdLufs: float


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
def ParseSummary(Stderr):
    """Extract (Integrated, LRA, TruePeak, Threshold) from ebur128 stderr Summary block; fall back to last occurrences."""
    Marker = 'Summary:'
    Idx = Stderr.rfind(Marker)
    Tail = Stderr[Idx:] if Idx >= 0 else Stderr

    I = _RE_INTEGRATED.search(Tail) if Idx >= 0 else None
    L = _RE_LRA.search(Tail) if Idx >= 0 else None
    P = _RE_PEAK.search(Tail)
    T = _RE_INTEGRATED_THRESHOLD.search(Tail) if Idx >= 0 else None

    if not (I and L and P and T):
        I_All = _RE_INTEGRATED.findall(Stderr)
        L_All = _RE_LRA.findall(Stderr)
        P_All = _RE_PEAK.findall(Stderr)
        T_All = _RE_INTEGRATED_THRESHOLD.findall(Stderr)
        if not (I_All and L_All and P_All and T_All):
            return None
        return LoudnessResult(
            float(I_All[-1]), float(L_All[-1]), float(P_All[-1]), float(T_All[-1])
        )

    return LoudnessResult(
        float(I.group(1)), float(L.group(1)), float(P.group(1)), float(T.group(1))
    )


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
class EbuR128MeasurementService:
    """ebur128 measurement + DB persistence; absorbed from Features/LoudnessAnalysis."""

    DEFAULT_TIMEOUT_SECONDS = 600

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def __init__(self, FFmpegPath=None):
        """Bind to a specific ffmpeg binary; resolve from WorkerContext when None."""
        self._FFmpegPathOverride = FFmpegPath

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C21
    def _ResolveFFmpegPath(self):
        """Return the bound override or the WorkerContext value; raise when neither available."""
        if self._FFmpegPathOverride:
            return self._FFmpegPathOverride
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.TryCurrent()
            if Ctx and Ctx.FFmpegPath:
                return Ctx.FFmpegPath
        except Exception:
            pass
        raise RuntimeError(
            "FFmpegPath unavailable -- pass explicitly to EbuR128MeasurementService "
            "or initialize WorkerContext in this process"
        )

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def MeasureLoudness(self, LocalFilePath, AudioStreamIndex=0, TimeoutSeconds=None):
        """Run ebur128 against one audio stream; return (LoudnessResult, None) on success or (None, FailureReason)."""
        FFmpegPath = self._ResolveFFmpegPath()
        Timeout = TimeoutSeconds or self.DEFAULT_TIMEOUT_SECONDS
        NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
        Cmd = [
            FFmpegPath,
            '-hide_banner', '-nostats', '-nostdin',
            '-i', LocalFilePath,
            '-map', f'0:a:{AudioStreamIndex}',
            '-af', 'ebur128=peak=true',
            '-f', 'null',
            NullSink,
        ]
        try:
            Result = subprocess.run(
                Cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=Timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, 'timeout'
        except FileNotFoundError:
            return None, 'ffmpeg_not_found'

        if Result.returncode != 0:
            return None, f'ffmpeg_exit_{Result.returncode}'

        Stderr = Result.stderr.decode('utf-8', errors='replace')
        Parsed = ParseSummary(Stderr)
        if Parsed is None:
            return None, 'parse_failed'
        return Parsed, None

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C28 -- FailureReason column deleted; MeasureAndPersist still returns it for the caller to log, but nothing persists it (was legacy off-contract cruft that raced with worker encodes).
    def PersistLoudness(self, MediaFileId, Loudness, FileSize=None, FileMtime=None):
        """Write the four loudness columns + change-detection fingerprint."""
        try:
            I = Loudness.IntegratedLufs if Loudness else None
            L = Loudness.LoudnessRangeLU if Loudness else None
            P = Loudness.TruePeakDbtp if Loudness else None
            T = Loudness.IntegratedThresholdLufs if Loudness else None
            if FileSize is not None and FileMtime is not None:
                DatabaseService().ExecuteNonQuery(
                    PERSIST_WITH_FINGERPRINT_SQL,
                    (I, L, P, T, FileSize, FileMtime, MediaFileId),
                )
            else:
                DatabaseService().ExecuteNonQuery(
                    PERSIST_MEASUREMENT_ONLY_SQL,
                    (I, L, P, T, MediaFileId),
                )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"PersistLoudness failed for MediaFileId={MediaFileId}",
                Ex, "EbuR128MeasurementService", "PersistLoudness",
            )
            return False

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    @staticmethod
    def IsMeasurementStale(MediaFile):
        """True when LoudnessMeasuredAt is NULL or on-disk size/mtime differ from LastProbedFileSize/LastProbedFileMtime."""
        if getattr(MediaFile, 'LoudnessMeasuredAt', None) is None:
            return True
        Size = getattr(MediaFile, 'CurrentFileSize', None)
        Mtime = getattr(MediaFile, 'CurrentFileMtime', None)
        LastSize = getattr(MediaFile, 'LastProbedFileSize', None)
        LastMtime = getattr(MediaFile, 'LastProbedFileMtime', None)
        if Size is None or Mtime is None:
            return False
        if LastSize is None or LastMtime is None:
            return True
        return (Size != LastSize) or (abs((Mtime - LastMtime).total_seconds()) >= 1)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def MeasureAndPersist(self, MediaFileId, LocalFilePath, AudioStreamIndex=0):
        """Convenience: stat + measure + persist; returns (Success, FailureReason)."""
        try:
            Stat = os.stat(LocalFilePath)
        except OSError as Ex:
            return False, f'stat_failed: {Ex}'

        FileSize = Stat.st_size
        FileMtime = datetime.fromtimestamp(Stat.st_mtime)

        Loudness, Reason = self.MeasureLoudness(LocalFilePath, AudioStreamIndex)
        Ok = self.PersistLoudness(MediaFileId, Loudness, FileSize, FileMtime)
        return Ok, Reason
