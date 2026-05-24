"""Reusable assertion helpers for pipeline tests.

Every helper raises AssertionError with a descriptive message on
mismatch. None of these mutate state.

See Tests/Pipeline/pipeline-test-harness.feature.md criteria 8-12.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Any, Optional

from Core.Database.DatabaseService import DatabaseService


# Reused from Features/LoudnessAnalysis -- single source of truth for parser.
from Features.LoudnessAnalysis.LoudnessAnalysisService import ParseSummary


def _ResolveFFmpegPath() -> str:
    from Core.WorkerContext import WorkerContext
    Ctx = WorkerContext.Current()
    if Ctx and Ctx.FFmpegPath:
        return Ctx.FFmpegPath
    Env = os.environ.get('FFMPEG_PATH')
    if Env:
        return Env
    raise RuntimeError(
        "FFmpegPath unavailable. Initialize WorkerContext before calling "
        "assertions, or set FFMPEG_PATH env var."
    )


def _ResolveFFprobePath() -> str:
    from Core.WorkerContext import WorkerContext
    Ctx = WorkerContext.Current()
    if Ctx and Ctx.FFprobePath:
        return Ctx.FFprobePath
    # Sibling of ffmpeg by convention
    FFmpeg = _ResolveFFmpegPath()
    Candidate = FFmpeg.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')
    if os.path.exists(Candidate):
        return Candidate
    return 'ffprobe'  # rely on PATH


def AssertIntegratedLoudnessNear(
    FilePath: str,
    TargetLufs: float,
    ToleranceLU: float = 1.0,
    AudioStreamIndex: int = 0,
) -> None:
    """Run ebur128 on the file's audio; assert Integrated within tolerance.

    Raises AssertionError naming measured vs expected on mismatch.
    """
    if not os.path.exists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
    Cmd = [
        FFmpeg, '-hide_banner', '-nostats', '-nostdin',
        '-i', FilePath,
        '-map', f'0:a:{AudioStreamIndex}',
        '-af', 'ebur128=peak=true',
        '-f', 'null', NullSink,
    ]
    Result = subprocess.run(Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900, check=False)
    if Result.returncode != 0:
        raise AssertionError(f"ebur128 ffmpeg exited with code {Result.returncode} on {FilePath}")
    Parsed = ParseSummary(Result.stderr.decode('utf-8', errors='replace'))
    if Parsed is None:
        raise AssertionError(f"ebur128 stderr missing Summary block for {FilePath}")
    Delta = abs(Parsed.IntegratedLufs - TargetLufs)
    if Delta > ToleranceLU:
        raise AssertionError(
            f"Integrated loudness out of tolerance for {FilePath}: "
            f"measured={Parsed.IntegratedLufs:.2f} LUFS, target={TargetLufs:.2f} LUFS, "
            f"delta={Delta:.2f} LU, tolerance={ToleranceLU:.2f} LU"
        )


def AssertTruePeakAtOrBelow(
    FilePath: str,
    MaxDbtp: float,
    AudioStreamIndex: int = 0,
) -> None:
    """Same ebur128 pass as Integrated; assert measured peak <= MaxDbtp."""
    if not os.path.exists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
    Cmd = [
        FFmpeg, '-hide_banner', '-nostats', '-nostdin',
        '-i', FilePath,
        '-map', f'0:a:{AudioStreamIndex}',
        '-af', 'ebur128=peak=true',
        '-f', 'null', NullSink,
    ]
    Result = subprocess.run(Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900, check=False)
    if Result.returncode != 0:
        raise AssertionError(f"ebur128 ffmpeg exited with code {Result.returncode} on {FilePath}")
    Parsed = ParseSummary(Result.stderr.decode('utf-8', errors='replace'))
    if Parsed is None:
        raise AssertionError(f"ebur128 stderr missing Summary block for {FilePath}")
    if Parsed.TruePeakDbtp > MaxDbtp:
        raise AssertionError(
            f"True peak exceeds ceiling for {FilePath}: "
            f"measured={Parsed.TruePeakDbtp:.2f} dBTP, max={MaxDbtp:.2f} dBTP"
        )


def AudioStreamHash(FilePath: str, AudioStreamIndex: int = 0) -> str:
    """SHA-256 of the file's audio stream bytes via ffmpeg -c copy.

    Used by AssertAudioBytesIdentical and exposed for callers that want
    to capture a hash now and compare later.
    """
    if not os.path.exists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    Cmd = [
        FFmpeg, '-hide_banner', '-nostats', '-nostdin', '-loglevel', 'error',
        '-i', FilePath,
        '-map', f'0:a:{AudioStreamIndex}',
        '-c', 'copy', '-f', 'data', '-',
    ]
    Proc = subprocess.Popen(Cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    H = hashlib.sha256()
    while True:
        Chunk = Proc.stdout.read(1024 * 1024)
        if not Chunk:
            break
        H.update(Chunk)
    Proc.wait(timeout=300)
    if Proc.returncode != 0:
        Err = Proc.stderr.read().decode('utf-8', errors='replace')[:500]
        raise AssertionError(f"ffmpeg audio-copy hash failed for {FilePath}: {Err}")
    return H.hexdigest()


def AssertAudioBytesIdentical(
    PathA: str,
    PathB: str,
    AudioStreamIndex: int = 0,
) -> None:
    """Assert audio streams of A and B are byte-identical via -c copy hash.

    Used to prove `-c:a copy` did its job (no re-encode introduced any change).
    """
    Ha = AudioStreamHash(PathA, AudioStreamIndex)
    Hb = AudioStreamHash(PathB, AudioStreamIndex)
    if Ha != Hb:
        raise AssertionError(
            f"Audio streams differ:\n"
            f"  A ({PathA}): {Ha}\n"
            f"  B ({PathB}): {Hb}"
        )


def AssertDbState(MediaFileId: int, **Expected: Any) -> None:
    """Assert MediaFiles row columns match expected kwargs.

    Column names match the DB (case-insensitive). Use Python None for SQL NULL.
    Example:
        AssertDbState(123, AudioComplete=True, IsCompliant=True,
                      RecommendedMode=None)
    """
    if not Expected:
        return
    Db = DatabaseService()
    Cols = ','.join(Expected.keys())
    Rows = Db.ExecuteQuery(
        f"SELECT {Cols} FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        raise AssertionError(f"MediaFile {MediaFileId} not found for DB assert")
    Row = dict(Rows[0])
    # CaseInsensitiveDict from MediaVortex would map keys; defensive lowercase.
    Mismatches = []
    for Key, Want in Expected.items():
        # The query columns come back lowercase from psycopg2
        Got = Row.get(Key.lower(), Row.get(Key))
        if Got != Want:
            Mismatches.append(f"  {Key}: expected={Want!r} actual={Got!r}")
    if Mismatches:
        Joined = "\n".join(Mismatches)
        raise AssertionError(
            f"MediaFile {MediaFileId} DB state mismatch:\n{Joined}"
        )


def AssertNoQueueRows(MediaFileId: int) -> None:
    """Assert TranscodeQueue is empty for this file AND queue flags are clear."""
    Db = DatabaseService()
    QueueRows = Db.ExecuteQuery(
        "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s",
        (MediaFileId,),
    )
    if QueueRows:
        Ids = [int(R['Id']) for R in QueueRows]
        raise AssertionError(
            f"MediaFile {MediaFileId} still has TranscodeQueue rows: {Ids}"
        )
    Flags = Db.ExecuteQuery(
        "SELECT NeedsQuick, NeedsTranscode, IsCompliant, RecommendedMode "
        "FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Flags:
        raise AssertionError(f"MediaFile {MediaFileId} not found")
    F = dict(Flags[0])
    Nq = F.get('needsquick')
    Nt = F.get('needstranscode')
    Rm = F.get('recommendedmode')
    Issues = []
    if Nq:
        Issues.append(f"NeedsQuick=True (expected False)")
    if Nt:
        Issues.append(f"NeedsTranscode=True (expected False)")
    if Rm:
        Issues.append(f"RecommendedMode={Rm!r} (expected None)")
    if Issues:
        Joined = "; ".join(Issues)
        raise AssertionError(
            f"MediaFile {MediaFileId} still flagged for queue: {Joined}"
        )


def AssertVideoCodecMatchesProfile(MediaFileId: int) -> None:
    """Assert the file's current video codec matches its AssignedProfile codec."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT m.FilePath, m.Codec AS CurrentCodec, m.AssignedProfile, p.Codec AS ProfileCodec "
        "FROM MediaFiles m LEFT JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE m.Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        raise AssertionError(f"MediaFile {MediaFileId} not found")
    R = dict(Rows[0])
    CurrentCodec = (R.get('currentcodec') or '').lower().strip()
    ProfileCodec = (R.get('profilecodec') or '').lower().strip()
    if not ProfileCodec:
        raise AssertionError(
            f"MediaFile {MediaFileId} has no resolvable AssignedProfile codec "
            f"(AssignedProfile={R.get('assignedprofile')!r})"
        )
    # libsvtav1 in Profiles -> av1 in MediaFiles after ffprobe re-parses
    # the encoded output. Normalize the known aliasing.
    Aliases = {
        'libsvtav1': 'av1', 'libaom-av1': 'av1', 'av1_nvenc': 'av1',
        'libx264': 'h264', 'libx265': 'hevc', 'hevc_nvenc': 'hevc',
    }
    Normalized = Aliases.get(ProfileCodec, ProfileCodec)
    if CurrentCodec != Normalized:
        raise AssertionError(
            f"MediaFile {MediaFileId} video codec mismatch: "
            f"current={CurrentCodec!r}, profile={ProfileCodec!r} "
            f"(normalized to {Normalized!r}), file={R.get('filepath')!r}"
        )
