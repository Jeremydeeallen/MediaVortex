#!/usr/bin/env python3
"""
BackfillProbeAndLoudness.py
Phase 1 standalone backfill for media-tabs-and-loudness.feature.md.

Runs FFmpeg's ebur128 filter on every MediaFiles row where audio loudness has
not been measured, and persists:
  - SourceIntegratedLufs   (LUFS)
  - SourceLoudnessRangeLU  (LU)
  - SourceTruePeakDbtp     (dBTP)
  - LoudnessMeasuredAt     (NOW())
  - LastProbedFileSize     (from os.stat)
  - LastProbedFileMtime    (from os.stat)

Designed to run UNATTENDED on a paused worker for ~hours. Resumable, idempotent.
Does NOT need WorkerService daemon up; does NOT claim queue rows.

Usage:
    python BackfillProbeAndLoudness.py --worker-name <name> [...]

  --worker-name        Worker whose FFmpegPath and WorkerShareMappings drive
                       binary resolution and path translation. Required.
  --limit N            Cap rows processed (default: no cap).
  --batch-size N       Commit every N rows (default: 25).
  --shard-id N         Partition: this instance handles Ids where
                       Id % total-shards == shard-id (0-indexed).
  --total-shards N     Total parallel instances. Default 1 (no partitioning).
  --drive LETTER       Restrict to a single drive (e.g. 'T:'). Default: all drives.

Parallel deployment example (8-way fan-out across larry-worker-{1..8}):
    for i in 1 2 3 4 5 6 7 8; do
      nohup python3 BackfillProbeAndLoudness.py \
        --worker-name larry-worker-${i} \
        --shard-id $((i-1)) --total-shards 8 \
        > /tmp/loudness-shard-${i}.log 2>&1 &
    done

Examples:
    # Smoke test on 5 rows before unleashing on the library
    python BackfillProbeAndLoudness.py --worker-name dot-worker-1 --limit 5

    # Full run, will take ~20 hours on the 54k unmeasured population
    python BackfillProbeAndLoudness.py --worker-name dot-worker-1

The script orders work by PriorityScore DESC NULLS LAST so files the operator
is most likely to queue next get measured first. Failures stamp
LoudnessMeasuredAt=NOW() with NULL measurement values so they don't retry
forever -- a subsequent root-cause fix can re-run with a different WHERE
predicate if needed.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
from datetime import datetime

import psycopg2


# ---------- DB ----------

def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', '10.0.0.15'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


# ---------- Path translation ----------

def LoadMountMap(Cursor, WorkerName):
    """Return {DriveLetter: LocalMountPrefix} for the given worker.

    Empty dict means no mappings -- paths pass through unchanged (Windows worker
    pattern). A Linux worker without mappings is misconfigured.
    """
    Cursor.execute(
        """
        SELECT DriveLetter, LocalMountPrefix
        FROM WorkerShareMappings
        WHERE WorkerName = %s
        """,
        (WorkerName,),
    )
    return {Row[0].upper(): Row[1] for Row in Cursor.fetchall()}


def ToLocalPath(CanonicalPath, MountMap, IsLinux):
    """Translate canonical DB path (T:\\Show\\file.mkv) to local worker path."""
    if not CanonicalPath:
        return CanonicalPath
    if MountMap:
        DriveLetter = CanonicalPath[0].upper()
        if DriveLetter in MountMap:
            LocalPath = MountMap[DriveLetter] + CanonicalPath[3:]
        else:
            LocalPath = CanonicalPath
    else:
        LocalPath = CanonicalPath
    if IsLinux:
        LocalPath = LocalPath.replace('\\', '/')
    return LocalPath


# ---------- FFmpeg invocation + parser ----------

# Regex extracts from the ebur128 SUMMARY block (printed at end of run on
# stderr). The summary looks like:
#
#   [Parsed_ebur128_0 @ ...] Summary:
#
#     Integrated loudness:
#       I:         -23.5 LUFS
#       Threshold: -33.5 LUFS
#
#     Loudness range:
#       LRA:         7.2 LU
#
#     True peak:
#       Peak:       -1.5 dBFS
#
# `I:` and `LRA:` also appear in every per-frame PROGRESS line during the
# run, with values that converge from the silence floor toward the true
# value. We must NOT pick those up -- pre-2026-05-17 a naive first-match
# regex captured I=-70 LUFS from the warmup progress line of every file.
# `Peak:` only appears in the summary (progress lines use `TPK:`).
#
# Strategy: split stderr on `Summary:` marker; if present, search only the
# tail. Otherwise fall back to LAST occurrence via findall.
_RE_INTEGRATED = re.compile(r'I:\s+(-?\d+(?:\.\d+)?)\s+LUFS')
_RE_LRA = re.compile(r'LRA:\s+(-?\d+(?:\.\d+)?)\s+LU')
_RE_PEAK = re.compile(r'Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS')


def _ParseSummary(Stderr):
    """Extract (Integrated, LRA, TruePeak) from ebur128 stderr.

    Returns None on any missing field. Anchors to the summary block at
    the tail of stderr; falls back to last-occurrence match if the marker
    isn't found.
    """
    Marker = 'Summary:'
    Idx = Stderr.rfind(Marker)
    Tail = Stderr[Idx:] if Idx >= 0 else Stderr

    I_Match = _RE_INTEGRATED.search(Tail) if Idx >= 0 else None
    L_Match = _RE_LRA.search(Tail) if Idx >= 0 else None
    P_Match = _RE_PEAK.search(Tail)

    if not (I_Match and L_Match and P_Match):
        # Fallback: take LAST occurrence in full stderr (handles weird FFmpeg
        # output where the Summary header is missing).
        I_All = _RE_INTEGRATED.findall(Stderr)
        L_All = _RE_LRA.findall(Stderr)
        P_All = _RE_PEAK.findall(Stderr)
        if not (I_All and L_All and P_All):
            return None
        return (float(I_All[-1]), float(L_All[-1]), float(P_All[-1]))

    return (float(I_Match.group(1)), float(L_Match.group(1)), float(P_Match.group(1)))


def MeasureLoudness(FFmpegPath, FilePath, TimeoutSeconds=600):
    """Run ebur128 against FilePath, return (Integrated, LRA, TruePeak) or None.

    Maps -map 0:a:0 to match BuildRemuxCommand's single-English-track behavior.
    Output goes to /dev/null (Linux) or NUL (Windows) -- we only care about
    the summary printed to stderr.

    Returns None when:
      - FFmpeg returns non-zero exit
      - Output doesn't contain all three summary lines
      - Timeout elapses (treated as failure)
    """
    NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
    Cmd = [
        FFmpegPath,
        '-hide_banner', '-nostats', '-nostdin',
        '-i', FilePath,
        '-map', '0:a:0',
        '-af', 'ebur128=peak=true',
        '-f', 'null',
        NullSink,
    ]
    try:
        Result = subprocess.run(
            Cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=TimeoutSeconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, 'timeout'
    except FileNotFoundError:
        return None, 'ffmpeg_not_found'

    if Result.returncode != 0:
        # Most commonly: no audio stream, file unreadable, codec unsupported.
        return None, f'ffmpeg_exit_{Result.returncode}'

    Stderr = Result.stderr.decode('utf-8', errors='replace')
    Parsed = _ParseSummary(Stderr)
    if Parsed is None:
        return None, 'parse_failed'
    return Parsed, None


# ---------- Backfill driver ----------

_STOP_REQUESTED = False


def _OnSignal(_Signum, _Frame):
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    print('\n[interrupt] finishing current row and committing; press Ctrl+C again to abort hard.\n')


def RunBackfill(WorkerName, Limit, BatchSize, ShardId, TotalShards, Drive=None):
    signal.signal(signal.SIGINT, _OnSignal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _OnSignal)

    Conn = GetConnection()
    Cur = Conn.cursor()

    # Resolve worker config
    Cur.execute(
        """
        SELECT FFmpegPath FROM Workers WHERE WorkerName = %s
        """,
        (WorkerName,),
    )
    Row = Cur.fetchone()
    if not Row:
        print(f"ERROR: Worker '{WorkerName}' not found in Workers table.")
        sys.exit(2)
    FFmpegPath = Row[0]
    if not FFmpegPath:
        print(f"ERROR: Worker '{WorkerName}' has no FFmpegPath configured.")
        sys.exit(2)

    MountMap = LoadMountMap(Cur, WorkerName)
    IsLinux = '/' in (next(iter(MountMap.values()), '') or '') or os.name != 'nt'

    print(f"Worker:       {WorkerName}")
    print(f"FFmpegPath:   {FFmpegPath}")
    print(f"MountMap:     {MountMap if MountMap else '(passthrough)'}")
    print(f"Platform:     {'linux-style' if IsLinux else 'windows-style'} paths")
    print(f"Limit:        {Limit if Limit else '(no cap)'}")
    print(f"BatchSize:    {BatchSize}")
    print(f"Shard:        {ShardId}/{TotalShards} (Id % {TotalShards} == {ShardId})")
    print(f"Drive:        {Drive if Drive else '(all)'}")
    print()

    # Select work. Optional partition by Id mod TotalShards so multiple
    # instances on different workers process disjoint subsets concurrently.
    # Optional drive filter restricts to one drive letter prefix (e.g. T:).
    LimitClause = f"LIMIT {int(Limit)}" if Limit else ""
    # Use %% for modulo so psycopg2 doesn't interpret % as a parameter
    # placeholder once Cur.execute() is called with a params tuple.
    ShardClause = (
        f"AND (Id %% {int(TotalShards)}) = {int(ShardId)}"
        if TotalShards > 1 else ""
    )
    DriveClause = ""
    QueryParams = ()
    if Drive:
        DrivePrefix = Drive.rstrip(':\\/') + ':'
        DriveClause = "AND FilePath LIKE %s"
        QueryParams = (f'{DrivePrefix}%',)
    Cur.execute(
        f"""
        SELECT Id, FilePath, AudioBitrateKbps, AudioChannels
        FROM MediaFiles
        WHERE LoudnessMeasuredAt IS NULL
          AND AudioCorruptSuspect = FALSE
          AND FilePath IS NOT NULL
          {ShardClause}
          {DriveClause}
        ORDER BY PriorityScore DESC NULLS LAST, Id
        {LimitClause}
        """,
        QueryParams,
    )
    Rows = Cur.fetchall()
    Total = len(Rows)
    print(f"Selected {Total} rows for measurement.\n")
    if Total == 0:
        Conn.close()
        return

    Succeeded = 0
    Failed = 0
    Skipped = 0
    PendingBatch = []
    StartedAt = datetime.now()

    def Flush():
        if not PendingBatch:
            return
        Cur.executemany(
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
            PendingBatch,
        )
        Conn.commit()
        PendingBatch.clear()

    try:
        for Index, (MediaFileId, CanonicalPath, _AudioBitrate, _AudioChannels) in enumerate(Rows, 1):
            if _STOP_REQUESTED:
                print(f"\nStop requested at row {Index}/{Total}. Committing pending batch.")
                break

            LocalPath = ToLocalPath(CanonicalPath, MountMap, IsLinux)

            # Stat short-circuit: missing file -> skip (no measurement, no stamp).
            try:
                Stat = os.stat(LocalPath)
            except OSError as Ex:
                Skipped += 1
                if Index % 100 == 0 or Index <= 5:
                    print(f"  [{Index}/{Total}] SKIP Id={MediaFileId} stat-failed: {Ex}")
                continue

            FileSize = Stat.st_size
            FileMtime = datetime.fromtimestamp(Stat.st_mtime)

            Measurement, FailureReason = MeasureLoudness(FFmpegPath, LocalPath)
            if Measurement is None:
                # Stamp LoudnessMeasuredAt=NOW() with NULL measurements so the
                # row drops out of the unmeasured set and we don't retry forever.
                PendingBatch.append((None, None, None, FileSize, FileMtime, MediaFileId))
                Failed += 1
                if Index % 100 == 0 or Index <= 5:
                    print(f"  [{Index}/{Total}] FAIL Id={MediaFileId} {FailureReason}: {LocalPath}")
            else:
                IntegratedLufs, LRA, TruePeak = Measurement
                PendingBatch.append((IntegratedLufs, LRA, TruePeak, FileSize, FileMtime, MediaFileId))
                Succeeded += 1
                if Index % 100 == 0 or Index <= 5:
                    Elapsed = (datetime.now() - StartedAt).total_seconds()
                    Rate = Index / Elapsed if Elapsed > 0 else 0
                    Remaining = (Total - Index) / Rate if Rate > 0 else 0
                    print(
                        f"  [{Index}/{Total}] OK   Id={MediaFileId} "
                        f"I={IntegratedLufs:>6.1f} LUFS  LRA={LRA:>5.1f} LU  TP={TruePeak:>5.1f} dBFS"
                        f"  ({Rate:.1f} rows/s, ~{int(Remaining/60)} min remaining)"
                    )

            if len(PendingBatch) >= BatchSize:
                Flush()
    finally:
        Flush()
        Conn.close()

    Elapsed = (datetime.now() - StartedAt).total_seconds()
    print()
    print(f"--- Backfill summary ---")
    print(f"  Total rows considered: {Total}")
    print(f"  Succeeded:             {Succeeded}")
    print(f"  Failed (stamped NULL): {Failed}")
    print(f"  Skipped (stat error):  {Skipped}")
    print(f"  Elapsed:               {int(Elapsed)} sec  ({(Elapsed/Total if Total else 0):.2f} sec/row)")


def Main():
    Parser = argparse.ArgumentParser(description='Phase 1 loudness backfill')
    Parser.add_argument('--worker-name', required=True, help='Worker for FFmpegPath + MountMap')
    Parser.add_argument('--limit', type=int, default=None, help='Cap rows processed')
    Parser.add_argument('--batch-size', type=int, default=25, help='Commit every N rows')
    Parser.add_argument('--shard-id', type=int, default=0,
                        help='0-indexed shard for parallel runs (default 0)')
    Parser.add_argument('--total-shards', type=int, default=1,
                        help='Total parallel shards (default 1 = no partitioning)')
    Parser.add_argument('--drive', default=None,
                        help="Restrict to one drive letter (e.g. 'T:'). Default all drives.")
    Args = Parser.parse_args()
    if Args.total_shards < 1 or Args.shard_id < 0 or Args.shard_id >= Args.total_shards:
        Parser.error(
            f"--shard-id ({Args.shard_id}) must be in [0, {Args.total_shards - 1}]"
        )
    RunBackfill(Args.worker_name, Args.limit, Args.batch_size,
                Args.shard_id, Args.total_shards, Args.drive)


if __name__ == '__main__':
    Main()
