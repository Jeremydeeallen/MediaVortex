#!/usr/bin/env python3
"""
BackfillLoudnessThreshold.py
Re-runs ebur128 for every MediaFiles row that has the original three
loudness measurements but is missing the integrated-loudness threshold.

Owns: linear-loudnorm.feature.md criterion 7.

Why re-measure instead of compute: the relative gating threshold from
EBU R128 is signal-dependent and cannot be derived from I/LRA/TP alone.
The only way to get it is to run ebur128 against the audio. Re-running
also self-corrects any drift from prior measurements (the parser is the
new threshold-aware one in LoudnessAnalysisService; persisting through
MeasureAndPersist updates all four columns in one transaction).

Designed to run UNATTENDED on a paused worker for ~hours. Resumable,
idempotent. Does NOT need WorkerService daemon up.

Usage:
    py Scripts/SQLScripts/BackfillLoudnessThreshold.py --worker-name <name> [...]

  --worker-name        Worker whose FFmpegPath + WorkerShareMappings drive
                       binary resolution and path translation. Required.
  --limit N            Cap rows processed (default: no cap).
  --shard-id N         Partition: this instance handles Ids where
                       Id % total-shards == shard-id (0-indexed).
  --total-shards N     Total parallel instances. Default 1 (no partitioning).
  --drive LETTER       Restrict to a single drive (e.g. 'T:').

Idempotent: a second run after a clean first run reports 0 eligible rows.
"""

import argparse
import os
import signal
import sys
from typing import Optional

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
    Cursor.execute(
        """
        SELECT DriveLetter, LocalMountPrefix
        FROM WorkerShareMappings
        WHERE WorkerName = %s
        """,
        (WorkerName,),
    )
    return {Row[0].upper(): Row[1] for Row in Cursor.fetchall()}


def LoadFFmpegPath(Cursor, WorkerName) -> Optional[str]:
    Cursor.execute(
        "SELECT FFmpegPath FROM Workers WHERE Name = %s",
        (WorkerName,),
    )
    Row = Cursor.fetchone()
    return Row[0] if Row else None


def ToLocalPath(CanonicalPath, MountMap, IsLinux):
    """Translate canonical DB path (T:\\Show\\file.mkv) to local worker path.

    UNC paths (\\\\host\\share\\...) on Windows workers without a matching
    mount map pass through unchanged. Drive-letter paths look up the map.
    """
    if not CanonicalPath:
        return CanonicalPath
    if MountMap and len(CanonicalPath) >= 3 and CanonicalPath[1] == ':':
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


# ---------- Driver ----------

INTERRUPTED = False


def InstallSignalHandler():
    def Handler(SigNum, Frame):
        global INTERRUPTED
        INTERRUPTED = True
        print("\nInterrupted; will exit after current row completes.")
    signal.signal(signal.SIGINT, Handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, Handler)


def BuildEligibleQuery(ShardId, TotalShards, Drive):
    """Rows with I/LRA/TP populated and Threshold NULL."""
    Predicates = [
        "SourceIntegratedLufs IS NOT NULL",
        "SourceLoudnessRangeLU IS NOT NULL",
        "SourceTruePeakDbtp IS NOT NULL",
        "SourceIntegratedThresholdLufs IS NULL",
        # Skip rows that already had a measurement failure -- re-running won't help.
        "LoudnessMeasurementFailureReason IS NULL",
    ]
    Params = []
    if Drive:
        Predicates.append("FilePath LIKE %s ESCAPE '!'")
        Params.append(f"{Drive[0].upper()}:%")
    if TotalShards > 1:
        Predicates.append("(Id %% %s) = %s")
        Params.extend([TotalShards, ShardId])
    Where = " AND ".join(Predicates)
    Sql = f"""
        SELECT Id, FilePath
        FROM MediaFiles
        WHERE {Where}
        ORDER BY Id
    """
    return Sql, tuple(Params)


def RunBackfill(Args):
    InstallSignalHandler()

    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        MountMap = LoadMountMap(Cur, Args.worker_name)
        IsLinux = os.name != 'nt'
        FFmpegPath = LoadFFmpegPath(Cur, Args.worker_name) or os.environ.get('FFMPEG_PATH')
        if not FFmpegPath:
            print(
                f"ERROR: FFmpegPath not configured for worker {Args.worker_name!r} "
                f"and FFMPEG_PATH env var not set.",
                file=sys.stderr,
            )
            return 2

        # LoudnessAnalysisService takes FFmpegPath directly -- no
        # WorkerContext singleton needed for a one-shot script.

        Sql, Params = BuildEligibleQuery(Args.shard_id, Args.total_shards, Args.drive)
        Cur.execute(Sql, Params)
        Rows = Cur.fetchall()
        TotalEligible = len(Rows)
        if Args.limit:
            Rows = Rows[: Args.limit]
        print(f"Eligible rows: {TotalEligible}; processing: {len(Rows)}")
        if not Rows:
            print("Nothing to do -- idempotent re-run path. Exiting.")
            return 0

        from Features.LoudnessAnalysis.LoudnessAnalysisService import LoudnessAnalysisService
        Svc = LoudnessAnalysisService(FFmpegPath=FFmpegPath)

        Success = 0
        Failed = 0
        Skipped = 0

        for I, (Id, FilePath) in enumerate(Rows, start=1):
            if INTERRUPTED:
                print("Stopping early due to signal.")
                break
            LocalPath = ToLocalPath(FilePath, MountMap, IsLinux)
            if not os.path.exists(LocalPath):
                print(f"[{I}/{len(Rows)}] MISS Id={Id}: {LocalPath}")
                Skipped += 1
                continue

            Ok, Reason = Svc.MeasureAndPersist(Id, LocalPath)
            if Ok and Reason is None:
                Success += 1
                Status = 'ok'
            elif Ok and Reason:
                Failed += 1
                Status = f'fail/{Reason}'
            else:
                Skipped += 1
                Status = f'skip/{Reason}'
            if I <= 10 or I % 50 == 0:
                print(f"[{I}/{len(Rows)}] Id={Id} {Status}: {os.path.basename(LocalPath)}")

        print()
        print(f"Done. Success={Success} Failed={Failed} Skipped={Skipped}")
        return 0
    finally:
        Cur.close()
        Conn.close()


def Main():
    Parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    Parser.add_argument('--worker-name', required=True)
    Parser.add_argument('--limit', type=int, default=0)
    Parser.add_argument('--shard-id', type=int, default=0)
    Parser.add_argument('--total-shards', type=int, default=1)
    Parser.add_argument('--drive', type=str, default=None)
    Args = Parser.parse_args()
    sys.exit(RunBackfill(Args))


if __name__ == '__main__':
    Main()
