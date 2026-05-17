"""LoudnessAnalysisService -- owns ebur128 measurement and persistence.

Captures three EBU R128 values per audio stream:
  - Integrated loudness (LUFS) -- "how loud is this file overall"
  - Loudness range (LU)        -- "how much do volumes vary inside this file"
  - True peak (dBTP)           -- "will peaks clip on cheap DACs"

Plus the on-disk fingerprint (size + mtime) so a future reprobe can short-circuit
unchanged files.

See:
- Features/TranscodeQueue/media-tabs-and-loudness.feature.md (criteria 5-6)
- Scripts/SQLScripts/BackfillProbeAndLoudness.py (Phase 1 throwaway script that
  this module supersedes for the steady-state probe pipeline)
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


# ---------- Result model ----------

@dataclass
class LoudnessResult:
    IntegratedLufs: float
    LoudnessRangeLU: float
    TruePeakDbtp: float


# ---------- Parser ----------

# `I:`, `LRA:` and `Peak:` also appear in per-frame PROGRESS lines emitted by
# the ebur128 filter while it runs. The progress values converge from the
# silence floor (-70 LUFS) toward the true value, so a first-match regex
# captures nonsense. We anchor parsing to the `Summary:` marker emitted at the
# end of the run (the canonical, final values).
_RE_INTEGRATED = re.compile(r'I:\s+(-?\d+(?:\.\d+)?)\s+LUFS')
_RE_LRA = re.compile(r'LRA:\s+(-?\d+(?:\.\d+)?)\s+LU')
_RE_PEAK = re.compile(r'Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS')


def ParseSummary(Stderr: str) -> Optional[LoudnessResult]:
    """Extract (Integrated, LRA, TruePeak) from ebur128 stderr output.

    Returns None when any field is missing. Anchors to the summary block at the
    tail of stderr; falls back to the LAST occurrence in the full text if the
    summary marker isn't present.
    """
    Marker = 'Summary:'
    Idx = Stderr.rfind(Marker)
    Tail = Stderr[Idx:] if Idx >= 0 else Stderr

    I = _RE_INTEGRATED.search(Tail) if Idx >= 0 else None
    L = _RE_LRA.search(Tail) if Idx >= 0 else None
    P = _RE_PEAK.search(Tail)

    if not (I and L and P):
        I_All = _RE_INTEGRATED.findall(Stderr)
        L_All = _RE_LRA.findall(Stderr)
        P_All = _RE_PEAK.findall(Stderr)
        if not (I_All and L_All and P_All):
            return None
        return LoudnessResult(float(I_All[-1]), float(L_All[-1]), float(P_All[-1]))

    return LoudnessResult(float(I.group(1)), float(L.group(1)), float(P.group(1)))


# ---------- Service ----------

class LoudnessAnalysisService:
    """Pure-logic + DB-write service. Construct per call or reuse."""

    DEFAULT_TIMEOUT_SECONDS = 600  # 10 min; covers 4-hour movies at >50x realtime decode

    def __init__(self, FFmpegPath: Optional[str] = None):
        """Bind to a specific FFmpeg binary.

        When FFmpegPath is None, resolves from WorkerContext.Current() at call
        time. If that returns None too, MeasureLoudness raises -- callers must
        either pass FFmpegPath or run inside a worker process.
        """
        self._FFmpegPathOverride = FFmpegPath

    def _ResolveFFmpegPath(self) -> str:
        if self._FFmpegPathOverride:
            return self._FFmpegPathOverride
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx and Ctx.FFmpegPath:
                return Ctx.FFmpegPath
        except Exception:
            pass
        raise RuntimeError(
            "FFmpegPath unavailable -- pass explicitly to LoudnessAnalysisService "
            "or initialize WorkerContext in this process"
        )

    def MeasureLoudness(
        self,
        LocalFilePath: str,
        AudioStreamIndex: int = 0,
        TimeoutSeconds: Optional[int] = None,
    ) -> Tuple[Optional[LoudnessResult], Optional[str]]:
        """Run ebur128 against a single audio stream of the file.

        LocalFilePath is the path FFmpeg will open -- caller must translate from
        the canonical DB path via PathTranslation before this call.

        Returns (LoudnessResult, None) on success, or (None, FailureReason) on
        any failure. FailureReason is a stable short identifier:
          'ffmpeg_not_found'  -- binary at FFmpegPath does not exist
          'timeout'           -- decode exceeded TimeoutSeconds
          'ffmpeg_exit_<N>'   -- non-zero exit code (codec error, no audio, etc.)
          'parse_failed'      -- ffmpeg ran cleanly but output didn't contain
                                 the expected summary block
        """
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

    def PersistLoudness(
        self,
        MediaFileId: int,
        Loudness: Optional[LoudnessResult],
        FileSize: Optional[int] = None,
        FileMtime: Optional[datetime] = None,
    ) -> bool:
        """Write the four loudness columns + the two change-detection columns.

        When `Loudness` is None (measurement failed) we still stamp
        LoudnessMeasuredAt=NOW() so the row drops out of the unmeasured set and
        we don't retry forever. The Phase 1 backfill uses the same semantic.
        FileSize/FileMtime: pass when caller stat'd the file (so the row is
        valid for future change-detection); leave None to preserve existing
        values.
        """
        try:
            I = Loudness.IntegratedLufs if Loudness else None
            L = Loudness.LoudnessRangeLU if Loudness else None
            P = Loudness.TruePeakDbtp if Loudness else None
            # Update size/mtime only when caller supplied them (don't NULL
            # existing values on a measurement-only refresh).
            if FileSize is not None and FileMtime is not None:
                DatabaseService().ExecuteNonQuery(
                    """
                    UPDATE MediaFiles
                    SET SourceIntegratedLufs  = %s,
                        SourceLoudnessRangeLU = %s,
                        SourceTruePeakDbtp    = %s,
                        LoudnessMeasuredAt    = NOW(),
                        LastProbedFileSize    = %s,
                        LastProbedFileMtime   = %s
                    WHERE Id = %s
                    """,
                    (I, L, P, FileSize, FileMtime, MediaFileId),
                )
            else:
                DatabaseService().ExecuteNonQuery(
                    """
                    UPDATE MediaFiles
                    SET SourceIntegratedLufs  = %s,
                        SourceLoudnessRangeLU = %s,
                        SourceTruePeakDbtp    = %s,
                        LoudnessMeasuredAt    = NOW()
                    WHERE Id = %s
                    """,
                    (I, L, P, MediaFileId),
                )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"PersistLoudness failed for MediaFileId={MediaFileId}",
                Ex, "LoudnessAnalysisService", "PersistLoudness",
            )
            return False

    @staticmethod
    def IsMeasurementStale(MediaFile) -> bool:
        """True when the file should be re-measured.

        Two conditions:
          - LoudnessMeasuredAt is NULL (never measured)
          - File's on-disk size or mtime differs from LastProbedFileSize /
            LastProbedFileMtime (file changed since last measurement)

        Note: this is a pure predicate; caller is responsible for filesystem
        access. Pass a MediaFile model populated with FileSize/FileMtime
        observed via os.stat against the local translated path.
        """
        if getattr(MediaFile, 'LoudnessMeasuredAt', None) is None:
            return True
        Size = getattr(MediaFile, 'CurrentFileSize', None)
        Mtime = getattr(MediaFile, 'CurrentFileMtime', None)
        LastSize = getattr(MediaFile, 'LastProbedFileSize', None)
        LastMtime = getattr(MediaFile, 'LastProbedFileMtime', None)
        if Size is None or Mtime is None:
            return False  # can't tell -- don't force re-measure
        if LastSize is None or LastMtime is None:
            return True   # no fingerprint to compare against
        return (Size != LastSize) or (abs((Mtime - LastMtime).total_seconds()) >= 1)

    def MeasureAndPersist(
        self,
        MediaFileId: int,
        LocalFilePath: str,
        AudioStreamIndex: int = 0,
    ) -> Tuple[bool, Optional[str]]:
        """Convenience: stat -> measure -> persist in one call.

        Returns (Success, FailureReason). Success means a row was written
        (even on measurement failure -- the row gets LoudnessMeasuredAt stamped
        with NULL measurement values so it drops out of the unmeasured set).

        Skip semantics: if stat fails, returns (False, 'stat_failed') WITHOUT
        writing a row -- transient issues (permission denied, NFS hiccup)
        should be retryable on a future pass from a worker with access.
        """
        try:
            Stat = os.stat(LocalFilePath)
        except OSError as Ex:
            return False, f'stat_failed: {Ex}'

        FileSize = Stat.st_size
        FileMtime = datetime.fromtimestamp(Stat.st_mtime)

        Loudness, Reason = self.MeasureLoudness(LocalFilePath, AudioStreamIndex)
        Ok = self.PersistLoudness(MediaFileId, Loudness, FileSize, FileMtime)
        return Ok, Reason
