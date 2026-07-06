from __future__ import annotations

import hashlib
import os
import subprocess
from typing import Any

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.Measurement.EbuR128MeasurementService import ParseSummary


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _DefaultTestFFmpegPath() -> str:
    """DB-backed ffmpeg path fallback when WorkerContext lacks FFmpegPath; empty string means caller must fail-fast."""
    from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
    return SystemSettingsRepository().GetSystemSetting('DefaultTestFFmpegPath') or ''


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _ResolveFFmpegPath() -> str:
    """ffmpeg binary path from WorkerContext, DB fallback, or raise; see pipeline-test-harness.feature.md S3."""
    from Core.WorkerContext import WorkerContext
    Ctx = WorkerContext.TryCurrent()
    if Ctx and Ctx.FFmpegPath:
        return Ctx.FFmpegPath
    Fallback = _DefaultTestFFmpegPath()
    if Fallback:
        return Fallback
    raise RuntimeError("FFmpegPath unavailable. Initialize WorkerContext before calling assertions, or seed SystemSettings.DefaultTestFFmpegPath.")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _ResolveFFprobePath() -> str:
    """ffprobe binary path -- WorkerContext, sibling of ffmpeg, or 'ffprobe' on PATH."""
    from Core.WorkerContext import WorkerContext
    from Core.Path.LocalPath import LocalExists
    Ctx = WorkerContext.TryCurrent()
    if Ctx and Ctx.FFprobePath:
        return Ctx.FFprobePath
    FFmpeg = _ResolveFFmpegPath()
    Candidate = FFmpeg.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')
    if LocalExists(Candidate):
        return Candidate
    return 'ffprobe'


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertIntegratedLoudnessNear(FilePath: str, TargetLufs: float, ToleranceLU: float = 1.0, AudioStreamIndex: int = 0) -> None:
    """ebur128 the file's audio; AssertionError if Integrated outside tolerance."""
    from Core.Path.LocalPath import LocalExists
    if not LocalExists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
    Cmd = [FFmpeg, '-hide_banner', '-nostats', '-nostdin', '-i', FilePath, '-map', f'0:a:{AudioStreamIndex}', '-af', 'ebur128=peak=true', '-f', 'null', NullSink]
    Result = subprocess.run(Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900, check=False)
    if Result.returncode != 0:
        raise AssertionError(f"ebur128 ffmpeg exited with code {Result.returncode} on {FilePath}")
    Parsed = ParseSummary(Result.stderr.decode('utf-8', errors='replace'))
    if Parsed is None:
        raise AssertionError(f"ebur128 stderr missing Summary block for {FilePath}")
    Delta = abs(Parsed.IntegratedLufs - TargetLufs)
    if Delta > ToleranceLU:
        raise AssertionError(f"Integrated loudness out of tolerance for {FilePath}: measured={Parsed.IntegratedLufs:.2f} LUFS, target={TargetLufs:.2f} LUFS, delta={Delta:.2f} LU, tolerance={ToleranceLU:.2f} LU")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertTruePeakAtOrBelow(FilePath: str, MaxDbtp: float, AudioStreamIndex: int = 0) -> None:
    """ebur128 the file's audio; AssertionError if true-peak above ceiling."""
    from Core.Path.LocalPath import LocalExists
    if not LocalExists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
    Cmd = [FFmpeg, '-hide_banner', '-nostats', '-nostdin', '-i', FilePath, '-map', f'0:a:{AudioStreamIndex}', '-af', 'ebur128=peak=true', '-f', 'null', NullSink]
    Result = subprocess.run(Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900, check=False)
    if Result.returncode != 0:
        raise AssertionError(f"ebur128 ffmpeg exited with code {Result.returncode} on {FilePath}")
    Parsed = ParseSummary(Result.stderr.decode('utf-8', errors='replace'))
    if Parsed is None:
        raise AssertionError(f"ebur128 stderr missing Summary block for {FilePath}")
    if Parsed.TruePeakDbtp > MaxDbtp:
        raise AssertionError(f"True peak exceeds ceiling for {FilePath}: measured={Parsed.TruePeakDbtp:.2f} dBTP, max={MaxDbtp:.2f} dBTP")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AudioStreamHash(FilePath: str, AudioStreamIndex: int = 0) -> str:
    """SHA-256 of the file's audio stream bytes via ffmpeg -c copy."""
    from Core.Path.LocalPath import LocalExists
    if not LocalExists(FilePath):
        raise AssertionError(f"File does not exist: {FilePath}")
    FFmpeg = _ResolveFFmpegPath()
    Cmd = [FFmpeg, '-hide_banner', '-nostats', '-nostdin', '-loglevel', 'error', '-i', FilePath, '-map', f'0:a:{AudioStreamIndex}', '-c', 'copy', '-f', 'data', '-']
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


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertAudioBytesIdentical(PathA: str, PathB: str, AudioStreamIndex: int = 0) -> None:
    """Assert audio streams of A and B are byte-identical via -c copy hash."""
    Ha = AudioStreamHash(PathA, AudioStreamIndex)
    Hb = AudioStreamHash(PathB, AudioStreamIndex)
    if Ha != Hb:
        raise AssertionError(f"Audio streams differ:\n  A ({PathA}): {Ha}\n  B ({PathB}): {Hb}")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertDbState(MediaFileId: int, **Expected: Any) -> None:
    """Assert MediaFiles row columns match expected kwargs (case-insensitive); use None for SQL NULL."""
    if not Expected:
        return
    Db = DatabaseService()
    Cols = ','.join(Expected.keys())
    Rows = Db.ExecuteQuery(f"SELECT {Cols} FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    if not Rows:
        raise AssertionError(f"MediaFile {MediaFileId} not found for DB assert")
    Row = Rows[0]
    Mismatches = []
    for Key, Want in Expected.items():
        Got = Row.get(Key)
        if Got != Want:
            Mismatches.append(f"  {Key}: expected={Want!r} actual={Got!r}")
    if Mismatches:
        Joined = "\n".join(Mismatches)
        raise AssertionError(f"MediaFile {MediaFileId} DB state mismatch:\n{Joined}")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertNoQueueRows(MediaFileId: int, TimeoutSec: int = 30) -> None:
    """Assert TranscodeQueue is empty for this file AND MediaFiles.WorkBucket IS NULL (file is compliant). Polls because HandleRemuxResult deletes the queue row AFTER setting FileReplaced=True; the harness can race that gap."""
    import time
    Db = DatabaseService()
    Deadline = time.time() + TimeoutSec
    LastIds = []
    while time.time() < Deadline:
        QueueRows = Db.ExecuteQuery("SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s", (MediaFileId,))
        if not QueueRows:
            break
        LastIds = [int(R['Id']) for R in QueueRows]
        time.sleep(1)
    else:
        raise AssertionError(f"MediaFile {MediaFileId} still has TranscodeQueue rows after {TimeoutSec}s: {LastIds}")
    Flags = Db.ExecuteQuery("SELECT WorkBucket, IsCompliant FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    if not Flags:
        raise AssertionError(f"MediaFile {MediaFileId} not found")
    F = Flags[0]
    Wb = F.get('WorkBucket')
    if Wb:
        raise AssertionError(f"MediaFile {MediaFileId} still flagged for queue: WorkBucket={Wb!r} (expected None)")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AssertVideoCodecMatchesProfile(MediaFileId: int) -> None:
    """Assert the file's current video codec matches its AssignedProfile codec (with known libsvtav1/libx264/libx265 aliasing)."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT m.RelativePath, m.Codec AS CurrentCodec, m.AssignedProfile, p.Codec AS ProfileCodec FROM MediaFiles m LEFT JOIN Profiles p ON p.ProfileName = m.AssignedProfile WHERE m.Id = %s", (MediaFileId,))
    if not Rows:
        raise AssertionError(f"MediaFile {MediaFileId} not found")
    R = Rows[0]
    CurrentCodec = (R.get('CurrentCodec') or '').lower().strip()
    ProfileCodec = (R.get('ProfileCodec') or '').lower().strip()
    if not ProfileCodec:
        raise AssertionError(f"MediaFile {MediaFileId} has no resolvable AssignedProfile codec (AssignedProfile={R.get('AssignedProfile')!r})")
    Aliases = {'libsvtav1': 'av1', 'libaom-av1': 'av1', 'av1_nvenc': 'av1', 'libx264': 'h264', 'libx265': 'hevc', 'hevc_nvenc': 'hevc'}
    Normalized = Aliases.get(ProfileCodec, ProfileCodec)
    if CurrentCodec != Normalized:
        raise AssertionError(f"MediaFile {MediaFileId} video codec mismatch: current={CurrentCodec!r}, profile={ProfileCodec!r} (normalized to {Normalized!r}), file={R.get('RelativePath')!r}")
