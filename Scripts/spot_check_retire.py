"""One-shot script: spot-check 5 RETIRE candidates before bulk delete."""
import os, sys, subprocess, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Tests.Pipeline.Harness.Invocation import _EnsureWorkerContext
_EnsureWorkerContext('I9-2024')

from Core.Database.DatabaseService import DatabaseService
from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
from Core.WorkerContext import WorkerContext

Db = DatabaseService()
ctx = WorkerContext.Current()
roots = LoadStorageRoots(Db)

rows = Db.ExecuteQuery(r"""
    SELECT a.Id AS AId, a.FilePath AS APath,
           b.Id AS BId, b.FilePath AS BPath
    FROM MediaFiles a
    JOIN MediaFiles b ON LOWER(b.FilePath) = LOWER(
        SUBSTRING(a.FilePath FROM 1 FOR LENGTH(a.FilePath) - LENGTH(
            SUBSTRING(a.FilePath FROM E'\.[^.\\/]+$')
        )) || '-mv.mp4'
    )
    WHERE a.Id != b.Id
      AND a.FilePath LIKE %s
      AND EXISTS (
          SELECT 1 FROM TranscodeAttempts t
          WHERE t.MediaFileId = a.Id AND t.Success = TRUE AND t.FileReplaced = TRUE
      )
    ORDER BY RANDOM()
    LIMIT 5
""", ('%.mkv',))

print(f"Sampling {len(rows)} RETIRE candidates...\n")

ffmpeg = ctx.FFmpegPath
ffprobe = ctx.FFprobePath
RE_I = re.compile(r'I:\s+(-?\d+(?:\.\d+)?)\s+LUFS')
RE_P = re.compile(r'Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS')

for r in rows:
    sr, rel = PathParse(r['BPath'], roots)
    blocal = PathResolve(sr, rel, ctx.WorkerName, Db) if sr and rel else None
    print(f"A(.mkv) = {r['AId']} {os.path.basename(r['APath'])}")
    print(f"B(-mv)  = {r['BId']} {os.path.basename(r['BPath'])}")
    if not blocal or not os.path.exists(blocal):
        print("  CHECK: B FILE MISSING\n")
        continue
    sz = os.path.getsize(blocal)
    pr = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-print_format', 'flat', blocal],
                        capture_output=True, text=True, timeout=30)
    has_video = '.codec_type="video"' in pr.stdout
    has_audio = '.codec_type="audio"' in pr.stdout
    eb = subprocess.run([ffmpeg, '-hide_banner', '-nostats', '-nostdin', '-i', blocal,
                        '-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', 'NUL'],
                       capture_output=True, timeout=600)
    stderr = eb.stderr.decode('utf-8', errors='replace')
    tail_idx = stderr.rfind('Summary:')
    tail_text = stderr[tail_idx:] if tail_idx >= 0 else stderr
    i_match = RE_I.search(tail_text)
    p_match = RE_P.search(tail_text)
    lufs = float(i_match.group(1)) if i_match else None
    peak = float(p_match.group(1)) if p_match else None
    print(f"  size={sz:,}  video={has_video}  audio={has_audio}")
    print(f"  I={lufs} LUFS  Peak={peak} dBTP")
    if lufs is not None:
        delta = abs(lufs - (-23.0))
        verdict = "NORMALIZED" if delta <= 1.5 else f"OFF-TARGET ({delta:.1f} LU)"
        print(f"  audio verdict: {verdict}")
    print()
